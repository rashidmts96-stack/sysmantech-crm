# Final Pre-Deploy Checklist

Follow this in order.

## Step 1: What to upload

Upload the full contents of `service-crm/deploy/` to your cPanel Python app root.

Upload these top-level items:

- `.htaccess`
- `.env.example`
- `app.py`
- `dashboard_settings_routes.py`
- `onsite_calls_blueprint.py`
- `passenger_wsgi.py`
- `requirements.txt`
- `syscare_routes.py`
- `CPANEL_DEPLOY.md`
- `FINAL_PRE_DEPLOY_CHECKLIST.md`
- `database/`
- `docs/`
- `instance/`
- `static/`
- `templates/`
- `tmp/`
- helper scripts like `tmp_add_columns.py`, `tmp_add_new_fields.py`, `tmp_show_jobs_schema.py`, `tmp_show_schema.py`, `update_syscare_expiry_and_alerts.py`

Do not upload:

- `__pycache__/`

If you are using environment variables in cPanel, clear or replace local secret values inside `instance/db_password` and `instance/secret_key` before upload.

## Step 2: cPanel Python App settings

Set these in `Setup Python App`:

- Python version: `3.10+`
- Startup file: `passenger_wsgi.py`
- Entry point: `application`

## Step 3: Paste these environment variables

Use your real cPanel database names and your own long random secret:

```text
DB_HOST=localhost
DB_NAME=your_cpanel_db_name
DB_USER=your_cpanel_db_username
DB_PASSWORD=your_cpanel_db_password
SECRET_KEY=replace_with_a_long_random_secret_string_here
APP_DEBUG=0
SESSION_COOKIE_SECURE=1
CSRF_ENFORCE_ALL_POSTS=1
DB_POOL_SIZE=24
DB_POOL_ACQUIRE_TIMEOUT_SECONDS=20
MAX_UPLOAD_REQUEST_MB=50
ONSITE_PUBLIC_CREATE_LIMIT=10
ONSITE_PUBLIC_CREATE_WINDOW_SECONDS=600
```

## Step 4: Writable folders

Make sure these exist and are writable:

- `instance/job_photos/`
- `instance/onsite_call_media/`
- `instance/profile_pictures/`
- `tmp/`

## Step 5: Install packages

Run:

```bash
pip install -r requirements.txt
```

## Step 6: Restart Passenger

After upload and env setup, restart Passenger.

If needed, touch:

```text
tmp/restart.txt
```

## Step 7: Quick smoke test after deploy

Check these one by one:

1. `/login`
2. login works
3. create one job
4. create one quotation
5. create one SYSCARE entry
6. create one onsite public request
7. create one internal lead

## Step 8: What to watch after go-live

Watch for these in the first hour:

- slow loading on `/new-job`, `/quotation/new`, `/syscare-new`
- 500 errors
- DB pool or connection errors in logs
- repeated Passenger restarts

If you see DB errors first, reduce Passenger process count before increasing `DB_POOL_SIZE` further.