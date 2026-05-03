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

# New columns to add
new_cols = {
    'alt_no': 'VARCHAR(20) NULL',
    'email': 'VARCHAR(100) NULL',
    'location': 'VARCHAR(100) NULL',
    'address': 'TEXT NULL',
    'pin_code': 'VARCHAR(10) NULL',
    'received_by': 'VARCHAR(50) NULL',
    'assigned_engineer': 'VARCHAR(50) NULL',
    'estimate_amount': 'DECIMAL(10,2) NULL',
    'accessories_received': 'TEXT NULL',
    'engineer_remarks': 'TEXT NULL',
    'photo': 'VARCHAR(255) NULL'
}

cur.execute('SHOW COLUMNS FROM jobs')
existing_cols = [r[0] for r in cur.fetchall()]

for col, definition in new_cols.items():
    if col not in existing_cols:
        print(f'Adding column {col}')
        cur.execute(f"ALTER TABLE jobs ADD COLUMN `{col}` {definition}")
        conn.commit()
    else:
        print(f'Already has {col}')

cur.close()
conn.close()
