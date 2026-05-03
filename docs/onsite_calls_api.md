# Onsite Call Module API

## Auth Model

- Public request route does not require login.
- Internal dashboard, detail, assignment, note, status, and report routes require an authenticated session.
- Reports are limited to `admin` and `super_admin`.
- Assignment is limited to `admin` and `super_admin`.
- Staff visibility is branch-scoped using the current CRM session branch.

## Pages

- `GET /onsite-call/request`
  - Public customer form
- `GET /onsite-calls/new`
  - Internal create form
- `GET /onsite-calls`
  - Dashboard list with filters and pagination
- `GET /onsite-calls/<call_id>`
  - Call detail, notes, assignment, status, reschedule
- `GET /onsite-calls/reports`
  - Admin reports view

## APIs

### Public Create

- `POST /api/onsite-call/create-public`
- Request fields:
  - `customer_name`
  - `phone`
  - `location`
  - `district`
  - `complaint_type`
  - `preferred_service`
  - `priority`
  - `preferred_datetime`
  - `device_model`
  - `complaint_description`
- Success:
  - `201` is not forced because form and JSON clients share the same endpoint; JSON clients receive `200` with `success=true`
- Result:
  - status starts as `New Lead`
  - source is `Customer`
  - admins are notified through log entries

### Internal Create

- `POST /api/onsite-call/create`
- Requires login
- Extra request fields:
  - `branch_name`
  - `assigned_engineer_id`
- Result:
  - status is `Open` when no engineer is assigned
  - status is `Assigned` when created with engineer assignment
  - source is `Admin` or `Staff` based on current role

### Engineer Lookup

- `GET /api/onsite-call/engineers?branch=<branch_name>`
- Requires login
- Response:
  - `{ "success": true, "items": [{"id": 3, "username": "engineer1"}] }`

### Assign Call

- `POST /api/onsite-call/assign`
- Requires `admin` or `super_admin`
- Request fields:
  - `call_id`
  - `branch_name`
  - `assigned_engineer_id`
- Allowed source statuses:
  - `Open`
  - `Assigned`
  - `Rescheduled`
- Result:
  - call status becomes `Assigned`
  - assignment time updates
  - log and notification entries are written

### Update Status

- `POST /api/onsite-call/update-status`
- Requires login
- Request fields:
  - `call_id`
  - `status`
  - `status_note` optional
- Allowed transitions:
  - `New Lead -> Open, Cancelled, Rescheduled`
  - `Open -> Assigned, Cancelled, Rescheduled`
  - `Assigned -> In Progress, Cancelled, Rescheduled`
  - `In Progress -> Completed, Failed, Cancelled, Rescheduled`
  - `Rescheduled -> Open, Assigned, Cancelled, Rescheduled`
  - `Completed -> Cancelled, Rescheduled`
  - `Failed -> Cancelled, Rescheduled`

### Add Note

- `POST /api/onsite-call/add-note`
- Requires login
- Request fields:
  - `call_id`
  - `note`

### Reschedule

- `POST /api/onsite-call/reschedule`
- Requires login
- Request fields:
  - `call_id`
  - `preferred_datetime`
  - `reason` optional
- Result:
  - status becomes `Rescheduled`
  - preferred datetime updates

### Dashboard List API

- `GET /onsite-calls?format=json`
- Filters:
  - `status`
  - `branch`
  - `engineer`
  - `complaint_type`
  - `priority`
  - `search`
  - `from_date`
  - `to_date`
  - `page`
  - `per_page`

### Reports API

- `GET /onsite-calls/reports?format=json`
- Requires `admin` or `super_admin`
- Filters:
  - `branch`
  - `engineer`
  - `complaint_type`
  - `priority`
  - `from_date`
  - `to_date`

## Concurrency Notes

- Assignment and status-changing routes lock the target row with `SELECT ... FOR UPDATE` through SQLAlchemy.
- Reports and dashboard counts use a short TTL in-memory cache to reduce repeated aggregation load.
- Public creation is safe for concurrent users because inserts are independent and do not rely on shared sequence counters.
