# Namecheap cPanel Deploy Steps

Use the contents of this `deploy` folder for cPanel/Passenger hosting.

## 1. Create cPanel database

In Namecheap cPanel:

- Create a MySQL database
- Create a MySQL user
- Assign the user to the database with all privileges

Keep these exact values:

- `DB_HOST`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`

On cPanel these names are usually prefixed, for example `cpaneluser_crmdb`.

## 2. Create the Python app

In cPanel:

- Open `Setup Python App`
- Choose Python `3.10+` if available
- Set the application root to the folder where you upload this bundle
- Set the application URL to your domain or subdomain
- Set the startup file to `passenger_wsgi.py`
- Set the application entry point to `application`

## 3. Upload files

Upload the full contents of this `deploy` folder to the application root.

Required items include:

- `app.py`
- `passenger_wsgi.py`
- `requirements.txt`
- `templates/`
- `static/`
- `instance/`
- `tmp/`

## 4. Install packages

Inside cPanel Python App or the app virtualenv terminal, run:

```bash
pip install -r requirements.txt
```

## 5. Set environment variables

In `Setup Python App` -> `Environment Variables`, set at least:

- `DB_HOST=localhost`
- `DB_NAME=your_cpanel_db_name`
- `DB_USER=your_cpanel_db_username`
- `DB_PASSWORD=your_cpanel_db_password`
- `SECRET_KEY=use_a_long_random_secret`
- `APP_DEBUG=0`
- `SESSION_COOKIE_SECURE=1`
- `CSRF_ENFORCE_ALL_POSTS=1`

Recommended:

- `DB_POOL_SIZE=24`
- `DB_POOL_ACQUIRE_TIMEOUT_SECONDS=20`
- `MAX_UPLOAD_REQUEST_MB=50`
- `ONSITE_PUBLIC_CREATE_LIMIT=10`
- `ONSITE_PUBLIC_CREATE_WINDOW_SECONDS=600`

If your hosting panel exposes Passenger process or worker controls, start conservatively so the total database connections stay within MySQL limits. As a rule of thumb, total app processes × `DB_POOL_SIZE` should match what your hosting database can actually sustain.

For a 60-user target, use these practical rules:

- Start with `DB_POOL_SIZE=24` and do not set it above `32`, because the mysql connector pool has a hard cap.
- Keep Passenger app processes conservative at first. One process with `DB_POOL_SIZE=24` is safer than multiple processes that can collectively exhaust MySQL connections.
- If your host enables multiple Passenger processes, make sure total possible DB connections stay realistic for the database plan. Example: `2 processes × 24 pool size = 48 possible DB connections`.
- Keep `APP_DEBUG=0` in hosting.
- Restart Passenger after every code or environment variable change.

## 6. Secret files

This bundle includes `instance/db_password` and `instance/secret_key` support, but for cPanel it is better to use environment variables.

If you use environment variables, make sure uploaded secret files do not contain old local credentials.

## 7. Writable folders

Make sure these folders exist and are writable by the Python app:

- `instance/job_photos/`
- `instance/onsite_call_media/`
- `instance/profile_pictures/`
- `tmp/`

## 8. Restart Passenger

After upload or code changes, restart the app from cPanel.

If needed, touch or update:

- `tmp/restart.txt`

## 9. If sub-pages return 404

Open `.htaccess` and uncomment the rewrite block.

## 10. Smoke test after deploy

Check these in browser:

- `/login`
- login works
- create one job
- close one job
- create one quotation
- create one SYSCARE entry

If all of those work, the cPanel deploy is basically healthy.

## 11. Pre-host 60-user checklist

Run these in the local project before upload:

```bash
f:/service-crm/.venv/Scripts/python.exe tests/pre_host_load_runner.py --users 60
f:/service-crm/.venv/Scripts/python.exe tests/pre_host_load_runner.py --users 60 --json
```

Pass criteria:

- Jobs: `60/60`
- Quotations: `60/60`
- SYSCARE: `60/60`
- Onsite public: `60/60`
- Onsite internal: `60/60`
- Internal lead: `60/60`

If jobs, quotations, or SYSCARE fail first while onsite still passes, the usual cause is DB connection pressure, not numbering logic.

## 12. Post-deploy watch list

Right after go-live, monitor these first:

- Slow page loads on `/new-job`, `/quotation/new`, and `/syscare-new`
- 500 errors during parallel create activity
- MySQL connection limit or pool exhaustion errors in app logs
- Repeated Passenger restarts or process kills

If any of those appear, lower Passenger process count first before raising DB pool size further.