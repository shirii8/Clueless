"""Explanations computed deterministically from evidence: what the student knows, their gaps,
interest-vs-evidence mismatches, goal readiness, alternative goals and next actions."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import Catalog, StudentView, additional_eligible
from app.config import level_target
from app.models import Assessment, Evidence, SkillState

RELIABILITY_LABEL = {
    "grade": "course grade", "assessed": "assessed diagnostic", "mock_test": "timed mock test", "quiz": "quiz",
    "exercise": "graded exercise", "project": "graded project", "mock_interview": "mock interview",
    "self_declared": "self-declared", "module_completion": "module completion",
}
STRENGTH_ORDER = ["mock_test", "assessed", "project", "grade", "exercise", "quiz", "mock_interview", "self_declared", "module_completion"]


def evidence_strength(sources: list[str]) -> str:
    tested = {"mock_test", "assessed", "project", "exercise", "quiz", "mock_interview"}
    if set(sources) & tested:
        return "strong (tested)"
    if "grade" in sources:
        return "moderate (course grade only)"
    if "self_declared" in sources:
        return "weak (self-declared)"
    return "none"


def skill_rows(db: Session, cat: Catalog, view: StudentView) -> list[dict]:
    states = {s.skill_id: s for s in db.scalars(select(SkillState).where(SkillState.student_id == view.id)).all()}
    threshold = cat.config["mastery_threshold"]
    rows = []
    for skill_id, skill in cat.skills.items():
        state = states.get(skill_id)
        p = view.mastery.get(skill_id, cat.config["p_init"])
        sources = state.sources if state else []
        level = view.target_skills.get(skill_id)
        target = level_target(level) if level else None
        status = ("mastered" if p >= threshold else "meets goal target" if target and p >= target
                  else "gap" if target else "in progress" if sources else "no evidence")
        rows.append({
            "skill_id": skill_id, "name": skill["name"], "category": skill["category"], "p_mastery": round(p, 3),
            "mastered": p >= threshold, "goal_level": level, "target": target, "status": status,
            "evidence": evidence_strength(sources), "sources": [RELIABILITY_LABEL.get(s, s) for s in sorted(sources, key=lambda s: STRENGTH_ORDER.index(s) if s in STRENGTH_ORDER else 99)],
            "evidence_count": state.evidence_count if state else 0, "interest": skill_id in view.interests,
            "missed": view.misses.get(skill_id, 0), "missed_topics": view.missed_topics.get(skill_id, []),
        })
    return rows


def mismatches(db: Session, cat: Catalog, view: StudentView) -> list[dict]:
    """Interest or goal that the tested evidence does not support yet - surfaced, never ignored."""
    found = []
    self_declared = {e.skill_id: e.value for e in db.scalars(select(Evidence).where(
        Evidence.student_id == view.id, Evidence.kind == "self_declared")).all()}
    for skill_id in set(view.interests) | set(self_declared):
        p = view.mastery.get(skill_id, 0)
        if skill_id in view.tested and p < 0.5:
            found.append({"skill_id": skill_id, "kind": "interest_vs_evidence",
                          "message": f"You listed {cat.skills[skill_id]['name']} as an interest or strength, but tested evidence puts it at {p:.0%}."})
    for skill_id, level in view.target_skills.items():
        p = view.mastery.get(skill_id, 0)
        if skill_id in view.tested and p < 0.4 and level >= 2:
            prereqs = [cat.skills[s]["name"] for s in cat.skill_prereqs.get(skill_id, []) if view.mastery.get(s, 0) < 0.6]
            extra = f" It builds on {', '.join(prereqs)}, which also need work." if prereqs else ""
            found.append({"skill_id": skill_id, "kind": "goal_vs_evidence",
                          "message": f"Your goal needs {cat.skills[skill_id]['name']} at level {level}, but your tested score is {p:.0%}.{extra} "
                                     "The plan adds work to close this; you may also want to compare related goals below."})
    return found


def goal_fit(cat: Catalog, view: StudentView) -> list[dict]:
    rows = []
    for goal in cat.goals.values():
        targets = goal["target_skills"]
        ratios = [min(1.0, view.mastery.get(s, 0) / level_target(l)) for s, l in targets.items()]
        fit = sum(ratios) / len(ratios) if ratios else 0
        gaps = [cat.skills[s]["name"] for s, l in targets.items() if view.mastery.get(s, 0) < level_target(l)]
        rows.append({"goal_id": goal["id"], "name": goal["name"], "fit": round(fit, 3), "gaps": gaps, "current": goal["id"] == view.goal_id})
    rows.sort(key=lambda r: -r["fit"])
    return rows


def readiness(db: Session, cat: Catalog, view: StudentView) -> dict:
    goal = cat.goals.get(view.goal_id or "")
    if not goal:
        return {"goal": view.goal_name, "ready": False, "criteria": [], "summary": "Choose a goal to see readiness criteria."}
    crit = goal["readiness"]
    criteria = []
    met_skills = [s for s, l in goal["target_skills"].items() if view.mastery.get(s, 0) >= level_target(l) and s in view.tested]
    needed = crit.get("skills_mastered_fraction", 0.75)
    total = len(goal["target_skills"])
    criteria.append({"name": "Goal skills demonstrated with tested evidence", "met": total > 0 and len(met_skills) / total >= needed,
                     "detail": f"{len(met_skills)} of {total} at target (need {needed:.0%})"})
    assessments = db.scalars(select(Assessment).where(Assessment.student_id == view.id)).all()
    if crit.get("mock_test"):
        tests = [a for a in assessments if a.kind == "mock_test" and a.status == "graded" and a.score is not None]
        within = [a for a in tests if not (a.details or {}).get("over_time")]
        best = max((a.score for a in within), default=None)
        mock_evidence = db.scalars(select(Evidence).where(Evidence.student_id == view.id, Evidence.kind == "mock_test")).all()
        if best is None and mock_evidence:
            best = max(e.value for e in mock_evidence)
        minimum = crit["mock_test"]["min_score"]
        criteria.append({"name": f"Timed mock test >= {minimum:.0%}", "met": best is not None and best >= minimum,
                         "detail": f"best {best:.0%}" if best is not None else "not taken yet"})
    if crit.get("projects"):
        graded = [a for a in assessments if a.kind == "project" and a.status == "graded" and (a.score or 0) >= 0.7]
        project_evidence = [e for e in db.scalars(select(Evidence).where(Evidence.student_id == view.id, Evidence.kind == "project")).all() if e.value >= 0.7]
        count = max(len(graded), len(project_evidence))
        criteria.append({"name": f"{crit['projects']} end-to-end project(s) passing the rubric", "met": count >= crit["projects"], "detail": f"{count} passed"})
    if crit.get("mock_interviews"):
        interviews = [a for a in assessments if a.kind == "mock_interview" and (a.score or 0) >= 0.6]
        evidence_iv = [e for e in db.scalars(select(Evidence).where(Evidence.student_id == view.id, Evidence.kind == "mock_interview")).all() if e.value >= 0.6]
        count = max(len(interviews), len(evidence_iv))
        criteria.append({"name": f"{crit['mock_interviews']} mock interview(s) cleared", "met": count >= crit["mock_interviews"], "detail": f"{count} cleared"})
    ready = all(c["met"] for c in criteria)
    unmet = [c["name"] for c in criteria if not c["met"]]
    return {"goal": goal["name"], "ready": ready, "criteria": criteria,
            "summary": "Ready: every criterion is backed by tested evidence." if ready else "Not yet: " + "; ".join(unmet) + "."}


def next_actions(db: Session, cat: Catalog, view: StudentView, plan: dict | None) -> list[dict]:
    actions = []
    untested = [s for s in view.target_skills if s not in view.tested]
    if untested:
        names = ", ".join(cat.skills[s]["name"] for s in untested[:3])
        actions.append({"kind": "diagnostic", "title": f"Take the short diagnostic for {names}",
                        "why": "These goal skills have no tested evidence yet, so the plan is working from weak signals."})
    for skill, count in sorted(view.misses.items(), key=lambda kv: -kv[1]):
        if count >= 2 and view.mastery.get(skill, 0) < view.target_for(skill):
            actions.append({"kind": "review", "title": f"Work through the review modules for {cat.skills[skill]['name']}",
                            "why": f"You missed {count} tested questions on it."})
            break
    if plan and plan.get("semesters"):
        first = plan["semesters"][0]
        for activity in first.get("activities", [])[:2]:
            actions.append({"kind": "practice", "title": activity["title"], "why": activity.get("reason", "")})
        for course in first.get("courses", [])[:2]:
            actions.append({"kind": "register", "title": f"Register for {course['code']} {course['title']} in semester {first['semester']}",
                            "why": course.get("reason", "")})
        for milestone in first.get("milestones", [])[:1]:
            actions.append({"kind": "milestone", "title": milestone["title"], "why": "Goal milestone for this semester."})
    ready = readiness(db, cat, view)
    if not ready["ready"]:
        for c in ready["criteria"]:
            if not c["met"] and "mock test" in c["name"].lower():
                actions.append({"kind": "mock_test", "title": "Take a timed mock test", "why": f"Readiness criterion: {c['name']} ({c['detail']})."})
                break
    return actions[:6]


def eligibility(cat: Catalog, view: StudentView) -> dict:
    ok, reason = additional_eligible(cat, view)
    minor = cat.rule("minor")
    return {"additional_credits": ok, "reason": reason,
            "minor": {"possible": ok and not view.is_cse, "rule": f"{minor.get('subjects', 6)} subjects, GPA >= {minor.get('minimum_gpa', 6.0)}, "
                      f">= {minor.get('minimum_additional_subjects', 3)} as additional credits"},
            "cgpa_to_unlock": max(0.0, round(float(cat.rule('additional_credits').get('minimum_cgpa', 7.5)) - view.cgpa, 2)) if not ok and not view.backlogs else None}


def diagnose(db: Session, cat: Catalog, view: StudentView) -> dict:
    rows = skill_rows(db, cat, view)
    know = [r for r in rows if r["status"] in ("mastered", "meets goal target")]
    gaps = [r for r in rows if r["status"] == "gap"]
    gaps.sort(key=lambda r: r["p_mastery"] - (r["target"] or 0))
    return {
        "student_id": view.id, "goal": view.goal_name, "goal_id": view.goal_id, "current_semester": view.current_semester,
        "pace": {"factor": round(view.pace, 2), "label": "slower than typical - plan hours are scaled up" if view.pace > 1.15
                 else "faster than typical" if view.pace < 0.85 else "typical"},
        "know": know, "gaps": gaps, "skills": rows, "mismatches": mismatches(db, cat, view),
        "eligibility": eligibility(cat, view), "goal_fit": goal_fit(cat, view)[:4],
        "constraints": {"weekly_hours": view.constraints.get("weekly_hours", 10), "credit_headroom": view.constraints.get("credit_headroom", 6),
                        "elective_slots": view.constraints.get("elective_slots"), "not_together": view.constraints.get("not_together", []),
                        "backlogs": view.backlogs, "excluded": sorted(view.excluded)},
    }
