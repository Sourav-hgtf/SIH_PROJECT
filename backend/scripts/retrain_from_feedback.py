"""Run the periodic active-learning calibration job.

Schedule this command through the deployment platform (for example nightly)
after enough analyst feedback has accumulated.
"""

from app.database import SessionLocal
from app.training import run_feedback_calibration


def main() -> None:
    db = SessionLocal()
    try:
        try:
            run = run_feedback_calibration(db)
        except ValueError as exc:
            print(f"Retraining skipped: {exc}")
            return
        db.commit()
        print(f"Created {run.model_version} from {run.feedback_count} analyst-reviewed reports")
    finally:
        db.close()


if __name__ == "__main__":
    main()
