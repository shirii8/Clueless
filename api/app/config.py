import json
import os
from functools import lru_cache
from pathlib import Path


def seed_dir() -> Path:
    configured = os.getenv("SEED_DIR")
    if configured:
        return Path(configured)
    here = Path(__file__).resolve()
    for candidate in (here.parents[2] / "data" / "seed", here.parents[1] / "data" / "seed"):
        if candidate.exists():
            return candidate
    return here.parents[2] / "data" / "seed"


@lru_cache(maxsize=4)
def _load_bkt(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def bkt_config(path: Path | None = None) -> dict:
    return _load_bkt(str(path or seed_dir() / "bkt.json"))


MAX_SEMESTER = 8
LEVEL_TARGETS = {1: 0.70, 2: 0.80, 3: 0.85}


def level_target(level: int) -> float:
    return LEVEL_TARGETS.get(int(level), 0.85)


def season_of(semester: int) -> str:
    return "Autumn" if semester % 2 == 1 else "Spring"
