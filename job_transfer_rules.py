TRANSFER_STATUSES = (
    "Sent",
    "In Service",
    "Completed",
    "Returned",
    "Cancelled",
)

ACTIVE_TRANSFER_STATUSES = (
    "Sent",
    "In Service",
    "Completed",
)

COMPLETED_TRANSFER_STATUSES = (
    "Completed",
    "Returned",
)

TRANSFER_ALLOWED_TRANSITIONS = {
    "Sent": ("In Service", "Completed", "Returned", "Cancelled"),
    "In Service": ("Completed", "Returned", "Cancelled"),
    "Completed": ("Returned",),
    "Returned": (),
    "Cancelled": (),
}


def normalize_transfer_status(value, default="Sent"):
    normalized = str(value or "").strip().lower()
    for status in TRANSFER_STATUSES:
        if status.lower() == normalized:
            return status
    return default


def allowed_next_transfer_statuses(current_status):
    normalized_current = normalize_transfer_status(current_status, default="")
    return TRANSFER_ALLOWED_TRANSITIONS.get(normalized_current, ())


def can_transition_transfer_status(current_status, next_status):
    normalized_next = normalize_transfer_status(next_status, default="")
    if not normalized_next:
        return False
    if normalize_transfer_status(current_status, default="") == normalized_next:
        return True
    return normalized_next in allowed_next_transfer_statuses(current_status)


def compute_job_transfer_split(total_service_charge, specialist_service_total):
    service_total = round(max(float(total_service_charge or 0), 0.0), 2)
    specialist_total = round(max(float(specialist_service_total or 0), 0.0), 2)
    return {
        "total_service_charge": service_total,
        "specialist_service_total": specialist_total,
        "closing_branch_service_margin": round(service_total - specialist_total, 2),
    }


def summarize_job_transfers(transfers, total_service_charge):
    normalized_transfers = []
    active_transfer = None
    latest_completed_transfer = None
    specialist_service_total = 0.0

    for raw_row in transfers or []:
        row = dict(raw_row or {})
        row["status"] = normalize_transfer_status(row.get("status"), default="Sent")
        row["internal_service_charge"] = round(max(float(row.get("internal_service_charge") or 0), 0.0), 2)
        normalized_transfers.append(row)

        if active_transfer is None and row["status"] in ACTIVE_TRANSFER_STATUSES:
            active_transfer = row

        if row["status"] in COMPLETED_TRANSFER_STATUSES:
            specialist_service_total += row["internal_service_charge"]
            if latest_completed_transfer is None:
                latest_completed_transfer = row

    split = compute_job_transfer_split(total_service_charge, specialist_service_total)
    return {
        "rows": normalized_transfers,
        "active_transfer": active_transfer,
        "latest_completed_transfer": latest_completed_transfer,
        "has_active_transfer": active_transfer is not None,
        "transfer_count": len(normalized_transfers),
        **split,
    }