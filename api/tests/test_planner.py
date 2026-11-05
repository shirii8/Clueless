from pathlib import Path
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.catalog import build_view, load_catalog
from app.db import Base
from app.evaluate import evaluate_all
from app.mastery import Observation, compute_mastery, load_bkt_config, recompute_skill_state, update_mastery
from app.models import Evidence, Student
from app.planner import build_plan, validate
from app.services import parse_goal

SEED = Path(os.environ["SEED_DIR"])


@pytest.fixture(scope="module")
def db():
    from app.seed import load_seed

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    load_seed(session, SEED)
    for student in session.query(Student).all():
        recompute_skill_state(session, student.id)
    session.commit()
    yield session
    session.close()


def view_of(db, student_id, **changes):
    cat = load_catalog(db)
    view = build_view(db, db.get(Student, student_id), cat)
    return cat, view.evolve(**changes) if changes else view


def issues(cat, view, semesters):
    return " | ".join(validate(cat, view, semesters))


def test_validator_rejects_invalid_plans(db):
    # S1024: Chemical Engineering, semester 5, CGPA 7.8, 6-credit headroom, 8 h/week, 2 open-elective slots.
    cat, view = view_of(db, "S1024")
    sem = lambda n, *items: {"semester": n, "courses": [{"code": c, "slot": slot} for c, slot in items]}  # noqa: E731
    assert "missing prerequisite" in issues(cat, view, [sem(6, ("CS2L002", "additional"))])
    assert "not offered in Spring" in issues(cat, view, [sem(6, ("CS2L004", "additional"))])
    assert "headroom" in issues(cat, view, [sem(5, ("CS2L004", "additional"), ("CS3L005", "additional"))])
    assert "cannot be taken together" in issues(cat, view, [sem(5, ("CS2L001", "elective"), ("CS2L004", "elective"))])
    assert "Unknown course code" in issues(cat, view, [sem(5, ("CS9L999", "elective"))])
    assert "already completed" in issues(cat, view, [sem(5, ("CS1L001", "additional"))])
    assert "outside the remaining semesters" in issues(cat, view, [sem(3, ("CS2L004", "elective"))])
    assert "extra hours/week" in issues(cat, view, [{**sem(5), "resources": [{"id": "R1", "skill_id": "databases", "hours_per_week": 9}]}])
    assert "cannot use the lateral slot" in issues(cat, view, [sem(5, ("CS2L004", "lateral"))])


def test_eligibility_rules_follow_regulations(db):
    cat, view = view_of(db, "P-CH-MINOR-CUTOFF")  # CGPA 7.49: one hundredth below the additional-credit cut-off
    text = issues(cat, view, [{"semester": 5, "courses": [{"code": "CS2L004", "slot": "additional"}]}])
    assert "below the 7.50" in text
    plan = build_plan(cat, view)
    assert not validate(cat, view, plan["semesters"])
    assert not any(c["slot"] == "additional" for s in plan["semesters"] for c in s["courses"])
    assert any("Minor" in n and "Best valid option" in n for n in plan["summary"]["notes"])
    # Non-CSE student without declared open-elective slots cannot put a CSE core subject in an elective slot.
    cat, view = view_of(db, "P-CHE-SWE")
    assert "elective slots used, only 0" in issues(cat, view, [{"semester": 3, "courses": [{"code": "CS2L004", "slot": "elective"}]}])


def test_backlogs_are_registered_first_and_block_additional_credits(db):
    cat, view = view_of(db, "P-CSE-BACKLOG")
    plan = build_plan(cat, view)
    assert not validate(cat, view, plan["semesters"])
    first = plan["semesters"][0]
    assert {"CS2L002", "MA2L006"} <= set(first["course_codes"])
    assert all(c["slot"] != "additional" for s in plan["semesters"] for c in s["courses"])
    moved = [{**s, "courses": [c for c in s["courses"] if c["code"] != "CS2L002"],
              "course_codes": [c for c in s["course_codes"] if c != "CS2L002"]} for s in plan["semesters"]]
    assert "must be registered in semester 6" in issues(cat, view, moved)


def test_never_assigns_mastered_content(db):
    cat, view = view_of(db, "S1024")
    mastered = {**view.mastery, "data_structures": 0.97, "algorithms": 0.96}
    v2 = view.evolve(mastery=mastered, tested=view.tested | {"data_structures", "algorithms"})
    assert "already-mastered" in issues(cat, v2, [{"semester": 5, "courses": [{"code": "CS6L007", "slot": "elective"}]}])
    plan = build_plan(cat, v2)
    assert not validate(cat, v2, plan["semesters"])
    codes = {c for s in plan["semesters"] for c in s["course_codes"]}
    assert "CS6L007" not in codes
    assert not any(r["skill_id"] in ("data_structures", "algorithms") for s in plan["semesters"] for r in s["resources"])


