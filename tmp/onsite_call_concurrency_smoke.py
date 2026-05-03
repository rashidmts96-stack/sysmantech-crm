from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app
from onsite_calls_blueprint import OnsiteCall, OnsiteCallLog, OnsiteCallNote


def build_payload(index):
    return {
        "customer_name": f"Load Test Customer {index}",
        "phone": f"989500{index:04d}",
        "location": f"Area {index}",
        "district": "Ernakulam",
        "complaint_type": "Laptop",
        "preferred_service": "Onsite",
        "priority": "Flexible",
        "preferred_datetime": (datetime.now(UTC) + timedelta(hours=index + 1)).strftime("%Y-%m-%dT%H:%M"),
        "device_model": f"Demo-{index}",
        "complaint_description": "Concurrent smoke test request",
    }


def main():
    service = app.extensions["onsite_calls_service"]
    created_ids = []

    def worker(index):
        call_id, errors = service.create_public_call(build_payload(index))
        if errors:
            raise RuntimeError(", ".join(errors))
        return call_id

    try:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, index) for index in range(10)]
            for future in as_completed(futures):
                created_ids.append(future.result())

        if len(created_ids) != 10 or len(set(created_ids)) != 10:
            raise RuntimeError(f"Expected 10 unique calls, got: {created_ids}")

        created_ids.sort()
        print("Concurrent create smoke test passed")
        print("Created call ids:", created_ids)
    finally:
        if created_ids:
            with service.session_scope() as db_session:
                db_session.query(OnsiteCallNote).filter(OnsiteCallNote.call_id.in_(created_ids)).delete(
                    synchronize_session=False
                )
                db_session.query(OnsiteCallLog).filter(OnsiteCallLog.call_id.in_(created_ids)).delete(
                    synchronize_session=False
                )
                db_session.query(OnsiteCall).filter(OnsiteCall.id.in_(created_ids)).delete(
                    synchronize_session=False
                )


if __name__ == "__main__":
    main()
