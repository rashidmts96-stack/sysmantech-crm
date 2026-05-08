import csv
import io
from datetime import datetime
from urllib.parse import urlencode

from flask import Response, flash, jsonify, redirect, render_template, request, session
from time_utils import business_now_naive, normalize_display_datetime


def register_dashboard_settings_routes(app, deps):
    get_db = deps["get_db"]
    db_error = deps["Error"]
    build_dashboard_filters = deps["build_dashboard_filters"]
    normalize_date_input = deps["_normalize_date_input"]
    get_multi_values = deps["_get_multi_values"]
    normalize_option_list = deps["_normalize_option_list"]
    has_legacy_password = deps["_has_legacy_password"]
    add_csrf_protected_endpoints = deps["_add_csrf_protected_endpoints"]
    load_known_branches = deps["load_known_branches"]
    decorate_job_rows_with_transfer_summary = deps["decorate_job_rows_with_transfer_summary"]
    format_datetime_display = deps["format_datetime_display"]
    get_age_group = deps["get_age_group"]
    get_branch_revenue_target = deps["get_branch_revenue_target"]
    get_cashflow_dashboard_snapshot = deps["get_cashflow_dashboard_snapshot"]
    default_branches = deps["DEFAULT_BRANCHES"]
    admin_dashboard_roles = {"super_admin", "admin"}
    dashboard_branch_session_key = "dashboard_branch_scope"

    def _flash_internal_error(user_message, exc=None):
        if exc is not None:
            app.logger.exception(user_message)
        flash(user_message, "danger")

    def _can_switch_dashboard_branch(role):
        return role in admin_dashboard_roles

    def _normalize_dashboard_branch_value(raw_value):
        value = str(raw_value or "").strip()
        if not value or value.upper() in {"ALL", "ALL BRANCHES"}:
            return "ALL"
        return value

    def _build_url(path, query_params=None):
        cleaned_params = {}
        for key, value in (query_params or {}).items():
            if value is None:
                continue
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
            cleaned_params[key] = value
        if not cleaned_params:
            return path
        return path + "?" + urlencode(cleaned_params, doseq=True)

    def _build_onsite_dashboard_alert_payload():
        onsite_dashboard_alert_count = 0
        onsite_dashboard_alert_status = ""
        onsite_dashboard_alert_label = "Onsite Call or Lead"
        onsite_service = app.extensions.get("onsite_calls_service")
        if onsite_service is not None:
            try:
                onsite_actor = onsite_service.actor()
                onsite_counts = onsite_service.dashboard_counts(onsite_actor, {}, use_cache=False)
                if onsite_actor.get("has_global_scope"):
                    onsite_dashboard_alert_status = "New Lead"
                    onsite_dashboard_alert_label = "Onsite Call or Lead"
                else:
                    onsite_dashboard_alert_status = "Assigned"
                    onsite_dashboard_alert_label = "Lead Assigned"
                onsite_dashboard_alert_count = int(onsite_counts.get(onsite_dashboard_alert_status) or 0)
            except Exception:
                app.logger.exception("Failed to load onsite dashboard alert count")

        onsite_dashboard_url = _build_url(
            "/onsite-calls",
            {
                "status": onsite_dashboard_alert_status if onsite_dashboard_alert_count > 0 else None,
            },
        )

        return {
            "onsite_dashboard_alert_count": onsite_dashboard_alert_count,
            "onsite_dashboard_alert_status": onsite_dashboard_alert_status,
            "onsite_dashboard_alert_label": onsite_dashboard_alert_label,
            "onsite_dashboard_url": onsite_dashboard_url,
        }

    def _get_dashboard_branch_options(cursor):
        option_values = []
        try:
            option_values.extend(load_known_branches(cursor))
        except Exception:
            option_values.extend([branch for branch in default_branches if branch and str(branch).upper() != "ALL"])
            try:
                cursor.execute(
                    "SELECT DISTINCT branch_name FROM jobs WHERE branch_name IS NOT NULL AND branch_name <> '' ORDER BY branch_name"
                )
                option_values.extend([row.get("branch_name") for row in cursor.fetchall() if row.get("branch_name")])
            except Exception:
                pass
        normalized = normalize_option_list(option_values)
        return ["ALL"] + [option for option in normalized if str(option).upper() != "ALL"]

    def _resolve_dashboard_branch_scope(cursor, role):
        if not _can_switch_dashboard_branch(role):
            return (session.get("branch") or "").strip(), []

        branch_options = _get_dashboard_branch_options(cursor)
        branch_lookup = {str(option).upper(): option for option in branch_options if option}
        selected_value = _normalize_dashboard_branch_value(session.get(dashboard_branch_session_key, "ALL"))
        resolved_value = branch_lookup.get(selected_value.upper(), "ALL")
        session[dashboard_branch_session_key] = resolved_value
        return resolved_value, branch_options

    def _get_dashboard_report_data(cursor, scope_sql, params):
        status_columns = [
            "Open",
            "Observation",
            "Waiting For Customer Approval",
            "Spare Waiting",
            "Outside Service",
            "Inspire",
            "Ready-Waiting for Customer",
            "Non-Repairable Waiting for Customer",
        ]
        active_scope_clause = "(closure_status IS NULL OR closure_status='') AND status <> 'Closed'"

        cursor.execute(
            f"""
            SELECT branch_name, status, COUNT(*) AS c
            FROM jobs
            WHERE {scope_sql}
              AND {active_scope_clause}
            GROUP BY branch_name, status
            ORDER BY branch_name
            """,
            params,
        )
        grouped_rows = cursor.fetchall()

        branch_map = {}
        branch_report_counts = {status_name: 0 for status_name in status_columns}
        branch_report_total = 0
        for row in grouped_rows:
            bname = row.get("branch_name") or "Unknown"
            status = row.get("status") or ""
            count = int(row.get("c") or 0)
            branch_map.setdefault(
                bname,
                {
                    "branch_name": bname,
                    "counts": {status_name: 0 for status_name in status_columns},
                    "total": 0,
                },
            )
            if status in branch_map[bname]["counts"]:
                branch_map[bname]["counts"][status] += count
                branch_report_counts[status] += count
                branch_report_total += count
            branch_map[bname]["total"] += count

        branch_wise_rows = [branch_map[key] for key in sorted(branch_map.keys())]

        branch_wise_totals = {status_name: 0 for status_name in status_columns}
        branch_wise_grand_total = 0
        for row in branch_wise_rows:
            for status_name in status_columns:
                branch_wise_totals[status_name] += row["counts"][status_name]
            branch_wise_grand_total += row["total"]

        age_buckets = ["0-2", "3-5", "6-10", "11-15", "16-30", "31-90", "91-180", "181+"]
        age_bucket_ranges = {
            "0-2": (0, 2),
            "3-5": (3, 5),
            "6-10": (6, 10),
            "11-15": (11, 15),
            "16-30": (16, 30),
            "31-90": (31, 90),
            "91-180": (91, 180),
            "181+": (181, None),
        }

        cursor.execute(
            f"""
            SELECT status, created_at
            FROM jobs
            WHERE {scope_sql}
              AND {active_scope_clause}
            """,
            params,
        )
        ageing_rows_raw = cursor.fetchall()

        ageing_rows = []
        ageing_totals_by_bucket = {bucket: 0 for bucket in age_buckets}
        ageing_grand_total = 0

        now = business_now_naive()
        for status_name in status_columns:
            row_counts = {bucket: 0 for bucket in age_buckets}
            row_total = 0

            for item in ageing_rows_raw:
                if (item.get("status") or "") != status_name:
                    continue

                created_at = normalize_display_datetime(item.get("created_at"))

                if not created_at:
                    continue

                age_days = (now.date() - created_at.date()).days
                if age_days < 0:
                    age_days = 0

                bucket = get_age_group(age_days)
                if bucket in row_counts:
                    row_counts[bucket] += 1
                    row_total += 1

            for bucket in age_buckets:
                ageing_totals_by_bucket[bucket] += row_counts[bucket]
            ageing_grand_total += row_total

            ageing_rows.append(
                {
                    "status": status_name,
                    "counts": row_counts,
                    "total": row_total,
                }
            )

        return {
            "status_columns": status_columns,
            "branch_wise_rows": branch_wise_rows,
            "branch_wise_totals": branch_wise_totals,
            "branch_wise_grand_total": branch_wise_grand_total,
            "branch_report_counts": branch_report_counts,
            "branch_report_total": branch_report_total,
            "ageing_rows": ageing_rows,
            "age_buckets": age_buckets,
            "age_bucket_ranges": age_bucket_ranges,
            "ageing_totals_by_bucket": ageing_totals_by_bucket,
            "ageing_grand_total": ageing_grand_total,
        }

    @app.route("/dashboard/branch-options")
    def dashboard_branch_options():
        if "username" not in session:
            return jsonify({"success": False, "message": "Authentication required"}), 401

        role = session.get("role")
        if not _can_switch_dashboard_branch(role):
            return jsonify({"success": False, "message": "Access denied"}), 403

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            selected_branch, branch_options = _resolve_dashboard_branch_scope(cursor, role)
            return jsonify(
                {
                    "success": True,
                    "selected_branch": selected_branch,
                    "branch_options": branch_options,
                }
            )
        except db_error:
            app.logger.exception("Failed to load dashboard branch options")
            return jsonify({"success": False, "message": "Could not load dashboard branches"}), 500
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    @app.route("/dashboard/branch-scope", methods=["POST"])
    def dashboard_set_branch_scope():
        if "username" not in session:
            return jsonify({"success": False, "message": "Authentication required"}), 401

        role = session.get("role")
        if not _can_switch_dashboard_branch(role):
            return jsonify({"success": False, "message": "Access denied"}), 403

        payload = request.get_json(silent=True) if request.is_json else None
        requested_branch = ""
        if isinstance(payload, dict):
            requested_branch = payload.get("branch_name", "")
        if not requested_branch:
            requested_branch = request.form.get("branch_name", "")

        normalized_branch = _normalize_dashboard_branch_value(requested_branch)

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            branch_options = _get_dashboard_branch_options(cursor)
            branch_lookup = {str(option).upper(): option for option in branch_options if option}

            if normalized_branch == "ALL":
                selected_branch = "ALL"
                display_name = "All Branches"
            else:
                selected_branch = branch_lookup.get(normalized_branch.upper())
                if not selected_branch:
                    return jsonify({"success": False, "message": "Invalid branch selection"}), 400
                display_name = selected_branch

            session[dashboard_branch_session_key] = selected_branch
            return jsonify(
                {
                    "success": True,
                    "selected_branch": selected_branch,
                    "display_name": display_name,
                }
            )
        except db_error as e:
            app.logger.exception("Failed to update dashboard branch scope")
            return jsonify({"success": False, "message": "Could not update dashboard branch"}), 500
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    @app.route("/dashboard/onsite-alert")
    def dashboard_onsite_alert():
        if "username" not in session:
            return jsonify({"success": False, "message": "Authentication required"}), 401

        try:
            payload = _build_onsite_dashboard_alert_payload()
            payload["success"] = True
            return jsonify(payload)
        except Exception:
            app.logger.exception("Failed to load dashboard onsite alert")
            return jsonify({"success": False, "message": "Could not load onsite alert"}), 500

    add_csrf_protected_endpoints("dashboard_set_branch_scope")

    @app.route("/dashboard-report-export/<report_name>")
    def dashboard_report_export(report_name):
        if "username" not in session:
            return redirect("/login")

        role = session.get("role")
        branch = session.get("branch")
        normalized_report = (report_name or "").strip().lower()

        allowed_reports = {
            "branch-wise": admin_dashboard_roles,
            "branch": {"coordinator", "engineer"},
            "ageing": {"super_admin", "admin", "coordinator", "engineer"},
        }
        if normalized_report not in allowed_reports:
            flash("Invalid report export", "danger")
            return redirect("/dashboard")
        if role not in allowed_reports[normalized_report]:
            flash("Access denied", "danger")
            return redirect("/dashboard")

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            selected_dashboard_branch, _ = _resolve_dashboard_branch_scope(cursor, role)
            dashboard_scope_branch = selected_dashboard_branch or (branch or "")

            dashboard_args = request.args.copy()
            if _can_switch_dashboard_branch(role):
                dashboard_args.setlist("filter_branch", [])

            dashboard_filters = build_dashboard_filters(dashboard_args, role, dashboard_scope_branch)
            report_data = _get_dashboard_report_data(cursor, dashboard_filters["where_sql"], dashboard_filters["params"])

            buffer = io.StringIO()
            writer = csv.writer(buffer)

            if normalized_report == "branch-wise":
                writer.writerow(["Service Location"] + report_data["status_columns"] + ["Total"])
                for row in report_data["branch_wise_rows"]:
                    writer.writerow([row["branch_name"]] + [row["counts"][status_name] for status_name in report_data["status_columns"]] + [row["total"]])
                writer.writerow(["Total"] + [report_data["branch_wise_totals"][status_name] for status_name in report_data["status_columns"]] + [report_data["branch_wise_grand_total"]])
            elif normalized_report == "branch":
                scope_label = selected_dashboard_branch if selected_dashboard_branch != "ALL" else "All Branches"
                writer.writerow(["Scope"] + report_data["status_columns"] + ["Total"])
                writer.writerow([scope_label] + [report_data["branch_report_counts"][status_name] for status_name in report_data["status_columns"]] + [report_data["branch_report_total"]])
            else:
                writer.writerow(["Job Card Status"] + [f"{bucket} Days" for bucket in report_data["age_buckets"]] + ["Total"])
                for row in report_data["ageing_rows"]:
                    writer.writerow([row["status"]] + [row["counts"][bucket] for bucket in report_data["age_buckets"]] + [row["total"]])
                writer.writerow(["Total"] + [report_data["ageing_totals_by_bucket"][bucket] for bucket in report_data["age_buckets"]] + [report_data["ageing_grand_total"]])

            filename = f"dashboard_{normalized_report}_{business_now_naive().strftime('%Y%m%d_%H%M')}.csv"
            return Response(
                buffer.getvalue(),
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        except db_error as e:
            _flash_internal_error("Report export failed", e)
            return redirect("/dashboard")
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    @app.route("/dashboard-filters")
    def dashboard_filters():

        if "username" not in session:
            return redirect("/login")

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            branch = session.get("branch")
            role = session.get("role")

            from_date = normalize_date_input(request.args.get("from_date", ""))
            to_date = normalize_date_input(request.args.get("to_date", ""))
            date_field_values = get_multi_values(request.args, "date_field")
            if not date_field_values:
                date_field_values = ["created"]

            filter_branch_values = get_multi_values(request.args, "filter_branch")
            filter_status_values = get_multi_values(request.args, "filter_status")
            filter_closure_values = get_multi_values(request.args, "filter_closure")
            filter_engineer_values = get_multi_values(request.args, "filter_engineer")

            apply_filters = request.args.get("apply", "").strip() == "1"

            if role in ["super_admin", "admin"]:
                cursor.execute(
                    "SELECT DISTINCT branch_name FROM jobs WHERE branch_name IS NOT NULL ORDER BY branch_name"
                )
                raw_branch_options = [r["branch_name"] for r in cursor.fetchall()]
                branch_options = normalize_option_list(raw_branch_options, keep_all_first=True)
            else:
                branch_options = []

            cursor.execute(
                "SELECT DISTINCT assigned_engineer FROM jobs WHERE assigned_engineer IS NOT NULL AND assigned_engineer <> '' ORDER BY assigned_engineer"
            )
            engineer_values = [r["assigned_engineer"] for r in cursor.fetchall()]
            try:
                cursor.execute(
                    "SELECT DISTINCT specialist_engineer FROM job_service_transfers WHERE specialist_engineer IS NOT NULL AND specialist_engineer <> '' ORDER BY specialist_engineer"
                )
                engineer_values.extend([r["specialist_engineer"] for r in cursor.fetchall()])
            except Exception:
                pass
            engineer_options = normalize_option_list(engineer_values)

            cursor.execute(
                "SELECT DISTINCT closure_status FROM jobs WHERE closure_status IS NOT NULL AND closure_status <> '' ORDER BY closure_status"
            )
            closure_options = normalize_option_list([r["closure_status"] for r in cursor.fetchall()])

            status_columns = [
                "Open",
                "Observation",
                "Waiting For Customer Approval",
                "Spare Waiting",
                "Outside Service",
                "Inspire",
                "Ready-Waiting for Customer",
                "Non-Repairable Waiting for Customer",
            ]

            filtered_jobs = []
            filter_query = ""
            if apply_filters:
                dashboard_filters_data = build_dashboard_filters(request.args, role, branch)
                where_sql = dashboard_filters_data["where_sql"]
                params = dashboard_filters_data["params"]

                cursor.execute(
                    f"""
                    SELECT id, job_number, customer_name, mobile, device, model, serial_number,
                           complaint, status, branch_name, priority, call_type, complaint_type,
                           assigned_engineer, closure_status, service_charges, created_at, closure_date
                    FROM jobs
                    WHERE {where_sql}
                    ORDER BY id DESC
                    """,
                    params,
                )
                filtered_jobs = cursor.fetchall()
                decorate_job_rows_with_transfer_summary(cursor, filtered_jobs)

                for row in filtered_jobs:
                    created_at = normalize_display_datetime(row.get("created_at"))
                    age_days = None
                    if created_at:
                        age_days = (business_now_naive().date() - created_at.date()).days
                        if age_days < 0:
                            age_days = 0
                    row["created_on"] = format_datetime_display(created_at)
                    row["closed_on"] = format_datetime_display(row.get("closure_date"))
                    row["age"] = age_days if age_days is not None else "-"

                query_data = {
                    "from_date": from_date,
                    "to_date": to_date,
                    "date_field": date_field_values,
                    "filter_branch": filter_branch_values,
                    "filter_status": filter_status_values,
                    "filter_closure": filter_closure_values,
                    "filter_engineer": filter_engineer_values,
                }
                filter_query = urlencode(query_data, doseq=True)

            return render_template(
                "dashboard_filters.html",
                branch=branch,
                from_date=from_date,
                to_date=to_date,
                date_fields=date_field_values,
                filter_branches=filter_branch_values,
                filter_statuses=filter_status_values,
                filter_closures=filter_closure_values,
                filter_engineers=filter_engineer_values,
                branch_options=branch_options,
                engineer_options=engineer_options,
                closure_options=closure_options,
                status_columns=status_columns,
                apply_filters=apply_filters,
                filtered_jobs=filtered_jobs,
                filter_query=filter_query,
            )

        except db_error as e:
            _flash_internal_error("Error loading filter page", e)
            return redirect("/dashboard")

        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    @app.route("/dashboard")
    def dashboard():

        if "username" not in session:
            return redirect("/login")

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            branch = session.get("branch")
            role = session.get("role")
            selected_dashboard_branch, dashboard_branch_options = _resolve_dashboard_branch_scope(cursor, role)
            dashboard_scope_branch = selected_dashboard_branch or (branch or "")
            can_switch_dashboard_branch = _can_switch_dashboard_branch(role)
            current_username = (session.get("username") or "").strip()
            dashboard_user = {"username": current_username, "profile_picture": ""}

            if current_username:
                cursor.execute(
                    "SELECT username, profile_picture FROM users WHERE username=%s",
                    (current_username,),
                )
                fetched_dashboard_user = cursor.fetchone() or {}
                dashboard_user.update({
                    "username": fetched_dashboard_user.get("username") or current_username,
                    "profile_picture": fetched_dashboard_user.get("profile_picture") or "",
                })

            dashboard_args = request.args.copy()
            if can_switch_dashboard_branch:
                dashboard_args.setlist("filter_branch", [])

            dashboard_filters = build_dashboard_filters(dashboard_args, role, dashboard_scope_branch)
            scope_sql = dashboard_filters["where_sql"]
            params = dashboard_filters["params"]

            from_date = dashboard_filters["from_date"]
            to_date = dashboard_filters["to_date"]
            date_field_filter = dashboard_filters["date_field"]
            filter_branch = dashboard_filters["filter_branch"]
            filter_status = dashboard_filters["filter_status"]
            filter_closure = dashboard_filters["filter_closure"]
            filter_engineer = dashboard_filters["filter_engineer"]

            branch_options = [option for option in dashboard_branch_options if str(option).upper() != "ALL"] if can_switch_dashboard_branch else []

            cursor.execute("SELECT DISTINCT assigned_engineer FROM jobs WHERE assigned_engineer IS NOT NULL AND assigned_engineer <> '' ORDER BY assigned_engineer")
            engineer_options = [r["assigned_engineer"] for r in cursor.fetchall()]

            cursor.execute("SELECT DISTINCT closure_status FROM jobs WHERE closure_status IS NOT NULL AND closure_status <> '' ORDER BY closure_status")
            closure_options = [r["closure_status"] for r in cursor.fetchall()]

            active_scope_clause = "(closure_status IS NULL OR closure_status='') AND status <> 'Closed'"
            non_closed_scope_clause = "(status IS NULL OR status <> 'Closed')"
            completed_waiting_clause = "COALESCE(TRIM(status), '') IN ('Ready-Waiting for Customer', 'Non-Repairable Waiting for Customer')"
            pending_jobs_clause = "COALESCE(TRIM(status), '') NOT IN ('Ready-Waiting for Customer', 'Non-Repairable Waiting for Customer')"
            selected_jobs_branch = "" if selected_dashboard_branch == "ALL" else selected_dashboard_branch

            def build_jobs_url(view_name, extra_params=None):
                query = {"view": view_name}
                if selected_jobs_branch:
                    query["branch_name"] = selected_jobs_branch
                if extra_params:
                    query.update(extra_params)
                return _build_url("/jobs", query)

            def build_syscare_url(extra_params=None):
                query = {}
                if selected_jobs_branch:
                    query["branch"] = selected_jobs_branch
                if extra_params:
                    query.update(extra_params)
                return _build_url("/syscare", query)

            def build_revenue_url(extra_params=None):
                query = {}
                if selected_jobs_branch:
                    query["filter_branch"] = selected_jobs_branch
                if extra_params:
                    query.update(extra_params)
                return _build_url("/revenue-dashboard", query)

            onsite_alert_payload = _build_onsite_dashboard_alert_payload()
            onsite_dashboard_alert_count = onsite_alert_payload["onsite_dashboard_alert_count"]
            onsite_dashboard_alert_status = onsite_alert_payload["onsite_dashboard_alert_status"]
            onsite_dashboard_alert_label = onsite_alert_payload["onsite_dashboard_alert_label"]
            onsite_dashboard_url = onsite_alert_payload["onsite_dashboard_url"]

            cursor.execute(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN {non_closed_scope_clause} THEN 1 ELSE 0 END), 0) AS total_cases,
                    COALESCE(SUM(CASE WHEN ((closure_status IS NOT NULL AND closure_status <> '') OR status='Closed') THEN 1 ELSE 0 END), 0) AS closed_cases,
                    COALESCE(SUM(CASE WHEN {non_closed_scope_clause} AND {pending_jobs_clause} THEN 1 ELSE 0 END), 0) AS pending_jobs,
                    COALESCE(SUM(CASE WHEN status='Open' AND (closure_status IS NULL OR closure_status='') THEN 1 ELSE 0 END), 0) AS open_cases,
                    COALESCE(SUM(CASE WHEN status='Open' AND (closure_status IS NULL OR closure_status='') AND created_at IS NOT NULL AND TIMESTAMPDIFF(DAY, created_at, NOW()) > 2 THEN 1 ELSE 0 END), 0) AS open_cases_over_2_days,
                    COALESCE(SUM(CASE WHEN {non_closed_scope_clause} AND {completed_waiting_clause} THEN 1 ELSE 0 END), 0) AS completed_jobs
                FROM jobs
                WHERE {scope_sql}
                """,
                params,
            )
            kpi_row = cursor.fetchone() or {}
            total_cases = int(kpi_row.get("total_cases") or 0)
            closed_cases = int(kpi_row.get("closed_cases") or 0)
            pending_jobs = int(kpi_row.get("pending_jobs") or 0)
            open_cases = int(kpi_row.get("open_cases") or 0)
            open_cases_over_2_days = int(kpi_row.get("open_cases_over_2_days") or 0)
            completed_jobs = int(kpi_row.get("completed_jobs") or 0)

            cursor.execute(
                f"""
                SELECT COUNT(DISTINCT j.id) AS pending_spare_billing
                FROM jobs j
                WHERE {scope_sql}
                    AND EXISTS (SELECT 1 FROM used_spares us WHERE us.job_id = j.id)
                    AND (j.spares_invoice_no IS NULL OR TRIM(j.spares_invoice_no) = '')
                    AND NOT ((j.closure_status IS NOT NULL AND j.closure_status <> '') OR j.status='Closed')
                """,
                params,
            )
            spare_billing_row = cursor.fetchone() or {}
            pending_spare_billing = int(spare_billing_row.get("pending_spare_billing") or 0)

            cursor.execute(
                f"""
                SELECT COUNT(DISTINCT jobs.id) AS active_transfer_jobs
                FROM jobs
                WHERE {scope_sql}
                  AND EXISTS (
                      SELECT 1
                      FROM job_service_transfers transfer
                      WHERE transfer.job_id = jobs.id
                        AND transfer.status IN ('Sent', 'In Service', 'Completed')
                  )
                """,
                params,
            )
            active_transfer_row = cursor.fetchone() or {}
            active_transfer_jobs = int(active_transfer_row.get("active_transfer_jobs") or 0)

            today = business_now_naive().date()
            first_day = today.replace(day=1)
            chart_from_date = normalize_date_input(request.args.get("chart_from_date", "")) or first_day.strftime("%Y-%m-%d")
            chart_to_date = normalize_date_input(request.args.get("chart_to_date", "")) or today.strftime("%Y-%m-%d")

            chart_params_common = list(params)

            cursor.execute(
                f"""
                SELECT
                    SUM(CASE WHEN LOWER(COALESCE(closure_status,'')) LIKE 'closed success%' THEN 1 ELSE 0 END) AS success_count,
                    SUM(CASE WHEN LOWER(COALESCE(closure_status,'')) LIKE 'closed failed%' THEN 1 ELSE 0 END) AS failed_count
                FROM jobs
                WHERE {scope_sql}
                  AND closure_date >= %s
                  AND closure_date <= %s
                """,
                tuple(chart_params_common + [chart_from_date + " 00:00:00", chart_to_date + " 23:59:59"]),
            )
            closure_row = cursor.fetchone() or {}
            closed_success_count = int(closure_row.get("success_count") or 0)
            closed_failed_count = int(closure_row.get("failed_count") or 0)

            cursor.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(device), ''), 'Unknown') AS label, COUNT(*) AS c
                FROM jobs
                WHERE {scope_sql}
                  AND created_at >= %s
                  AND created_at <= %s
                GROUP BY COALESCE(NULLIF(TRIM(device), ''), 'Unknown')
                ORDER BY c DESC
                """,
                tuple(chart_params_common + [chart_from_date + " 00:00:00", chart_to_date + " 23:59:59"]),
            )
            new_calls_rows = cursor.fetchall()
            new_calls_labels = [r.get("label") or "Unknown" for r in new_calls_rows]
            new_calls_counts = [int(r.get("c") or 0) for r in new_calls_rows]

            cursor.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(call_type), ''), 'Unknown') AS label, COUNT(*) AS c
                FROM jobs
                WHERE {scope_sql}
                  AND created_at >= %s
                  AND created_at <= %s
                GROUP BY COALESCE(NULLIF(TRIM(call_type), ''), 'Unknown')
                ORDER BY c DESC
                """,
                tuple(chart_params_common + [chart_from_date + " 00:00:00", chart_to_date + " 23:59:59"]),
            )
            call_type_rows = cursor.fetchall()
            official_call_types = [
                "AMC Visit",
                "Carry In",
                "Installation",
                "Onsite Visit",
                "Pickup Request",
                "Remote Support",
            ]
            official_map = {v.upper(): v for v in official_call_types}
            type_counts = {v: 0 for v in official_call_types}
            other_counts = {}

            for r in call_type_rows:
                raw_label = (r.get("label") or "").strip()
                cnt = int(r.get("c") or 0)
                if not raw_label or raw_label == "-- Select Type --":
                    continue

                key = raw_label.upper()
                if key in official_map:
                    type_counts[official_map[key]] += cnt
                else:
                    other_counts[raw_label] = other_counts.get(raw_label, 0) + cnt

            call_type_labels = [k for k in official_call_types if type_counts[k] > 0]
            call_type_counts = [type_counts[k] for k in call_type_labels]

            for extra_label in sorted(other_counts.keys()):
                call_type_labels.append(extra_label)
                call_type_counts.append(other_counts[extra_label])

            sales_revenue_total = 0.0
            service_revenue_total = 0.0
            total_target = 0.0

            if selected_dashboard_branch == "ALL":
                revenue_target_branch = "All Branches"
            else:
                revenue_target_branch = selected_dashboard_branch or "All Branches"

            try:
                revenue_where = ["entry_date >= %s", "entry_date <= %s"]
                revenue_params = [chart_from_date, chart_to_date]

                if selected_jobs_branch:
                    revenue_where.append("branch_name=%s")
                    revenue_params.append(selected_jobs_branch)

                cursor.execute(
                    f"""
                    SELECT
                        COALESCE(SUM(sales_profit), 0) AS sales_total,
                        COALESCE(SUM(service_charges), 0) AS service_total
                    FROM branch_revenue_entries
                    WHERE {' AND '.join(revenue_where)}
                    """,
                    tuple(revenue_params),
                )
                revenue_sum_row = cursor.fetchone() or {}
                sales_revenue_total = float(revenue_sum_row.get("sales_total") or 0)
                service_revenue_total = float(revenue_sum_row.get("service_total") or 0)

                if not selected_jobs_branch:
                    cursor.execute(
                        """
                        SELECT COALESCE(SUM(COALESCE(total_target, COALESCE(sales_target,0) + COALESCE(service_target,0))), 0) AS t
                        FROM branch_revenue_targets
                        WHERE UPPER(branch_name) <> 'ALL'
                        """
                    )
                    trow = cursor.fetchone() or {}
                    total_target = float(trow.get("t") or 0)
                    if total_target <= 0:
                        revenue_target = get_branch_revenue_target(cursor, "ALL")
                        total_target = float(revenue_target.get("total_target") or 0)
                else:
                    revenue_target = get_branch_revenue_target(cursor, revenue_target_branch)
                    total_target = float(revenue_target.get("total_target") or 0)

            except Exception:
                sales_revenue_total = 0.0
                service_revenue_total = 0.0
                total_target = 0.0
                if not revenue_target_branch:
                    revenue_target_branch = "ALL"

            achieved_total = service_revenue_total + sales_revenue_total
            total_target_remaining = max(total_target - achieved_total, 0)
            achieved_percentage = 0.0
            revenue_advice = "Target not set"
            revenue_advice_class = "secondary"

            if total_target > 0:
                achieved_percentage = (achieved_total / total_target) * 100
                if achieved_percentage >= 100:
                    revenue_advice = "Target achieved. Maintain momentum."
                    revenue_advice_class = "success"
                elif achieved_percentage >= 85:
                    revenue_advice = "Close to target. Push high-value follow-ups."
                    revenue_advice_class = "primary"
                elif achieved_percentage >= 60:
                    revenue_advice = "On track, but service and sales need a stronger push."
                    revenue_advice_class = "warning"
                else:
                    revenue_advice = "Below target. Review branch pipeline and pending closures."
                    revenue_advice_class = "danger"

            syscare_target = 30
            syscare_achieved = 0
            syscare_remaining = syscare_target
            syscare_percentage = 0.0
            syscare_advice = "No SYSCARE records in selected period."
            syscare_advice_class = "secondary"

            _syscare_branch_filter = selected_jobs_branch or None

            # Load SYSCARE target dynamically from branch targets table
            try:
                if _syscare_branch_filter:
                    cursor.execute(
                        "SELECT COALESCE(SUM(monthly_target), 0) AS t FROM syscare_branch_targets WHERE branch_name = %s",
                        (_syscare_branch_filter,),
                    )
                else:
                    cursor.execute("SELECT COALESCE(SUM(monthly_target), 0) AS t FROM syscare_branch_targets")
                _st_row = cursor.fetchone() or {}
                _computed_target = int(_st_row.get("t") or 0)
                if _computed_target > 0:
                    syscare_target = _computed_target
            except Exception:
                pass  # table may not exist yet; keep default 30

            try:
                syscare_where = ["record_date >= %s", "record_date <= %s"]
                syscare_params = [chart_from_date, chart_to_date]

                if _syscare_branch_filter:
                    syscare_where.append("branch_name=%s")
                    syscare_params.append(_syscare_branch_filter)

                cursor.execute(
                    f"""
                    SELECT COUNT(*) AS c
                    FROM syscare_memberships
                    WHERE {' AND '.join(syscare_where)}
                    """,
                    tuple(syscare_params),
                )
                syscare_row = cursor.fetchone() or {}
                syscare_achieved = int(syscare_row.get("c") or 0)
            except Exception:
                syscare_achieved = 0

            syscare_remaining = max(syscare_target - syscare_achieved, 0)
            if syscare_target > 0:
                syscare_percentage = (syscare_achieved / syscare_target) * 100
                if syscare_percentage >= 100:
                    syscare_advice = "SYSCARE target achieved for this period."
                    syscare_advice_class = "success"
                elif syscare_percentage >= 75:
                    syscare_advice = "Close to SYSCARE target. Push pending warm leads."
                    syscare_advice_class = "primary"
                elif syscare_percentage >= 50:
                    syscare_advice = "SYSCARE is midway. Increase daily follow-up conversion."
                    syscare_advice_class = "warning"
                else:
                    syscare_advice = "SYSCARE below plan. Focus on branch-wise conversion and renewals."
                    syscare_advice_class = "danger"

            closure_header_query = {
                "view": "closed",
                "chart_mode": "closed",
                "chart_from_date": chart_from_date,
                "chart_to_date": chart_to_date,
            }
            if selected_jobs_branch:
                closure_header_query["branch_name"] = selected_jobs_branch
            if filter_status:
                closure_header_query["status"] = filter_status
            closure_header_url = _build_url("/jobs", closure_header_query)

            syscare_header_query = {}
            if chart_from_date and chart_to_date and len(chart_from_date) >= 7 and len(chart_to_date) >= 7:
                if chart_from_date[:7] == chart_to_date[:7]:
                    syscare_header_query["month"] = chart_from_date[:7]
            elif chart_to_date and len(chart_to_date) >= 7:
                syscare_header_query["month"] = chart_to_date[:7]
            elif chart_from_date and len(chart_from_date) >= 7:
                syscare_header_query["month"] = chart_from_date[:7]
            if selected_jobs_branch:
                syscare_header_query["branch"] = selected_jobs_branch
            syscare_header_url = _build_url("/syscare", syscare_header_query)

            revenue_header_query = {}
            if selected_jobs_branch:
                revenue_header_query["filter_branch"] = selected_jobs_branch
            revenue_header_url = _build_url("/revenue-dashboard", revenue_header_query)

            cashflow_scope_branch = selected_jobs_branch or ""
            cashflow_dashboard = {
                "today_date": business_now_naive().strftime("%Y-%m-%d"),
                "cash_total": 0.0,
                "card_total": 0.0,
                "upi_total": 0.0,
                "total_collected": 0.0,
                "available_cash": 0.0,
                "pending_transfers": 0.0,
                "branch_rows": [],
                "has_data": False,
            }
            try:
                cashflow_dashboard = get_cashflow_dashboard_snapshot(cursor, cashflow_scope_branch)
            except Exception:
                app.logger.exception("Failed to load cashflow dashboard snapshot")

            cashflow_header_query = {
                "from_date": cashflow_dashboard.get("today_date") or business_now_naive().strftime("%Y-%m-%d"),
                "to_date": cashflow_dashboard.get("today_date") or business_now_naive().strftime("%Y-%m-%d"),
            }
            if selected_jobs_branch:
                cashflow_header_query["filter_branch"] = selected_jobs_branch
            cashflow_header_url = _build_url("/cashflow", cashflow_header_query)
            cashflow_review_query = {"view": "transfer-review"}
            if selected_jobs_branch:
                cashflow_review_query["filter_branch"] = selected_jobs_branch
            cashflow_review_url = _build_url("/cashflow", cashflow_review_query)

            report_data = _get_dashboard_report_data(cursor, scope_sql, params)

            total_cases_url = build_jobs_url("ongoing")
            pending_jobs_url = build_jobs_url("pending")
            open_cases_url = build_jobs_url("open")
            completed_jobs_url = build_jobs_url("completed")
            shortcut_closed_jobs_url = build_jobs_url("closed")
            shortcut_all_jobs_url = build_jobs_url("all")
            pending_spare_billing_url = _build_url(
                "/used-spares",
                {
                    "view": "pending",
                    "filter_branch": selected_jobs_branch or None,
                },
            )
            active_transfer_jobs_url = build_jobs_url(
                "active",
                {
                    "transfer_filter": "active",
                },
            )
            closed_success_url = build_jobs_url(
                "closed",
                {
                    "closure_result": "success",
                    "chart_mode": "closed",
                    "chart_from_date": chart_from_date,
                    "chart_to_date": chart_to_date,
                },
            )
            closed_failed_url = build_jobs_url(
                "closed",
                {
                    "closure_result": "failed",
                    "chart_mode": "closed",
                    "chart_from_date": chart_from_date,
                    "chart_to_date": chart_to_date,
                },
            )
            new_call_links = [
                build_jobs_url(
                    "all",
                    {
                        "device_filter": label,
                        "chart_mode": "created",
                        "chart_from_date": chart_from_date,
                        "chart_to_date": chart_to_date,
                    },
                )
                for label in new_calls_labels
            ]
            call_type_links = [
                build_jobs_url(
                    "all",
                    {
                        "call_type_filter": label,
                        "chart_mode": "created",
                        "chart_from_date": chart_from_date,
                        "chart_to_date": chart_to_date,
                    },
                )
                for label in call_type_labels
            ]
            dashboard_page_data = {
                "closedResult": {
                    "labels": ["Closed Success", "Closed Failed"],
                    "counts": [closed_success_count, closed_failed_count],
                    "links": [closed_success_url, closed_failed_url],
                },
                "newCalls": {
                    "labels": new_calls_labels,
                    "counts": new_calls_counts,
                    "links": new_call_links,
                },
                "callTypes": {
                    "labels": call_type_labels,
                    "counts": call_type_counts,
                    "links": call_type_links,
                },
                "syscare": {
                    "labels": ["Achieved", "Balance"],
                    "counts": [syscare_achieved, syscare_remaining],
                    "links": [syscare_header_url, syscare_header_url],
                },
                "revenue": {
                    "labels": ["Service Charges", "Sales Revenue"],
                    "counts": [service_revenue_total, sales_revenue_total],
                    "links": [revenue_header_url, revenue_header_url],
                },
            }
            scope_label = selected_dashboard_branch if selected_dashboard_branch != "ALL" else "All Branches"

            template_context = {
                "branch": branch,
                "total_cases": total_cases,
                "pending_jobs": pending_jobs,
                "closed_cases": closed_cases,
                "open_cases": open_cases,
                "open_cases_over_2_days": open_cases_over_2_days,
                "completed_jobs": completed_jobs,
                "pending_spare_billing": pending_spare_billing,
                "active_transfer_jobs": active_transfer_jobs,
                "onsite_dashboard_alert_count": onsite_dashboard_alert_count,
                "onsite_dashboard_alert_status": onsite_dashboard_alert_status,
                "onsite_dashboard_alert_label": onsite_dashboard_alert_label,
                "onsite_dashboard_url": onsite_dashboard_url,
                "scope_label": scope_label,
                "can_switch_dashboard_branch": can_switch_dashboard_branch,
                "selected_dashboard_branch": selected_dashboard_branch,
                "selected_jobs_branch": selected_jobs_branch,
                "dashboard_branch_options": dashboard_branch_options,
                "status_columns": report_data["status_columns"],
                "branch_wise_rows": report_data["branch_wise_rows"],
                "branch_wise_totals": report_data["branch_wise_totals"],
                "branch_wise_grand_total": report_data["branch_wise_grand_total"],
                "branch_report_counts": report_data["branch_report_counts"],
                "branch_report_total": report_data["branch_report_total"],
                "ageing_rows": report_data["ageing_rows"],
                "age_buckets": report_data["age_buckets"],
                "age_bucket_ranges": report_data["age_bucket_ranges"],
                "ageing_totals_by_bucket": report_data["ageing_totals_by_bucket"],
                "ageing_grand_total": report_data["ageing_grand_total"],
                "from_date": from_date,
                "to_date": to_date,
                "date_field_filter": date_field_filter,
                "filter_branch": filter_branch,
                "filter_status": filter_status,
                "filter_closure": filter_closure,
                "filter_engineer": filter_engineer,
                "open_report": (request.args.get("open_report") or "").strip(),
                "branch_options": branch_options,
                "engineer_options": engineer_options,
                "closure_options": closure_options,
                "chart_from_date": chart_from_date,
                "chart_to_date": chart_to_date,
                "closed_success_count": closed_success_count,
                "closed_failed_count": closed_failed_count,
                "total_cases_url": total_cases_url,
                "pending_jobs_url": pending_jobs_url,
                "open_cases_url": open_cases_url,
                "completed_jobs_url": completed_jobs_url,
                "pending_spare_billing_url": pending_spare_billing_url,
                "active_transfer_jobs_url": active_transfer_jobs_url,
                "shortcut_closed_jobs_url": shortcut_closed_jobs_url,
                "shortcut_all_jobs_url": shortcut_all_jobs_url,
                "closed_success_url": closed_success_url,
                "closed_failed_url": closed_failed_url,
                "closure_header_url": closure_header_url,
                "new_calls_labels": new_calls_labels,
                "new_calls_counts": new_calls_counts,
                "call_type_labels": call_type_labels,
                "call_type_counts": call_type_counts,
                "service_revenue_total": service_revenue_total,
                "sales_revenue_total": sales_revenue_total,
                "revenue_header_url": revenue_header_url,
                "revenue_target_branch": revenue_target_branch,
                "total_target": total_target,
                "achieved_total": achieved_total,
                "total_target_remaining": total_target_remaining,
                "achieved_percentage": achieved_percentage,
                "revenue_advice": revenue_advice,
                "revenue_advice_class": revenue_advice_class,
                "syscare_target": syscare_target,
                "syscare_achieved": syscare_achieved,
                "syscare_remaining": syscare_remaining,
                "syscare_percentage": syscare_percentage,
                "syscare_header_url": syscare_header_url,
                "syscare_advice": syscare_advice,
                "syscare_advice_class": syscare_advice_class,
                "cashflow_header_url": cashflow_header_url,
                "cashflow_today_date": cashflow_dashboard.get("today_date"),
                "cashflow_today_cash": cashflow_dashboard.get("cash_total", 0.0),
                "cashflow_today_card": cashflow_dashboard.get("card_total", 0.0),
                "cashflow_today_upi": cashflow_dashboard.get("upi_total", 0.0),
                "cashflow_today_total": cashflow_dashboard.get("total_collected", 0.0),
                "cashflow_available_cash": cashflow_dashboard.get("available_cash", 0.0),
                "cashflow_pending_transfers": cashflow_dashboard.get("pending_transfers", 0.0),
                "cashflow_pending_transfer_count": cashflow_dashboard.get("pending_transfer_count", 0),
                "cashflow_review_url": cashflow_review_url,
                "cashflow_today_branch_rows": cashflow_dashboard.get("branch_rows", []),
                "cashflow_has_data": cashflow_dashboard.get("has_data", False),
                "dashboard_user": dashboard_user,
                "dashboard_page_data": dashboard_page_data,
            }

            if request.args.get("partial", "").strip() == "1":
                return render_template("_dashboard_content.html", **template_context)

            return render_template("dashboard.html", **template_context)

        except db_error as e:
            _flash_internal_error("Error loading dashboard", e)
            return redirect("/jobs")

        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    @app.route("/settings")
    def settings():

        if "username" not in session:
            return redirect("/login")

        if session.get("role") != "super_admin":
            return "Access Denied"

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT * FROM dropdown_options ORDER BY type, `order`, value")
        rows = cursor.fetchall()

        grouped = {}

        for r in rows:
            grouped.setdefault(r["type"], []).append(r)

        cursor.execute("SELECT id, username, role, password FROM users ORDER BY id ASC")
        user_rows = cursor.fetchall()
        users = []
        legacy_password_users = []

        for row in user_rows:
            user_entry = {
                "id": row.get("id"),
                "username": row.get("username"),
                "role": row.get("role"),
                "requires_password_reset": has_legacy_password(row.get("password")),
            }
            users.append(user_entry)
            if user_entry["requires_password_reset"]:
                legacy_password_users.append(user_entry)

        cursor.execute("SELECT id, username, branch_name FROM user_branches ORDER BY id ASC")
        user_branches = cursor.fetchall()

        cursor.execute("SELECT * FROM branch_revenue_targets ORDER BY branch_name ASC")
        revenue_targets = cursor.fetchall()

        for row in revenue_targets:
            base_total = row.get("total_target")
            if base_total is None:
                base_total = float(row.get("sales_target") or 0) + float(row.get("service_target") or 0)
            row["effective_target"] = float(base_total or 0)

        cursor.close()
        db.close()

        return render_template(
            "settings.html",
            grouped=grouped,
            users=users,
            legacy_password_users=legacy_password_users,
            user_branches=user_branches,
            branch_list=default_branches,
            revenue_targets=revenue_targets,
        )