def test_s1024_sequence_and_limits(db):
    cat, view = view_of(db, "S1024")
    plan = build_plan(cat, view)
    order = {c: s["semester"] for s in plan["semesters"] for c in s["course_codes"]}
    assert order["CS2L004"] < order["CS2L002"], "data structures before algorithms"
    assert order["CS2L002"] <= min(order.get("CS3L003", 9), order.get("CS3L005", 9)), "DSA before databases and OS"
    for s in plan["semesters"]:
        assert s["load"]["additional_credits"] <= 6 and s["load"]["extra_hours"] <= 8
        assert not {"CS2L001", "CS2L004"} <= set(s["course_codes"])
    assert all(c["reason"] for s in plan["semesters"] for c in s["courses"])


def test_bkt_evidence_weighting():
    config = load_bkt_config(SEED / "bkt.json")
    assert update_mastery(0.3, 1, "assessed", config) > 0.3
    assert update_mastery(0.3, 0, "assessed", config) < 0.3
    value = 0.2
    for _ in range(100):
        value = update_mastery(value, 1, "self_declared", config)
    assert value < 0.5, "self-declared evidence stays weak"
    first_try = update_mastery(0.4, 1, "quiz", config, attempts=1)
    third_try = update_mastery(0.4, 1, "quiz", config, attempts=3)
    assert first_try > third_try > 0.4, "needing more attempts is weaker evidence"
    grades_only, _ = compute_mastery([Observation("algorithms", "grade", 1.0, 1, 1, 1.0)] * 10, ["algorithms"], config)
    assert grades_only["algorithms"] < config["mastery_threshold"], "completing courses is not demonstrated proficiency"
    tested, meta = compute_mastery([Observation("algorithms", "quiz", 1.0, 6)], ["algorithms"], config)
    assert tested["algorithms"] >= config["mastery_threshold"] and meta["algorithms"]["tested"]


def test_repeated_misses_trigger_remediation(db):
    cat, view = view_of(db, "P-CE-DS-MISMATCH")
    weak = view.evolve(misses={**view.misses, "linear_algebra": 3}, missed_topics={"linear_algebra": ["rank"]})
    plan = build_plan(cat, weak)
    first = plan["semesters"][0]
    assert any(m["skill_id"] == "linear_algebra" for m in first["review_modules"])
    assert any("repeated misses" in r["reason"] or "Prerequisite refresher" in r["reason"] for r in first["resources"])
    assert not validate(cat, weak, plan["semesters"])


def test_strong_and_weak_quiz_change_the_plan_differently(db):
    cat, view = view_of(db, "S1024")
    config = cat.config
    from app.mastery import student_observations

    base = student_observations(db, db.get(Student, "S1024"), config)
    plans = {}
    for label, value in (("strong", 0.95), ("weak", 0.05)):
        mastery, _ = compute_mastery(base + [Observation("data_structures", "quiz", value, 5)], list(cat.skills), config)
        misses = {**view.misses, "data_structures": 5} if value < 0.5 else view.misses
        v2 = view.evolve(mastery=mastery, misses=misses, tested=view.tested | {"data_structures"})
        plans[label] = build_plan(cat, v2)
        assert not validate(cat, v2, plans[label]["semesters"])
    strong = plans["strong"]
    # CS2L004 may stay only as the institute prerequisite of CS2L002; data-structures content itself is not re-assigned.
    for s in strong["semesters"]:
        for c in s["courses"]:
            if c["code"] == "CS2L004":
                assert "Prerequisite for CS2L002" in c["reason"]
        assert not any(x.get("skill_id") == "data_structures" for x in s["resources"] + s["activities"])
    assert "data_structures" not in {g["skill_id"] for g in strong["summary"]["gaps"]}
    assert plans["weak"]["semesters"][0]["review_modules"], "weak result adds review modules"


def test_goal_parsing_clarifies_vague_goals(db):
    cat = load_catalog(db)
    assert parse_goal(cat, "I want to crack GATE and do an M.Tech")["goal_id"] == "gate"
    assert parse_goal(cat, "Preparing for UPSC civil services")["goal_id"] == "upsc"
    vague = parse_goal(cat, "I want to be successful")
    assert vague["goal_id"] is None and vague["clarifying_question"] and vague["options"]


def test_planning_is_deterministic(db):
    cat, view = view_of(db, "P-EE-MS")
    assert build_plan(cat, view) == build_plan(cat, view)


def test_every_profile_passes_the_evaluation_checklist(db):
    result = evaluate_all(db)
    assert result["profiles"] >= 70
    assert result["all_passed"] == result["profiles"], result["failures"][:5]
    assert result["gap_coverage_rate"] > 0.95


def test_module_completion_does_not_raise_mastery(db):
    student = db.get(Student, "P-CHE-SWE")
    before = recompute_skill_state(db, student.id)["data_structures"]
    db.add(Evidence(id="EV-TEST-MOD", student_id=student.id, skill_id="data_structures", kind="module_completion", value=1.0))
    db.flush()
    assert recompute_skill_state(db, student.id)["data_structures"] == before
    db.rollback()
