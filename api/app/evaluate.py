"""Evaluation harness: run every student profile through the buddy and check each plan.

Checklist per profile (the product's evaluation process):
  valid            the deterministic validator finds no violation (prerequisites, offerings, slots,
                   credit headroom, weekly hours, not-together pairs, eligibility, backlogs first)
  catalog_only     every recommended course exists in the knowledge base (cited by code)
  goal_coverage    every goal-skill gap is addressed by a course, an open resource or practice
  active_practice  every plan with gaps contains hands-on activities, not only passive content
  no_repeats       nothing already completed or mastered is assigned again
  explained        every recommended course carries a reason
  deterministic    planning twice gives an identical plan
  adapts           a weak quiz on a gap skill changes the plan differently from a strong one
  override         rejecting a recommended course yields a valid plan without it

Usage: python -m app.evaluate [--out ../docs/evaluation-report.md]
"""
import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import build_view, load_catalog
from app.mastery import Observation, compute_mastery, load_bkt_config, student_observations
from app.models import Student
from app.planner import build_plan, validate

CHECKS = ["valid", "catalog_only", "goal_coverage", "active_practice", "no_repeats", "explained", "deterministic", "adapts", "override"]


def _codes(plan: dict) -> list[str]:
    return [c for s in plan["semesters"] for c in s["course_codes"]]


def evaluate_student(db: Session, cat, student: Student) -> dict:
    view = build_view(db, student, cat)
    plan = build_plan(cat, view)
    result = {"id": student.id, "persona": student.persona, "goal": view.goal_id, "semester": view.current_semester, "failures": []}
    violations = validate(cat, view, plan["semesters"])
    checks = {"valid": not violations}
    if violations:
        result["failures"].append(f"valid: {violations[:3]}")
    checks["catalog_only"] = all(c in cat.courses for c in _codes(plan))
    gaps = plan["summary"]["gaps"]
    addressed = set(plan["summary"]["coverage"])
    for s in plan["semesters"]:
        addressed |= {r["skill_id"] for r in s["resources"]} | {a["skill_id"] for a in s["activities"] if a.get("skill_id")}
    missing = [g["skill_id"] for g in gaps if g["skill_id"] not in addressed]
    flagged = set(plan["summary"].get("unaddressed", []))
    # A gap passes if it is addressed, or if the plan says clearly that it cannot fit and offers the best option.
    checks["goal_coverage"] = all(s in flagged for s in missing) and (not missing or any("Best options" in n for n in plan["summary"]["notes"]))
    result["coverage_rate"] = 1.0 if not gaps else round(1 - len(missing) / len(gaps), 3)
    if missing:
        result["infeasible_flagged"] = missing
    if not checks["goal_coverage"]:
        result["failures"].append(f"goal_coverage: {missing} not addressed and not flagged")
    has_activity = any(s["activities"] for s in plan["semesters"])
    checks["active_practice"] = has_activity or not gaps
    threshold = cat.config["mastery_threshold"]
    repeats = [c for c in _codes(plan) if c in view.done and c not in view.backlogs]
    repeats += [r["title"] for s in plan["semesters"] for r in s["resources"] if view.mastery.get(r["skill_id"], 0) >= threshold]
    checks["no_repeats"] = not repeats
    checks["explained"] = all(item.get("reason") for s in plan["semesters"] for item in s["courses"]) and bool(plan["rationale"])
    checks["deterministic"] = json.dumps(build_plan(cat, view), sort_keys=True) == json.dumps(plan, sort_keys=True)
    # Adaptation: strong vs weak mid-semester quiz on the first gap skill.
    if gaps:
        skill = gaps[0]["skill_id"]
        base = student_observations(db, student, load_bkt_config())
        outcomes = []
        for value in (0.95, 0.1):
            mastery, _ = compute_mastery(base + [Observation(skill, "quiz", value, 4)], list(cat.skills), cat.config)
            misses = dict(view.misses)
            if value < 0.5:
                misses[skill] = misses.get(skill, 0) + 4
            v2 = view.evolve(mastery=mastery, misses=misses, tested=view.tested | {skill})
            p2 = build_plan(cat, v2)
            outcomes.append(json.dumps(p2["semesters"], sort_keys=True))
            if validate(cat, v2, p2["semesters"]):
                result["failures"].append(f"adapts: invalid plan after simulated quiz {value}")
        checks["adapts"] = outcomes[0] != outcomes[1]
    else:
        checks["adapts"] = True
    codes = [c for c in _codes(plan) if c not in view.backlogs]
    if codes:
        v3 = view.evolve(excluded=view.excluded | {codes[0]})
        p3 = build_plan(cat, v3)
        checks["override"] = codes[0] not in _codes(p3) and not validate(cat, v3, p3["semesters"])
    else:
        checks["override"] = True
    result["checks"] = checks
    result["summary"] = {"courses": len(codes), "gaps": len(gaps), "activities": sum(len(s["activities"]) for s in plan["semesters"]),
                         "resources": sum(len(s["resources"]) for s in plan["semesters"]), "notes": plan["summary"]["notes"][:2]}
    for name, ok in checks.items():
        if not ok and not any(f.startswith(name) for f in result["failures"]):
            result["failures"].append(name)
    return result


