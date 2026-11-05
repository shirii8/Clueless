"""Bayesian Knowledge Tracing with evidence reliability.

Each evidence item is a soft observation: a score v in [0, 1] mixes the "correct" and "incorrect"
BKT posteriors, the learning transition is applied, and the result is blended with the prior by the
reliability of the evidence kind. Self-declared evidence can only set a weak prior that stays below
mastery. Course grades are converted into evidence for the skills a course covers, weighted by how
deeply the course covers each skill, so completing a course is never treated as proven mastery.
"""
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import bkt_config
from app.models import CourseSkill, Evidence, Skill, SkillState, Student


def load_bkt_config(path: Path | None = None) -> dict:
    return bkt_config(path)


@dataclass
class Observation:
    skill_id: str
    kind: str
    value: float
    items: int = 1
    attempts: int = 1
    weight: float = 1.0
    source: str = ""


def update_mastery(prior: float, value: float, kind: str, config: dict, attempts: int = 1, weight: float = 1.0) -> float:
    if kind not in config["reliability"]:
        raise ValueError(f"Unsupported evidence kind: {kind}")
    if not 0 <= value <= 1:
        raise ValueError("Evidence value must be between 0 and 1")
    reliability = config["reliability"][kind] * max(0.0, min(1.0, weight))
    if kind == "self_declared":
        cap = config.get("self_declared_cap", 0.49)
        weak_prior = min(value * 0.4, cap)
        return min(cap, prior * (1 - reliability) + weak_prior * reliability) if prior < cap else prior
    if reliability == 0:
        return prior
    # Needing several attempts is weaker evidence of proficiency than a first-try answer.
    penalty = config.get("attempt_penalty", 0.15) * max(0, attempts - 1)
    value = max(0.0, value * (1 - min(penalty, 0.6)))
    slip, guess = config["p_slip"], config["p_guess"]
    correct = prior * (1 - slip) / (prior * (1 - slip) + (1 - prior) * guess)
    incorrect = prior * slip / (prior * slip + (1 - prior) * (1 - guess))
    posterior = value * correct + (1 - value) * incorrect
    learned = posterior + (1 - posterior) * config["p_learn"]
    return prior * (1 - reliability) + learned * reliability


def grade_observations(db: Session, student: Student, config: dict) -> list[Observation]:
    points = config.get("grade_points", {})
    coverage: dict[str, list[tuple[str, int]]] = {}
    for code, skill_id, level in db.execute(select(CourseSkill.course_code, CourseSkill.skill_id, CourseSkill.level)):
        coverage.setdefault(code, []).append((skill_id, level))
    observations = []
    for item in student.completed_courses or []:
        grade = (item.get("grade") or "").upper()
        if grade not in points:
            continue
        for skill_id, level in coverage.get(item.get("code"), []):
            observations.append(Observation(skill_id, "grade", points[grade] / 10, weight=level / 3, source=f"grade:{item['code']}:{grade}"))
    return observations


def compute_mastery(
    observations: list[Observation], skill_ids: list[str], config: dict
) -> tuple[dict[str, float], dict[str, dict]]:
    values = {skill_id: config["p_init"] for skill_id in skill_ids}
    meta: dict[str, dict] = {skill_id: {"count": 0, "tested": False, "sources": set()} for skill_id in skill_ids}
    tested_kinds = set(config.get("tested_kinds", []))
    for obs in observations:
        if obs.skill_id not in values:
            continue
        for _ in range(max(1, obs.items)):
            values[obs.skill_id] = update_mastery(values[obs.skill_id], obs.value, obs.kind, config, obs.attempts, obs.weight)
        info = meta[obs.skill_id]
        info["count"] += 1
        info["sources"].add(obs.kind)
        if obs.kind in tested_kinds:
            info["tested"] = True
    # Untested skills can never reach mastery: only tested evidence demonstrates proficiency.
    threshold = config["mastery_threshold"]
    for skill_id, info in meta.items():
        if not info["tested"] and values[skill_id] >= threshold:
            values[skill_id] = threshold - 0.01
    return values, meta


def student_observations(db: Session, student: Student, config: dict, extra: list[Observation] | None = None) -> list[Observation]:
    observations = grade_observations(db, student, config)
    for item in db.scalars(
        select(Evidence).where(Evidence.student_id == student.id).order_by(Evidence.created_at, Evidence.id)
    ).all():
        observations.append(Observation(item.skill_id, item.kind, item.value, item.items, item.attempts, 1.0, item.source))
    return observations + list(extra or [])


def recompute_skill_state(db: Session, student_id: str, config: dict | None = None) -> dict[str, float]:
    config = config or load_bkt_config()
    student = db.get(Student, student_id)
    skill_ids = list(db.scalars(select(Skill.id)).all())
    values, meta = compute_mastery(student_observations(db, student, config), skill_ids, config)
    db.execute(delete(SkillState).where(SkillState.student_id == student_id))
    for skill_id, probability in values.items():
        info = meta[skill_id]
        db.add(SkillState(student_id=student_id, skill_id=skill_id, p_mastery=round(probability, 4),
                          evidence_count=info["count"], tested=info["tested"], sources=sorted(info["sources"])))
    db.flush()
    return {key: round(value, 4) for key, value in values.items()}


def hypothetical_mastery(db: Session, student: Student, extra: list[Observation]) -> dict[str, float]:
    config = load_bkt_config()
    skill_ids = list(db.scalars(select(Skill.id)).all())
    values, _ = compute_mastery(student_observations(db, student, config, extra), skill_ids, config)
    return {key: round(value, 4) for key, value in values.items()}
