"""Restore the original seed state: drop every table, recreate, reload data/seed and rebuild plans.

Usage: docker compose run --rm api python -m app.reset   (or: make reset)
"""
from app.config import seed_dir
from app.db import Base, SessionLocal, engine
from app import models  # noqa: F401  (registers tables)
from app.models import Student
from app.seed import load_seed
from app.services import reprocess_student
from sqlalchemy import select


def reset_database() -> list[str]:
    engine.dispose()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        report = load_seed(db, seed_dir())
        students = db.scalars(select(Student)).all()
        for student in students:
            reprocess_student(db, student, "seed", use_llm=False)
        report.append(f"plans: rebuilt and validated for {len(students)} students")
    return report


def main() -> None:
    for line in reset_database():
        print(line)
    print("Seed state restored.")


if __name__ == "__main__":
    main()