def evaluate_all(db: Session) -> dict:
    cat = load_catalog(db)
    rows = [evaluate_student(db, cat, s) for s in db.scalars(select(Student).order_by(Student.id)).all()]
    totals = {name: sum(1 for r in rows if r["checks"].get(name)) for name in CHECKS}
    gaps_total = sum(r["summary"]["gaps"] for r in rows)
    addressed = sum(r["summary"]["gaps"] * r["coverage_rate"] for r in rows)
    return {"profiles": len(rows), "pass_counts": totals, "all_passed": sum(1 for r in rows if all(r["checks"].values())),
            "gap_coverage_rate": round(addressed / gaps_total, 3) if gaps_total else 1.0,
            "infeasible_flagged": [{"id": r["id"], "skills": r["infeasible_flagged"]} for r in rows if r.get("infeasible_flagged")],
            "failures": [r for r in rows if r["failures"]], "rows": rows}


def write_report(result: dict, out: Path) -> None:
    n = result["profiles"]
    lines = ["# Evaluation report", "", "Generated by `python -m app.evaluate` over every seeded student profile.", "",
             f"Profiles evaluated: **{n}**; passing every check: **{result['all_passed']}**.", "", "| Check | Passed |", "|---|---|"]
    lines += [f"| {name} | {count}/{n} |" for name, count in result["pass_counts"].items()]
    lines += ["", f"Goal-skill gaps addressed by a course, resource or practice: **{result['gap_coverage_rate']:.1%}**. "
              "The rest are gaps the buddy explicitly reports as not fitting the student's time or eligibility, with the best valid option:"]
    lines += [f"- {r['id']}: {', '.join(r['skills'])}" for r in result["infeasible_flagged"]] or ["- none"]
    lines += ["", "## Check definitions", "", "```", __doc__.split("Checklist per profile (the product's evaluation process):")[1].split("Usage:")[0].rstrip(), "```", ""]
    if result["failures"]:
        lines += ["## Failures", ""] + [f"- {r['id']}: {'; '.join(r['failures'])}" for r in result["failures"]]
    lines += ["", "## Per-profile summary", "", "| Profile | Persona | Goal | Sem | Courses | Gaps | Activities | Resources |", "|---|---|---|---|---|---|---|---|"]
    for r in result["rows"]:
        s = r["summary"]
        lines.append(f"| {r['id']} | {r['persona']} | {r['goal']} | {r['semester']} | {s['courses']} | {s['gaps']} | {s['activities']} | {s['resources']} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    from app.db import Base, SessionLocal, engine
    from app.main import initialize_database

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    Base.metadata.create_all(bind=engine)
    initialize_database()
    with SessionLocal() as db:
        result = evaluate_all(db)
    print(json.dumps({k: v for k, v in result.items() if k in ("profiles", "pass_counts", "all_passed", "gap_coverage_rate", "infeasible_flagged")}, indent=2))
    for r in result["failures"][:20]:
        print(f"FAIL {r['id']}: {r['failures']}")
    if args.out:
        write_report(result, args.out)
        print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
