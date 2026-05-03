import os

import mysql.connector


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_db_password():
    configured_password = os.getenv("DB_PASSWORD", "").strip()
    if configured_password:
        return configured_password
    password_file = os.getenv("DB_PASSWORD_FILE", "").strip() or os.path.join(BASE_DIR, "instance", "db_password")
    if os.path.exists(password_file):
        with open(password_file, "r", encoding="utf-8") as password_handle:
            return password_handle.read().strip()
    return ""


conn = mysql.connector.connect(
    host=os.getenv("DB_HOST", "localhost"),
    user=os.getenv("DB_USER", "root"),
    password=_load_db_password(),
    database=os.getenv("DB_NAME", "crm_system")
)
cur = conn.cursor()
cur.execute('SHOW CREATE TABLE dropdown_options')
print(cur.fetchone())
cur.close()
conn.close()
