import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base, engine
from app.migrations import run_labeling_migrations, run_lsr_migrations, run_recommendation_migrations

Base.metadata.create_all(bind=engine)
run_lsr_migrations(engine)
run_recommendation_migrations(engine)
run_labeling_migrations(engine)
