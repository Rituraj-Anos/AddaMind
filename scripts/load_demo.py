"""Load the synthetic demo into a fresh "Suman" project: python -m scripts.load_demo [--reset]

--reset deletes the existing database and media folder first.
"""
import shutil
import sys
import time
from pathlib import Path

from backend.chatintel import db, ingest

DEMO = Path(__file__).resolve().parents[1] / "data" / "demo"
CHATS = ["WhatsApp Chat with College Friends.zip", "WhatsApp Chat - Shrimant.zip"]


def main(reset: bool) -> None:
    if reset:
        for p in ["addamind.db", "addamind.db-wal", "addamind.db-shm"]:
            (db.data_dir() / p).unlink(missing_ok=True)
        shutil.rmtree(db.data_dir() / "projects", ignore_errors=True)
        db._ready.clear()
    pid = db.create_project("Suman")["id"]
    for name in CHATS:
        t = time.time()
        job_id = ingest.create_job(pid, name)
        with open(DEMO / name, "rb") as f:
            ingest.save_upload(f, pid, job_id)
        ingest.run_job(pid, job_id)
        job = db.get_job(pid, job_id)
        print(f"{name}: {job['status']} in {time.time() - t:.1f}s {job['error'] or ''}")
        print("   ", {k: v for k, v in job["info"].items() if k != "months"})
    print(f"project {pid}")


if __name__ == "__main__":
    main("--reset" in sys.argv)
