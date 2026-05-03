import os

import mysql.connector
from datetime import date


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


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": _load_db_password(),
    "database": os.getenv("DB_NAME", "crm_system"),
}

def update_expiry_days_and_alerts():
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    # 1. Alert: 6 months completed (182 days left)
    cur.execute(
        """
        SELECT syscare_id, customer_name, contact_number, branch_name
        FROM syscare_memberships
        WHERE DATEDIFF(expiry_date, CURDATE()) = 182
        """
    )
    six_months = cur.fetchall()
    if six_months:
        print('6 months completed (alert):')
        for row in six_months:
            print(row)

    # 2. Alert: 1 month or less left (<=30 days)
    cur.execute(
        """
        SELECT syscare_id, customer_name, contact_number, branch_name,
               DATEDIFF(expiry_date, CURDATE()) AS expire_within_days
        FROM syscare_memberships
        WHERE DATEDIFF(expiry_date, CURDATE()) <= 30
          AND DATEDIFF(expiry_date, CURDATE()) > 0
        """
    )
    one_month = cur.fetchall()
    if one_month:
        print('1 month or less left (reminder):')
        for row in one_month:
            print(row)

    cur.close()
    conn.close()

if __name__ == "__main__":
    update_expiry_days_and_alerts()
