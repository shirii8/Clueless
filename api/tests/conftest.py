import os
import tempfile
from pathlib import Path

# Point the app at a throwaway SQLite database before app.db is imported, and never at a model.
_tmp = Path(tempfile.mkdtemp(prefix="clueless-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["LLM_API_KEY"] = ""
os.environ.setdefault("SEED_DIR", str(Path(__file__).resolve().parents[2] / "data" / "seed"))
