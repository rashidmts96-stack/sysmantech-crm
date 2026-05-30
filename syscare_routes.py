import base64
from datetime import date, datetime, timedelta
import csv
import io
import os
import re

from flask import flash, redirect, render_template, request, session
from time_utils import business_now_naive
from werkzeug.utils import secure_filename

try:
    import qrcode
except ImportError:
    qrcode = None


def register_syscare_routes(app, deps):

    @app.route("/syscare-export", methods=["GET"])
    def syscare_export():
        if "username" not in session:
            return redirect("/login")

        role = session.get("role")
        session_branch = (session.get("branch") or "").strip()

        try:
            branch_scope = _get_branch_scope(role, session_branch)
        except PermissionError:
            flash("Invalid branch scope", "danger")
            return redirect("/syscare")

        selected_month = (request.args.get("month") or "").strip()
        selected_month, month_start, month_end = _month_start_end(selected_month)
        search_q = (request.args.get("q") or "").strip()
        filter_branch_rec = (request.args.get("branch") or "").strip()
        filter_incharge_rec = (request.args.get("incharge") or "").strip()

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            membership_cols = _get_syscare_membership_columns(cursor)
            has_is_manual = "is_manual" in membership_cols

            records_where = "record_date >= %s AND record_date <= %s"
            records_params = [month_start, month_end]
            if branch_scope:
                records_where += " AND branch_name = %s"
                records_params.append(branch_scope)
            elif filter_branch_rec:
                records_where += " AND branch_name = %s"
                records_params.append(filter_branch_rec)
            if filter_incharge_rec:
                records_where += " AND incharge = %s"
                records_params.append(filter_incharge_rec)
            if search_q:
                search_fields = ["customer_name", "syscare_id", "contact_number"]
                if "model_serial" in membership_cols:
                    search_fields.append("model_serial")
                if "product_model" in membership_cols:
                    search_fields.append("product_model")
                if "serial_number" in membership_cols:
                    search_fields.append("serial_number")
                like = f"%{search_q}%"
                records_where += " AND (" + " OR ".join(f"{field} LIKE %s" for field in search_fields) + ")"
                records_params.extend([like] * len(search_fields))

            select_cols = [
                "record_date", "syscare_id", "customer_name", "contact_number",
                "branch_name", "incharge", "amount", "expiry_date"
            ]
            if "product_model" in membership_cols:
                select_cols.append("product_model")
            if "serial_number" in membership_cols:
                select_cols.append("serial_number")
            if "model_serial" in membership_cols:
                select_cols.append("model_serial")
            if has_is_manual:
                select_cols.append("is_manual")

            select_sql = f"SELECT {', '.join(select_cols)} FROM syscare_memberships WHERE {records_where} ORDER BY record_date DESC, id DESC"
            cursor.execute(select_sql, tuple(records_params))
            rows = cursor.fetchall()

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=select_cols)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

            output.seek(0)
            from flask import Response
            filename = f"syscare_export_{selected_month or 'all'}.csv"

            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                },
            )
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    get_db = deps["get_db"]
    db_error = deps["Error"]
    normalize_date_input = deps["_normalize_date_input"]
    next_sequence_value = deps["_next_sequence_value"]
    load_workbook = deps.get("load_workbook")
    syscare_optional_columns_sql = (
        "ALTER TABLE syscare_memberships ADD COLUMN address TEXT NULL",
        "ALTER TABLE syscare_memberships ADD COLUMN mail_id VARCHAR(255) NULL",
        "ALTER TABLE syscare_memberships ADD COLUMN model_serial VARCHAR(255) NULL",
        "ALTER TABLE syscare_memberships ADD COLUMN product_model VARCHAR(255) NULL",
        "ALTER TABLE syscare_memberships ADD COLUMN serial_number VARCHAR(255) NULL",
        "ALTER TABLE syscare_memberships ADD COLUMN assigned_engineer VARCHAR(255) NULL",
        "ALTER TABLE syscare_memberships ADD COLUMN is_manual TINYINT(1) NOT NULL DEFAULT 0",
    )
    syscare_membership_columns_cache = None

    def _flash_internal_error(user_message, exc=None):
        if exc is not None:
            app.logger.exception(user_message)
        flash(user_message, "danger")

    def _build_qr_data_uri(content):
        if not content or qrcode is None:
            return ""

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=1,
        )
        qr.add_data(content)
        qr.make(fit=True)

        image = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _has_global_scope(role, session_branch):
        return role in ["super_admin", "admin"] and (session_branch or "").strip().upper() == "ALL"

    def _get_branch_scope(role, session_branch):
        normalized_branch = (session_branch or "").strip()
        if _has_global_scope(role, normalized_branch):
            return None
        if not normalized_branch or normalized_branch.upper() == "ALL":
            raise PermissionError("Invalid branch scope")
        return normalized_branch

    def _header_key(text):
        return re.sub(r"[^a-z0-9]+", "", str(text or "").strip().lower())

    def _build_header_index(headers):
        header_map = {}
        for idx, header in enumerate(headers or []):
            key = _header_key(header)
            if key and key not in header_map:
                header_map[key] = idx
        return header_map

    def _pick_index(header_map, aliases):
        for alias in aliases:
            if alias in header_map:
                return header_map[alias]
        return None

    def _get_cell(row, idx):
        if idx is None:
            return ""
        if idx >= len(row):
            return ""
        v = row[idx]
        return "" if v is None else v

    def _parse_date_any(value):
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        if isinstance(value, (int, float)):
            # Excel serial date support
            if value > 0:
                try:
                    base = datetime(1899, 12, 30)
                    return (base + timedelta(days=float(value))).date()
                except Exception:
                    return None

        s = str(value).strip()
        if not s:
            return None

        normalized = normalize_date_input(s)
        if normalized:
            return datetime.strptime(normalized, "%Y-%m-%d").date()

        for fmt in ["%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y"]:
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue

        return None

    def _parse_money(value):
        s = str(value or "").strip()
        if not s:
            return 0.0
        s = s.replace(",", "")
        s = re.sub(r"[^0-9.\-]", "", s)
        if not s or s in ["-", ".", "-."]:
            return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0

    def _parse_int(value):
        try:
            return int(float(str(value or "0").strip() or 0))
        except (ValueError, TypeError):
            return 0

    def _days_until_expiry(value):
        expiry = _parse_date_any(value)
        if not expiry:
            return None
        return (expiry - date.today()).days

    def _format_display_date(value):
        parsed = _parse_date_any(value)
        if parsed:
            return parsed.strftime("%d-%m-%Y")
        text = str(value or "").strip()
        return text or "-"

    def _split_model_serial(value):
        text = str(value or "").strip()
        if not text:
            return "", ""

        if " / " in text:
            parts = text.split(" / ", 1)
            return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""

        if "SN:" in text:
            parts = text.split("SN:", 1)
            model = parts[0].replace("/", " ").strip()
            serial = parts[1].strip() if len(parts) > 1 else ""
            return model, serial

        if "," in text:
            parts = text.split(",", 1)
            return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""

        return text, ""

    def _iter_syscare_upload_rows(uploaded_file):
        filename = secure_filename(uploaded_file.filename or "")
        ext = os.path.splitext(filename)[1].lower()

        aliases = {
            "record_date": ["date", "plandate"],
            "syscare_id": ["syscareid", "syscare", "id"],
            "customer_name": ["cusname", "customername", "name", "customer"],
            "contact_number": ["contactnumber", "contact", "mobile", "phonenumber"],
            "branch_name": ["branch", "branchname"],
            "incharge": ["incharge", "engineer", "staff"],
            "product_model": ["productmodel", "model", "devicemodel"],
            "serial_number": ["serialnumber", "serialno", "serial", "sn"],
            "model_serial": ["modelserial", "modelserialnumber"],
            "amount": ["amount", "planamount", "value"],
            "expiry_date": ["expirydate", "expiry", "validtill", "servicevalidtill"],
        }

        def _resolve_rows(rows_iter, header_map):
            idx_date = _pick_index(header_map, aliases["record_date"])
            idx_syscare_id = _pick_index(header_map, aliases["syscare_id"])
            idx_customer_name = _pick_index(header_map, aliases["customer_name"])
            idx_contact_number = _pick_index(header_map, aliases["contact_number"])
            idx_branch_name = _pick_index(header_map, aliases["branch_name"])
            idx_incharge = _pick_index(header_map, aliases["incharge"])
            idx_product_model = _pick_index(header_map, aliases["product_model"])
            idx_serial_number = _pick_index(header_map, aliases["serial_number"])
            idx_model_serial = _pick_index(header_map, aliases["model_serial"])
            idx_amount = _pick_index(header_map, aliases["amount"])
            idx_expiry_date = _pick_index(header_map, aliases["expiry_date"])

            if idx_date is None:
                raise ValueError("Missing required column: Date")
            if idx_syscare_id is None:
                raise ValueError("Missing required column: Syscare ID")

            for row_number, row in rows_iter:
                row = list(row) if not isinstance(row, list) else row
                record_date = _parse_date_any(_get_cell(row, idx_date))
                syscare_id = str(_get_cell(row, idx_syscare_id) or "").strip()
                product_model = str(_get_cell(row, idx_product_model) or "").strip()
                serial_number = str(_get_cell(row, idx_serial_number) or "").strip()
                model_serial = str(_get_cell(row, idx_model_serial) or "").strip()
                if (not product_model or not serial_number) and model_serial:
                    legacy_model, legacy_serial = _split_model_serial(model_serial)
                    if not product_model:
                        product_model = legacy_model
                    if not serial_number:
                        serial_number = legacy_serial
                model_serial = f"{product_model} / {serial_number}".strip(" /")

                if not record_date or not syscare_id:
                    yield row_number, None
                    continue

                yield row_number, {
                    "record_date": record_date.strftime("%Y-%m-%d"),
                    "syscare_id": syscare_id,
                    "customer_name": str(_get_cell(row, idx_customer_name) or "").strip(),
                    "contact_number": str(_get_cell(row, idx_contact_number) or "").strip(),
                    "branch_name": str(_get_cell(row, idx_branch_name) or "").strip(),
                    "incharge": str(_get_cell(row, idx_incharge) or "").strip(),
                    "model_serial": model_serial,
                    "product_model": product_model,
                    "serial_number": serial_number,
                    "amount": round(max(_parse_money(_get_cell(row, idx_amount)), 0), 2),
                    "expiry_date": (_parse_date_any(_get_cell(row, idx_expiry_date)) or None),
                }

        if ext == ".csv":
            raw_bytes = uploaded_file.stream.read()
            try:
                text = raw_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw_bytes.decode("utf-8", errors="ignore")
            reader = csv.reader(io.StringIO(text))
            headers = next(reader, None)
            if not headers:
                raise ValueError("The file is empty")
            header_map = _build_header_index(headers)
            yield from _resolve_rows(enumerate(reader, start=2), header_map)
            return

        if ext == ".xlsx":
            if load_workbook is None:
                raise ValueError("Excel needs openpyxl. Use CSV or install openpyxl.")
            workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
            try:
                sheet = workbook.active
                rows_iter = sheet.iter_rows(values_only=True)
                headers = next(rows_iter, None)
                if not headers:
                    raise ValueError("The file is empty")
                header_map = _build_header_index(headers)
                yield from _resolve_rows(enumerate(rows_iter, start=2), header_map)
            finally:
                workbook.close()
            return

        raise ValueError("Please upload .xlsx or .csv")

    def ensure_syscare_memberships_table():
        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS syscare_memberships (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    record_date DATE NOT NULL,
                    syscare_id VARCHAR(100) NOT NULL,
                    customer_name VARCHAR(255) NULL,
                    contact_number VARCHAR(50) NULL,
                    branch_name VARCHAR(255) NULL,
                    incharge VARCHAR(255) NULL,
                    amount DECIMAL(12,2) NOT NULL DEFAULT 0,
                    expiry_date DATE NULL,
                    uploaded_by VARCHAR(255) NULL,
                    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_syscare_id (syscare_id),
                    INDEX idx_syscare_record_date (record_date),
                    INDEX idx_syscare_branch (branch_name)
                )
                """
            )
            db.commit()
            for col_sql in syscare_optional_columns_sql:
                try:
                    cursor.execute(col_sql)
                    db.commit()
                except Exception:
                    pass
        except db_error:
            pass
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    def _month_start_end(month_text):
        if not month_text or not re.match(r"^\d{4}-\d{2}$", month_text):
            now = business_now_naive()
            month_text = f"{now.year:04d}-{now.month:02d}"

        year = int(month_text[:4])
        month = int(month_text[5:7])
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        return month_text, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    def _build_syscare_monthly_chart_context(cursor, selected_month, branch_scope, monthly_target, month_count=12):
        selected_month, _, anchor_month_end = _month_start_end(selected_month)
        anchor_year = int(selected_month[:4])
        anchor_month = int(selected_month[5:7])
        anchor_index = anchor_year * 12 + anchor_month - 1
        window_start_index = anchor_index - (month_count - 1)

        first_record_sql = """
            SELECT MIN(record_date) AS first_record_date
            FROM syscare_memberships
            WHERE record_date IS NOT NULL AND record_date <= %s
        """
        first_record_params = [anchor_month_end]
        if branch_scope:
            first_record_sql += " AND branch_name = %s"
            first_record_params.append(branch_scope)

        cursor.execute(first_record_sql, tuple(first_record_params))
        first_record_row = cursor.fetchone() or {}
        first_record_date = first_record_row.get("first_record_date")

        if isinstance(first_record_date, str) and first_record_date:
            first_record_date = datetime.strptime(first_record_date, "%Y-%m-%d").date()

        if first_record_date:
            first_month_index = first_record_date.year * 12 + first_record_date.month - 1
            start_index = max(window_start_index, min(first_month_index, anchor_index))
        else:
            start_index = anchor_index

        month_points = []
        for absolute_month_index in range(start_index, anchor_index + 1):
            year_num = absolute_month_index // 12
            month_num = absolute_month_index % 12 + 1
            month_start_date = date(year_num, month_num, 1)
            if month_num == 12:
                month_end_date = date(year_num + 1, 1, 1) - timedelta(days=1)
            else:
                month_end_date = date(year_num, month_num + 1, 1) - timedelta(days=1)

            month_points.append(
                {
                    "key": f"{year_num:04d}-{month_num:02d}",
                    "start": month_start_date,
                    "end": month_end_date,
                }
            )

        achieved_sql = """
            SELECT YEAR(record_date) AS year_num, MONTH(record_date) AS month_num, COUNT(*) AS achieved
            FROM syscare_memberships
            WHERE record_date >= %s AND record_date <= %s
        """
        achieved_params = [
            month_points[0]["start"].strftime("%Y-%m-%d"),
            month_points[-1]["end"].strftime("%Y-%m-%d"),
        ]
        if branch_scope:
            achieved_sql += " AND branch_name = %s"
            achieved_params.append(branch_scope)
        achieved_sql += " GROUP BY YEAR(record_date), MONTH(record_date) ORDER BY YEAR(record_date), MONTH(record_date)"

        cursor.execute(achieved_sql, tuple(achieved_params))
        achieved_rows = cursor.fetchall()
        achieved_map = {
            f"{int(row.get('year_num') or 0):04d}-{int(row.get('month_num') or 0):02d}": int(row.get("achieved") or 0)
            for row in achieved_rows
        }

        year_count = len({point["start"].year for point in month_points})
        labels = []
        full_labels = []
        achieved_series = []
        target_series = []
        balance_series = []

        for point in month_points:
            label_date = point["start"]
            labels.append(label_date.strftime("%b %Y") if year_count > 1 else label_date.strftime("%b"))
            full_labels.append(label_date.strftime("%B %Y"))
            achieved_value = achieved_map.get(point["key"], 0)
            target_value = int(monthly_target or 0)
            achieved_series.append(achieved_value)
            target_series.append(target_value)
            balance_series.append(max(target_value - achieved_value, 0))

        scope_label = branch_scope or "All Branches"
        return {
            "syscare_chart_labels": labels,
            "syscare_chart_full_labels": full_labels,
            "syscare_chart_achieved_series": achieved_series,
            "syscare_chart_target_series": target_series,
            "syscare_chart_balance_series": balance_series,
            "syscare_chart_scope_label": scope_label,
            "syscare_chart_start_label": month_points[0]["start"].strftime("%B %Y"),
            "syscare_chart_anchor_label": month_points[-1]["start"].strftime("%B %Y"),
            "syscare_chart_total_achieved": sum(achieved_series),
            "syscare_chart_target_value": int(monthly_target or 0),
            "syscare_chart_has_data": any(value > 0 for value in achieved_series) or any(value > 0 for value in target_series),
        }

    def _load_syscare_membership_columns(cursor):
        cols = set()
        try:
            cursor.execute("SHOW COLUMNS FROM syscare_memberships")
            for row in cursor.fetchall() or []:
                # dictionary=True cursor returns dict; fallback for tuple rows
                if isinstance(row, dict):
                    name = row.get("Field")
                else:
                    name = row[0] if row else None
                if name:
                    cols.add(str(name))
        except Exception:
            pass
        return cols

    def _refresh_syscare_membership_columns(cursor=None):
        nonlocal syscare_membership_columns_cache

        if cursor is not None:
            syscare_membership_columns_cache = _load_syscare_membership_columns(cursor)
            return set(syscare_membership_columns_cache or ())

        db = None
        schema_cursor = None
        try:
            db = get_db()
            schema_cursor = db.cursor(dictionary=True)
            syscare_membership_columns_cache = _load_syscare_membership_columns(schema_cursor)
        except Exception:
            pass
        finally:
            if schema_cursor:
                schema_cursor.close()
            if db:
                db.close()

        return set(syscare_membership_columns_cache or ())

    def _get_syscare_membership_columns(cursor=None):
        if syscare_membership_columns_cache is None:
            return _refresh_syscare_membership_columns(cursor)
        return set(syscare_membership_columns_cache or ())

    def ensure_syscare_branch_targets_table():
        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS syscare_branch_targets (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    branch_name VARCHAR(255) NOT NULL,
                    monthly_target INT NOT NULL DEFAULT 30,
                    updated_by VARCHAR(255) NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_sbt_branch (branch_name)
                )
                """
            )
            db.commit()
        except db_error:
            pass
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    # Ensure once at app boot time
    ensure_syscare_memberships_table()
    ensure_syscare_branch_targets_table()
    _refresh_syscare_membership_columns()

    @app.route("/syscare")
    def syscare_dashboard():
        if "username" not in session:
            return redirect("/login")

        role = session.get("role")
        can_manage = role in ["super_admin", "admin"]
        can_create = True
        session_branch = (session.get("branch") or "").strip()
        has_global_scope = can_manage and session_branch.upper() == "ALL"
        user_branch_scope = None
        if not has_global_scope:
            # Everyone except ALL-branch admin/super_admin is branch-scoped.
            if session_branch and session_branch.upper() != "ALL":
                user_branch_scope = session_branch
            else:
                # Safety fallback: avoid exposing cross-branch data when branch is missing.
                user_branch_scope = "__NO_BRANCH__"

        selected_month = (request.args.get("month") or "").strip()
        selected_month, month_start, month_end = _month_start_end(selected_month)

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            membership_cols = _get_syscare_membership_columns(cursor)
            has_is_manual = "is_manual" in membership_cols

            # Load branch targets (admins: all branches, users: their own branch only)
            if user_branch_scope:
                cursor.execute(
                    "SELECT branch_name, monthly_target FROM syscare_branch_targets WHERE branch_name = %s ORDER BY branch_name",
                    (user_branch_scope,),
                )
            else:
                cursor.execute("SELECT branch_name, monthly_target FROM syscare_branch_targets ORDER BY branch_name")
            branch_targets_rows = cursor.fetchall()
            branch_targets_map = {r["branch_name"]: r["monthly_target"] for r in branch_targets_rows}

            # Per-branch achieved counts for this month
            achieved_sql = """
                SELECT branch_name, COUNT(*) AS achieved
                FROM syscare_memberships
                WHERE record_date >= %s AND record_date <= %s AND branch_name IS NOT NULL AND branch_name != ''
            """
            achieved_params = [month_start, month_end]
            if user_branch_scope:
                achieved_sql += " AND branch_name = %s"
                achieved_params.append(user_branch_scope)
            achieved_sql += " GROUP BY branch_name ORDER BY branch_name"
            cursor.execute(achieved_sql, tuple(achieved_params))
            branch_achieved_rows = cursor.fetchall()
            branch_achieved_map = {r["branch_name"]: int(r["achieved"] or 0) for r in branch_achieved_rows}

            # Overall achieved count
            count_sql = "SELECT COUNT(*) AS c FROM syscare_memberships WHERE record_date >= %s AND record_date <= %s"
            count_params = [month_start, month_end]
            if user_branch_scope:
                count_sql += " AND branch_name = %s"
                count_params.append(user_branch_scope)
            cursor.execute(count_sql, tuple(count_params))
            achieved_count = int((cursor.fetchone() or {}).get("c") or 0)

            # Total target = sum of branch targets, or 30 if none set
            monthly_target = sum(branch_targets_map.values()) if branch_targets_map else 30
            monthly_chart_context = _build_syscare_monthly_chart_context(
                cursor,
                selected_month,
                user_branch_scope,
                monthly_target,
            )

            remaining_count = max(monthly_target - achieved_count, 0)
            achieved_percentage = (achieved_count / monthly_target * 100.0) if monthly_target > 0 else 0.0

            if achieved_percentage >= 100:
                advice = "Target achieved. Keep quality and renewal follow-up strong."
                advice_class = "success"
            elif achieved_percentage >= 75:
                advice = "Close to target. Focus on pending warm leads this week."
                advice_class = "primary"
            elif achieved_percentage >= 50:
                advice = "Midway to target. Increase branch-level follow-ups and incharge conversion."
                advice_class = "warning"
            else:
                advice = "Below plan. Review daily conversion and prioritize expiring members."
                advice_class = "danger"

            # Build per-branch stats list
            all_branches = sorted(set(list(branch_targets_map.keys()) + list(branch_achieved_map.keys())))
            branch_stats = []
            for b in all_branches:
                b_target = branch_targets_map.get(b, 0)
                b_achieved = branch_achieved_map.get(b, 0)
                b_remaining = max(b_target - b_achieved, 0)
                b_pct = round((b_achieved / b_target * 100) if b_target > 0 else 0, 1)
                branch_stats.append({
                    "branch_name": b,
                    "monthly_target": b_target,
                    "achieved": b_achieved,
                    "remaining": b_remaining,
                    "percentage": b_pct,
                })

            # Show top-performing branches first in the dashboard table.
            branch_stats.sort(key=lambda row: (-int(row.get("achieved") or 0), (row.get("branch_name") or "").lower()))

            records_where = "record_date >= %s AND record_date <= %s"
            records_params = [month_start, month_end]
            if user_branch_scope:
                records_where += " AND branch_name = %s"
                records_params.append(user_branch_scope)

            # Server-side filter params
            per_page = 25
            try:
                current_page = max(int(request.args.get("page") or 1), 1)
            except ValueError:
                current_page = 1
            search_q = (request.args.get("q") or "").strip()
            filter_branch_rec = (request.args.get("branch") or "").strip()
            filter_incharge_rec = (request.args.get("incharge") or "").strip()

            if not user_branch_scope and filter_branch_rec:
                records_where += " AND branch_name = %s"
                records_params.append(filter_branch_rec)
            if filter_incharge_rec:
                records_where += " AND incharge = %s"
                records_params.append(filter_incharge_rec)
            if search_q:
                search_fields = ["customer_name", "syscare_id", "contact_number"]
                if "model_serial" in membership_cols:
                    search_fields.append("model_serial")
                if "product_model" in membership_cols:
                    search_fields.append("product_model")
                if "serial_number" in membership_cols:
                    search_fields.append("serial_number")
                like = f"%{search_q}%"
                records_where += " AND (" + " OR ".join(f"{f} LIKE %s" for f in search_fields) + ")"
                records_params.extend([like] * len(search_fields))

            # Total count for pagination
            cursor.execute(
                f"SELECT COUNT(*) AS c FROM syscare_memberships WHERE {records_where}",
                tuple(records_params),
            )
            total_records = int((cursor.fetchone() or {}).get("c") or 0)
            total_pages = max(1, (total_records + per_page - 1) // per_page)
            current_page = min(current_page, total_pages)
            offset = (current_page - 1) * per_page

            # Distinct branches & incharges for filter dropdowns (scoped)
            scope_where = "1=1"
            scope_params_list = []
            if user_branch_scope:
                scope_where = "branch_name = %s"
                scope_params_list = [user_branch_scope]
            cursor.execute(
                f"SELECT DISTINCT branch_name FROM syscare_memberships WHERE {scope_where} AND branch_name IS NOT NULL AND branch_name != '' ORDER BY branch_name",
                tuple(scope_params_list),
            )
            distinct_branches = [r["branch_name"] for r in cursor.fetchall()]
            cursor.execute(
                f"SELECT DISTINCT incharge FROM syscare_memberships WHERE {scope_where} AND incharge IS NOT NULL AND incharge != '' ORDER BY incharge",
                tuple(scope_params_list),
            )
            distinct_incharges = [r["incharge"] for r in cursor.fetchall()]

            cursor.execute(
                """
                  SELECT id, record_date, syscare_id, customer_name, contact_number,
                      {product_model_expr} AS product_model,
                      {serial_number_expr} AS serial_number,
                      {model_serial_expr} AS model_serial,
                      branch_name,
                      incharge, amount, expiry_date,
                      {is_manual_expr} AS is_manual
                FROM syscare_memberships
                WHERE {records_where}
                ORDER BY record_date DESC, id DESC
                LIMIT {per_page} OFFSET {offset}
                """.format(
                    product_model_expr=("product_model" if "product_model" in membership_cols else "NULL"),
                    serial_number_expr=("serial_number" if "serial_number" in membership_cols else "NULL"),
                    model_serial_expr=("model_serial" if "model_serial" in membership_cols else "NULL"),
                    is_manual_expr=("is_manual" if has_is_manual else "0"),
                    records_where=records_where,
                    per_page=per_page,
                    offset=offset,
                ),
                tuple(records_params),
            )
            records = cursor.fetchall()
            for record in records:
                record["expire_within_days"] = _days_until_expiry(record.get("expiry_date"))

            return render_template(
                "syscare_dashboard.html",
                selected_month=selected_month,
                month_start=month_start,
                month_end=month_end,
                monthly_target=monthly_target,
                achieved_count=achieved_count,
                remaining_count=remaining_count,
                achieved_percentage=achieved_percentage,
                advice=advice,
                advice_class=advice_class,
                records=records,
                total_records=total_records,
                total_pages=total_pages,
                current_page=current_page,
                search_q=search_q,
                filter_branch_rec=filter_branch_rec,
                filter_incharge_rec=filter_incharge_rec,
                distinct_branches=distinct_branches,
                distinct_incharges=distinct_incharges,
                branch_stats=branch_stats,
                branch_targets_map=branch_targets_map,
                can_manage=can_manage,
                can_create=can_create,
                **monthly_chart_context,
            )

        except db_error as e:
            _flash_internal_error("SYSCARE error", e)
            return redirect("/dashboard")
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    @app.route("/syscare-upload", methods=["POST"])
    def syscare_upload():
        if "username" not in session:
            return redirect("/login")

        role = session.get("role")
        session_branch = (session.get("branch") or "").strip()
        if role not in ["super_admin", "admin"]:
            return "Access Denied"

        try:
            branch_scope = _get_branch_scope(role, session_branch)
        except PermissionError:
            flash("Invalid branch scope", "danger")
            return redirect("/syscare")

        selected_month = (request.form.get("month") or "").strip()
        selected_month, month_start, month_end = _month_start_end(selected_month)

        upload = request.files.get("syscare_file")
        if not upload or not (upload.filename or "").strip():
            flash("Choose Excel or CSV file", "danger")
            return redirect(f"/syscare?month={selected_month}")

        try:
            parsed = list(_iter_syscare_upload_rows(upload))
        except ValueError as e:
            _flash_internal_error("Could not read SYSCARE upload file", e)
            return redirect(f"/syscare?month={selected_month}")
        except Exception as e:
            _flash_internal_error("Could not read SYSCARE upload file", e)
            return redirect(f"/syscare?month={selected_month}")

        if not parsed:
            flash("No rows found", "warning")
            return redirect(f"/syscare?month={selected_month}")

        rows_to_upsert = []
        skipped = 0
        for row_number, payload in parsed:
            if not payload:
                skipped += 1
                continue
            payload_branch = str(payload.get("branch_name") or "").strip()
            if branch_scope:
                if payload_branch and payload_branch != branch_scope:
                    skipped += 1
                    continue
                payload["branch_name"] = branch_scope
            rows_to_upsert.append(
                (
                    payload["record_date"],
                    payload["syscare_id"],
                    payload["customer_name"] or None,
                    payload["contact_number"] or None,
                    payload["branch_name"] or None,
                    payload["incharge"] or None,
                    payload["model_serial"] or None,
                    payload["product_model"] or None,
                    payload["serial_number"] or None,
                    payload["amount"],
                    payload["expiry_date"].strftime("%Y-%m-%d") if payload["expiry_date"] else None,
                    session.get("username"),
                )
            )

        if not rows_to_upsert:
            flash(f"No valid rows to upload. Skipped {skipped}", "warning")
            return redirect(f"/syscare?month={selected_month}")

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.executemany(
                """
                INSERT INTO syscare_memberships
                    (record_date, syscare_id, customer_name, contact_number, branch_name,
                     incharge, model_serial, product_model, serial_number, amount, expiry_date, uploaded_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    record_date=VALUES(record_date),
                    customer_name=VALUES(customer_name),
                    contact_number=VALUES(contact_number),
                    branch_name=VALUES(branch_name),
                    incharge=VALUES(incharge),
                    model_serial=VALUES(model_serial),
                    product_model=VALUES(product_model),
                    serial_number=VALUES(serial_number),
                    amount=VALUES(amount),
                    expiry_date=VALUES(expiry_date),
                    uploaded_by=VALUES(uploaded_by),
                    uploaded_at=CURRENT_TIMESTAMP
                """,
                rows_to_upsert,
            )
            db.commit()
            flash(f"SYSCARE upload complete: {len(rows_to_upsert)} saved, {skipped} skipped", "success")
        except db_error as e:
            _flash_internal_error("SYSCARE upload failed", e)
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

        return redirect(f"/syscare?month={selected_month}")

    @app.route("/syscare-set-targets", methods=["POST"])
    def syscare_set_targets():
        if "username" not in session:
            return redirect("/login")
        role = session.get("role")
        session_branch = (session.get("branch") or "").strip()
        if role not in ["super_admin", "admin"]:
            return "Access Denied"

        try:
            branch_scope = _get_branch_scope(role, session_branch)
        except PermissionError:
            flash("Invalid branch scope", "danger")
            return redirect("/syscare")

        selected_month = (request.form.get("month") or "").strip()
        branches = request.form.getlist("branch_name[]")
        targets = request.form.getlist("target[]")
        new_branch = (request.form.get("new_branch_name") or "").strip()
        new_target_str = (request.form.get("new_branch_target") or "0").strip()
        delete_branch_name = (request.form.get("delete_branch_name") or "").strip()

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor()
            if delete_branch_name:
                if branch_scope and delete_branch_name != branch_scope:
                    flash("Access denied for this branch", "danger")
                    return redirect(f"/syscare?month={selected_month}")
                cursor.execute(
                    "DELETE FROM syscare_branch_targets WHERE branch_name = %s",
                    (delete_branch_name,),
                )
                db.commit()
                flash(f"Branch target '{delete_branch_name}' deleted.", "success")
                return redirect(f"/syscare?month={selected_month}")

            for branch, target_str in zip(branches, targets):
                branch = branch.strip()
                if not branch:
                    continue
                if branch_scope and branch != branch_scope:
                    flash("Access denied for this branch", "danger")
                    return redirect(f"/syscare?month={selected_month}")
                try:
                    target = max(int(target_str or 0), 0)
                except ValueError:
                    target = 0
                cursor.execute(
                    """
                    INSERT INTO syscare_branch_targets (branch_name, monthly_target, updated_by)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE monthly_target=VALUES(monthly_target), updated_by=VALUES(updated_by)
                    """,
                    (branch, target, session.get("username")),
                )
            if new_branch:
                if branch_scope and new_branch != branch_scope:
                    flash("Access denied for this branch", "danger")
                    return redirect(f"/syscare?month={selected_month}")
                try:
                    new_target = max(int(new_target_str or 0), 0)
                except ValueError:
                    new_target = 0
                cursor.execute(
                    """
                    INSERT INTO syscare_branch_targets (branch_name, monthly_target, updated_by)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE monthly_target=VALUES(monthly_target), updated_by=VALUES(updated_by)
                    """,
                    (new_branch, new_target, session.get("username")),
                )
            db.commit()
            flash("Branch targets saved successfully.", "success")
        except db_error as e:
            _flash_internal_error("Failed to save targets", e)
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

        return redirect(f"/syscare?month={selected_month}")

    @app.route("/syscare-new", methods=["GET", "POST"])
    def syscare_new_entry():
        if "username" not in session:
            return redirect("/login")
        role = session.get("role")
        session_branch = (session.get("branch") or "").strip()

        try:
            branch_scope = _get_branch_scope(role, session_branch)
        except PermissionError:
            flash("Invalid branch scope", "danger")
            return redirect("/dashboard")


        def _get_form_defaults():
            if branch_scope:
                return [branch_scope], []
            branch_set = set()
            incharge_set = set()
            db2 = None
            cur2 = None
            try:
                db2 = get_db()
                cur2 = db2.cursor(dictionary=True)
                # Pull branches from multiple sources. If one table/query fails,
                # continue with the others so suggestions are still available.
                branch_queries = [
                    "SELECT DISTINCT branch_name FROM syscare_memberships WHERE branch_name IS NOT NULL AND branch_name != ''",
                    "SELECT DISTINCT branch_name FROM syscare_branch_targets WHERE branch_name IS NOT NULL AND branch_name != ''",
                    "SELECT DISTINCT branch_name FROM jobs WHERE branch_name IS NOT NULL AND branch_name != ''",
                    "SELECT value AS branch_name FROM dropdown_options WHERE type='branch'",
                ]
                if role in ["super_admin", "admin"]:
                    branch_queries.append("SELECT DISTINCT branch_name FROM user_branches WHERE branch_name IS NOT NULL AND branch_name != ''")
                else:
                    branch_queries.append("SELECT branch_name FROM user_branches WHERE username=%s AND branch_name IS NOT NULL AND branch_name != ''")

                for q in branch_queries:
                    try:
                        if "%s" in q:
                            cur2.execute(q, (session.get("username"),))
                        else:
                            cur2.execute(q)
                        for r in cur2.fetchall() or []:
                            bname = (r.get("branch_name") if isinstance(r, dict) else None) or ""
                            bname = str(bname).strip()
                            if bname:
                                branch_set.add(bname)
                    except Exception:
                        continue

                # Incharge suggestions: prioritize engineers and historical SYSCARE incharge values.
                incharge_queries = [
                    "SELECT DISTINCT incharge AS incharge_name FROM syscare_memberships WHERE incharge IS NOT NULL AND incharge != ''",
                    "SELECT DISTINCT username AS incharge_name FROM users WHERE role='engineer' AND username IS NOT NULL AND username != ''",
                    "SELECT DISTINCT username AS incharge_name FROM users WHERE username IS NOT NULL AND username != ''",
                ]
                for q in incharge_queries:
                    try:
                        cur2.execute(q)
                        for r in cur2.fetchall() or []:
                            iname = (r.get("incharge_name") if isinstance(r, dict) else None) or ""
                            iname = str(iname).strip()
                            if iname:
                                incharge_set.add(iname)
                    except Exception:
                        continue

                if session_branch:
                    branch_set.add(session_branch)
            except Exception:
                pass
            finally:
                if cur2:
                    cur2.close()
                if db2:
                    db2.close()
            return sorted(branch_set), sorted(incharge_set)

        if request.method == "GET":
            branches, incharges = _get_form_defaults()
            today = date.today()
            expiry = today + timedelta(days=364)
            return render_template(
                "syscare_new_entry.html",
                branches=branches,
                incharges=incharges,
                default_branch=session_branch,
                user_role=role,
                is_edit=False,
                route_action="/syscare-new",
                entry=None,
                today=today.strftime("%Y-%m-%d"),
                expiry=expiry.strftime("%Y-%m-%d"),
            )

        # POST — save new entry
        # syscare_id is only taken from the form for admin/super_admin, else will be generated after insert
        record_date_str = (request.form.get("record_date") or "").strip()
        expiry_date_str = (request.form.get("expiry_date") or "").strip()
        customer_name = (request.form.get("customer_name") or "").strip()
        contact_number = (request.form.get("contact_number") or "").strip()
        address = (request.form.get("address") or "").strip()
        mail_id = (request.form.get("mail_id") or "").strip()
        product_model = (request.form.get("product_model") or "").strip()
        serial_number = (request.form.get("serial_number") or "").strip()
        model_serial_legacy = (request.form.get("model_serial") or "").strip()
        if (not product_model or not serial_number) and model_serial_legacy:
            legacy_model, legacy_serial = _split_model_serial(model_serial_legacy)
            if not product_model:
                product_model = legacy_model
            if not serial_number:
                serial_number = legacy_serial
        model_serial = f"{product_model} / {serial_number}".strip(" /")
        branch_name = (request.form.get("branch_name") or "").strip()
        if branch_scope:
            branch_name = branch_scope
        incharge = (request.form.get("incharge") or "").strip()
        assigned_engineer = (request.form.get("assigned_engineer") or "").strip()
        amount_str = (request.form.get("amount") or "0").strip()

        errors = []
        if role in ["admin", "super_admin"]:
            syscare_id = (request.form.get("syscare_id") or "").strip()
        else:
            syscare_id = None
        if not record_date_str:
            errors.append("Date is required")
        if not expiry_date_str:
            errors.append("Expiry Date is required")
        if not customer_name:
            errors.append("Customer name is required")
        if not contact_number:
            errors.append("Mobile Number is required")
        if not product_model:
            errors.append("Product Model is required")
        if not serial_number:
            errors.append("Serial Number is required")
        if not branch_name:
            errors.append("Branch is required")
        if not incharge:
            errors.append("Incharge is required")
        if amount_str == "":
            errors.append("Amount is required")
        if errors:
            for e in errors:
                flash(e, "danger")
            return redirect("/syscare-new")

        try:
            record_date = datetime.strptime(record_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format", "danger")
            return redirect("/syscare-new")

        try:
            expiry_date = (
                datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
                if expiry_date_str
                else record_date + timedelta(days=364)
            )
        except ValueError:
            expiry_date = record_date + timedelta(days=364)

        try:
            amount = float(amount_str.replace(",", "") or 0)
        except ValueError:
            amount = 0.0

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            membership_cols = _get_syscare_membership_columns(cursor)

            insert_cols = ["record_date", "customer_name", "contact_number"]
            insert_vals = [
                record_date.strftime("%Y-%m-%d"),
                customer_name or None,
                contact_number or None,
            ]
            # Only allow syscare_id for admin/super_admin
            if role in ["admin", "super_admin"] and syscare_id:
                insert_cols.insert(1, "syscare_id")
                insert_vals.insert(1, syscare_id)
            else:
                syscare_id = str(
                    next_sequence_value(
                        cursor,
                        "syscare_memberships",
                        """
                                                SELECT COALESCE(MAX(CAST(syscare_id AS UNSIGNED)), 5000) AS seed_value
                        FROM syscare_memberships
                        WHERE syscare_id IS NOT NULL
                          AND syscare_id REGEXP '^[0-9]+$'
                        """,
                    )
                )
                insert_cols.insert(1, "syscare_id")
                insert_vals.insert(1, syscare_id)

            optional_values = {
                "address": address or None,
                "mail_id": mail_id or None,
                "model_serial": model_serial or None,
                "product_model": product_model or None,
                "serial_number": serial_number or None,
                "branch_name": branch_name or None,
                "incharge": incharge or None,
                "assigned_engineer": assigned_engineer or None,
                "amount": amount,
                "expiry_date": expiry_date.strftime("%Y-%m-%d"),
                "uploaded_by": session.get("username"),
            }
            for col, val in optional_values.items():
                if col in membership_cols:
                    insert_cols.append(col)
                    insert_vals.append(val)
            if "is_manual" in membership_cols:
                insert_cols.append("is_manual")
                insert_vals.append(1)

            columns_sql = ", ".join(insert_cols)
            placeholders_sql = ", ".join(["%s"] * len(insert_cols))
            cursor.execute(
                f"INSERT INTO syscare_memberships ({columns_sql}) VALUES ({placeholders_sql})",
                tuple(insert_vals),
            )
            db.commit()
            entry_id = cursor.lastrowid

            flash(f"SYSCARE entry created: ID {syscare_id}", "success")
            return redirect(f"/syscare-certificate/{entry_id}")
        except db_error as e:
            if e.errno == 1062:
                flash(f"SYSCARE ID {syscare_id} already exists. Use a different ID.", "danger")
            else:
                _flash_internal_error("SYSCARE save failed", e)
            return redirect("/syscare-new")
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    @app.route("/syscare-edit/<int:entry_id>", methods=["GET", "POST"])
    def syscare_edit_entry(entry_id):
        if "username" not in session:
            return redirect("/login")
        role = session.get("role")
        session_branch = (session.get("branch") or "").strip()
        if role not in ["super_admin", "admin"]:
            return "Access Denied"

        try:
            branch_scope = _get_branch_scope(role, session_branch)
        except PermissionError:
            flash("Invalid branch scope", "danger")
            return redirect("/syscare")

        def _load_form_suggestions():
            if branch_scope:
                return [branch_scope], []
            branch_set = set()
            incharge_set = set()
            db2 = None
            cur2 = None
            try:
                db2 = get_db()
                cur2 = db2.cursor(dictionary=True)
                queries = [
                    "SELECT DISTINCT branch_name FROM syscare_memberships WHERE branch_name IS NOT NULL AND branch_name != ''",
                    "SELECT DISTINCT branch_name FROM syscare_branch_targets WHERE branch_name IS NOT NULL AND branch_name != ''",
                    "SELECT DISTINCT branch_name FROM jobs WHERE branch_name IS NOT NULL AND branch_name != ''",
                    "SELECT value AS branch_name FROM dropdown_options WHERE type='branch'",
                    "SELECT DISTINCT branch_name FROM user_branches WHERE branch_name IS NOT NULL AND branch_name != ''",
                ]
                for q in queries:
                    try:
                        cur2.execute(q)
                        for r in cur2.fetchall() or []:
                            bname = str((r.get("branch_name") if isinstance(r, dict) else "") or "").strip()
                            if bname:
                                branch_set.add(bname)
                    except Exception:
                        continue

                incharge_queries = [
                    "SELECT DISTINCT incharge AS incharge_name FROM syscare_memberships WHERE incharge IS NOT NULL AND incharge != ''",
                    "SELECT DISTINCT username AS incharge_name FROM users WHERE role='engineer' AND username IS NOT NULL AND username != ''",
                    "SELECT DISTINCT username AS incharge_name FROM users WHERE username IS NOT NULL AND username != ''",
                ]
                for q in incharge_queries:
                    try:
                        cur2.execute(q)
                        for r in cur2.fetchall() or []:
                            iname = str((r.get("incharge_name") if isinstance(r, dict) else "") or "").strip()
                            if iname:
                                incharge_set.add(iname)
                    except Exception:
                        continue
            except Exception:
                pass
            finally:
                if cur2:
                    cur2.close()
                if db2:
                    db2.close()
            return sorted(branch_set), sorted(incharge_set)

        def _get_entry(cursor_obj, cols, rid):
            select_parts = [
                "id",
                "record_date",
                "syscare_id",
                "customer_name",
                "contact_number",
                ("address" if "address" in cols else "NULL AS address"),
                ("mail_id" if "mail_id" in cols else "NULL AS mail_id"),
                ("model_serial" if "model_serial" in cols else "NULL AS model_serial"),
                ("product_model" if "product_model" in cols else "NULL AS product_model"),
                ("serial_number" if "serial_number" in cols else "NULL AS serial_number"),
                "branch_name",
                "incharge",
                "amount",
                "expiry_date",
            ]
            entry_sql = f"SELECT {', '.join(select_parts)} FROM syscare_memberships WHERE id = %s"
            entry_params = [rid]
            if branch_scope:
                entry_sql += " AND branch_name = %s"
                entry_params.append(branch_scope)
            cursor_obj.execute(entry_sql, tuple(entry_params))
            entry = cursor_obj.fetchone()
            if entry:
                entry["expire_within_days"] = _days_until_expiry(entry.get("expiry_date"))
            return entry

        if request.method == "GET":
            db = None
            cursor = None
            try:
                db = get_db()
                cursor = db.cursor(dictionary=True)
                membership_cols = _get_syscare_membership_columns(cursor)
                entry = _get_entry(cursor, membership_cols, entry_id)
                if not entry:
                    flash("Record not found", "danger")
                    return redirect("/syscare")
                branches, incharges = _load_form_suggestions()
                return render_template(
                    "syscare_new_entry.html",
                    next_id=str(entry.get("syscare_id") or ""),
                    branches=branches,
                    incharges=incharges,
                    default_branch=str(entry.get("branch_name") or ""),
                    user_role=session.get("role"),
                    is_edit=True,
                    route_action=f"/syscare-edit/{entry_id}",
                    entry=entry,
                    today=(entry.get("record_date").strftime("%Y-%m-%d") if getattr(entry.get("record_date"), "strftime", None) else str(entry.get("record_date") or "")),
                    expiry=(entry.get("expiry_date").strftime("%Y-%m-%d") if getattr(entry.get("expiry_date"), "strftime", None) else str(entry.get("expiry_date") or "")),
                )
            except db_error as e:
                _flash_internal_error("Could not load SYSCARE record", e)
                return redirect("/syscare")
            finally:
                if cursor:
                    cursor.close()
                if db:
                    db.close()

        # POST update
        syscare_id = (request.form.get("syscare_id") or "").strip()
        record_date_str = (request.form.get("record_date") or "").strip()
        expiry_date_str = (request.form.get("expiry_date") or "").strip()
        customer_name = (request.form.get("customer_name") or "").strip()
        contact_number = (request.form.get("contact_number") or "").strip()
        address = (request.form.get("address") or "").strip()
        mail_id = (request.form.get("mail_id") or "").strip()
        product_model = (request.form.get("product_model") or "").strip()
        serial_number = (request.form.get("serial_number") or "").strip()
        model_serial_legacy = (request.form.get("model_serial") or "").strip()
        if (not product_model or not serial_number) and model_serial_legacy:
            legacy_model, legacy_serial = _split_model_serial(model_serial_legacy)
            if not product_model:
                product_model = legacy_model
            if not serial_number:
                serial_number = legacy_serial
        model_serial = f"{product_model} / {serial_number}".strip(" /")
        branch_name = (request.form.get("branch_name") or "").strip()
        incharge = (request.form.get("incharge") or "").strip()
        amount_str = (request.form.get("amount") or "0").strip()

        errors = []
        if not syscare_id:
            errors.append("SYSCARE ID is required")
        if not record_date_str:
            errors.append("Date is required")
        if not expiry_date_str:
            errors.append("Expiry Date is required")
        if not customer_name:
            errors.append("Customer Name is required")
        if not contact_number:
            errors.append("Mobile Number is required")
        if not product_model:
            errors.append("Product Model is required")
        if not serial_number:
            errors.append("Serial Number is required")
        if not branch_name:
            errors.append("Branch is required")
        if not incharge:
            errors.append("Incharge is required")
        if amount_str == "":
            errors.append("Amount is required")
        if errors:
            for e in errors:
                flash(e, "danger")
            return redirect(f"/syscare-edit/{entry_id}")

        try:
            record_date = datetime.strptime(record_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format", "danger")
            return redirect(f"/syscare-edit/{entry_id}")

        try:
            expiry_date = (
                datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
                if expiry_date_str
                else record_date + timedelta(days=364)
            )
        except ValueError:
            expiry_date = record_date + timedelta(days=364)

        try:
            amount = float(amount_str.replace(",", "") or 0)
        except ValueError:
            amount = 0.0

        if branch_scope:
            branch_name = branch_scope

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            membership_cols = _get_syscare_membership_columns(cursor)

            existing_entry = _get_entry(cursor, membership_cols, entry_id)
            if not existing_entry:
                flash("Record not found", "danger")
                return redirect("/syscare")

            updates = []
            values = []
            field_values = {
                "record_date": record_date.strftime("%Y-%m-%d"),
                "syscare_id": syscare_id,
                "customer_name": customer_name or None,
                "contact_number": contact_number or None,
                "address": address or None,
                "mail_id": mail_id or None,
                "model_serial": model_serial or None,
                "product_model": product_model or None,
                "serial_number": serial_number or None,
                "branch_name": branch_name or None,
                "incharge": incharge or None,
                "amount": amount,
                "expiry_date": expiry_date.strftime("%Y-%m-%d"),
                "uploaded_by": session.get("username"),
            }

            for col, val in field_values.items():
                if col in membership_cols:
                    updates.append(f"{col}=%s")
                    values.append(val)

            if not updates:
                flash("No editable columns available", "warning")
                return redirect(f"/syscare-certificate/{entry_id}")

            values.append(entry_id)
            update_sql = f"UPDATE syscare_memberships SET {', '.join(updates)} WHERE id=%s"
            if branch_scope:
                update_sql += " AND branch_name=%s"
                values.append(branch_scope)
            cursor.execute(update_sql, tuple(values))
            db.commit()
            flash("SYSCARE certificate updated", "success")
            return redirect(f"/syscare-certificate/{entry_id}")
        except db_error as e:
            if e.errno == 1062:
                flash(f"SYSCARE ID {syscare_id} already exists.", "danger")
            else:
                _flash_internal_error("SYSCARE update failed", e)
            return redirect(f"/syscare-edit/{entry_id}")
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    @app.route("/syscare-certificate/<int:entry_id>")
    def syscare_certificate(entry_id):
        if "username" not in session:
            return redirect("/login")
        role = session.get("role")
        can_edit = role in ["super_admin", "admin"]
        session_branch = (session.get("branch") or "").strip()
        has_global_scope = can_edit and session_branch.upper() == "ALL"

        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            membership_cols = _get_syscare_membership_columns(cursor)

            select_parts = [
                "id",
                "record_date",
                "syscare_id",
                "customer_name",
                "contact_number",
                ("address" if "address" in membership_cols else "NULL AS address"),
                ("mail_id" if "mail_id" in membership_cols else "NULL AS mail_id"),
                ("model_serial" if "model_serial" in membership_cols else "NULL AS model_serial"),
                ("product_model" if "product_model" in membership_cols else "NULL AS product_model"),
                ("serial_number" if "serial_number" in membership_cols else "NULL AS serial_number"),
                "branch_name",
                "incharge",
                (
                    "assigned_engineer"
                    if "assigned_engineer" in membership_cols
                    else "NULL AS assigned_engineer"
                ),
                "amount",
                "expiry_date",
                ("is_manual" if "is_manual" in membership_cols else "0 AS is_manual"),
            ]

            cert_sql = f"SELECT {', '.join(select_parts)} FROM syscare_memberships WHERE id = %s"
            cert_params = [entry_id]
            if not has_global_scope:
                # Everyone except ALL-branch admin/super_admin is branch-scoped.
                if session_branch and session_branch.upper() != "ALL":
                    cert_sql += " AND branch_name = %s"
                    cert_params.append(session_branch)
                else:
                    cert_sql += " AND 1=0"
            cursor.execute(cert_sql, tuple(cert_params))
            entry = cursor.fetchone()
            if not entry:
                flash("Record not found", "danger")
                return redirect("/syscare")
            entry["expire_within_days"] = _days_until_expiry(entry.get("expiry_date"))
            entry["record_date_display"] = _format_display_date(entry.get("record_date"))
            entry["expiry_date_display"] = _format_display_date(entry.get("expiry_date"))
            book_complaint_url = "https://wa.me/918086744444"
            store_locator_url = "https://sysmantech.net/storelocator"
            return render_template(
                "syscare_certificate.html",
                entry=entry,
                can_edit=can_edit,
                book_complaint_url=book_complaint_url,
                store_locator_url=store_locator_url,
                book_complaint_qr=_build_qr_data_uri(book_complaint_url),
                store_locator_qr=_build_qr_data_uri(store_locator_url),
            )
        except db_error as e:
            _flash_internal_error("Could not load SYSCARE certificate", e)
            return redirect("/syscare")
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()

    @app.route("/syscare-delete/<int:entry_id>", methods=["POST"])
    def syscare_delete_entry(entry_id):
        if "username" not in session:
            return redirect("/login")
        if session.get("role") not in ["super_admin", "admin"]:
            return "Access Denied", 403
        session_branch = (session.get("branch") or "").strip()
        has_global_scope = session_branch.upper() == "ALL"
        month_back = (request.form.get("month") or "").strip()
        redirect_url = f"/syscare{('?month=' + month_back) if month_back else ''}"
        db = None
        cursor = None
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            if has_global_scope:
                cursor.execute("SELECT syscare_id FROM syscare_memberships WHERE id = %s", (entry_id,))
            else:
                if not session_branch or session_branch.upper() == "ALL":
                    flash("Invalid branch scope", "danger")
                    return redirect(redirect_url)
                cursor.execute(
                    "SELECT syscare_id FROM syscare_memberships WHERE id = %s AND branch_name = %s",
                    (entry_id, session_branch),
                )
            row = cursor.fetchone()
            if not row:
                flash("Record not found", "danger")
                return redirect(redirect_url)
            syscare_id = row["syscare_id"]
            if has_global_scope:
                cursor.execute("DELETE FROM syscare_memberships WHERE id = %s", (entry_id,))
            else:
                cursor.execute(
                    "DELETE FROM syscare_memberships WHERE id = %s AND branch_name = %s",
                    (entry_id, session_branch),
                )
            db.commit()
            flash(f"SYSCARE entry {syscare_id} deleted successfully.", "success")
        except db_error as e:
            _flash_internal_error("Failed to delete SYSCARE entry", e)
        finally:
            if cursor:
                cursor.close()
            if db:
                db.close()
        return redirect(redirect_url)
