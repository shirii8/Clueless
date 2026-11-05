"""Load and quality-check the plain-file seed data in data/seed.

`validate_seed` raises SeedDataError on anything that would make the buddy reason incorrectly
(broken references, cycles, invalid answers) and returns a report of counts, coverage and
documented inconsistencies for the data-quality section of the README.
"""
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import seed_dir as default_seed_dir
from app.models import (
    Course, CourseSkill, Evidence, Exercise, Goal, Module, Prerequisite, Question, Resource, Rule, Skill,
    SkillPrereq, Student,
)

COURSE_FIELDS = ("code", "title", "dept", "credits", "ltp", "contact_hours", "curriculum_semester", "semester_offered",
                 "type", "mode", "syllabus", "objectives", "prerequisite_text", "source_url", "source_page",
                 "verification", "verification_note", "last_verified")
COURSE_TYPES = {"first_year", "core", "elective", "lateral", "project"}
EVIDENCE_KINDS = {"grade", "assessed", "mock_test", "quiz", "exercise", "project", "mock_interview", "module_completion", "self_declared"}


class SeedDataError(ValueError):
    pass


def _csv(path: Path, required: tuple[str, ...] = ()) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = sorted(set(required) - set(reader.fieldnames or []))
        if missing:
            raise SeedDataError(f"{path.name} is missing CSV headers: {missing}")
        return list(reader)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _find_cycle(edges: dict[str, set[str]]) -> list[str] | None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for nxt in edges.get(node, ()):
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if state.get(nxt) is None:
                found = visit(nxt)
                if found:
                    return found
        state[node] = 2
        stack.pop()
        return None

    for node in list(edges):
        if state.get(node) is None:
            found = visit(node)
            if found:
                return found
    return None


def validate_seed(seed_dir: Path) -> list[str]:
    report: list[str] = []
    info: list[str] = []
    courses = _csv(seed_dir / "courses.csv", COURSE_FIELDS)
    codes = [row["code"].strip() for row in courses]
    duplicates = sorted(code for code, n in Counter(codes).items() if n > 1)
    if duplicates:
        raise SeedDataError(f"duplicate course codes: {duplicates}")
    required = ("code", "title", "dept", "credits", "ltp", "semester_offered", "type", "syllabus", "objectives", "source_url", "last_verified")
    missing = [row["code"] for row in courses if any(not row.get(f, "").strip() for f in required)]
    if missing:
        raise SeedDataError(f"courses.csv has missing required fields: {missing}")
    by_code = {row["code"]: row for row in courses}
    for row in courses:
        try:
            credits = int(row["credits"])
            l, t, p = (int(x) for x in row["ltp"].split("-"))
        except ValueError as error:
            raise SeedDataError(f"{row['code']}: credits and L-T-P must be integers") from error
        if credits <= 0:
            raise SeedDataError(f"{row['code']}: credits must be positive")
        if row["type"] not in COURSE_TYPES:
            raise SeedDataError(f"{row['code']}: unknown course type {row['type']}")
        offered = {s.strip() for s in row["semester_offered"].split("|")}
        if not offered <= {"Autumn", "Spring"}:
            raise SeedDataError(f"{row['code']}: semester_offered must be Autumn and/or Spring")
        if not row["source_url"].startswith("https://"):
            raise SeedDataError(f"{row['code']}: source_url must be an https URL")
        sem = row["curriculum_semester"].strip()
        if sem and row["type"] != "first_year":
            expected = "Autumn" if int(sem) % 2 else "Spring"
            if offered != {expected}:
                info.append(f"{row['code']}: curriculum semester {sem} implies {expected} but offered {row['semester_offered']}")
        if credits != l + t + math.ceil(p / 2):
            info.append(f"{row['code']}: credits {credits} differ from L+T+P/2 for {row['ltp']} (institute value kept)")
        if row["verification_note"]:
            if "differ" in row["verification_note"] or "implies" in row["verification_note"] or "lists" in row["verification_note"]:
                info.append(f"{row['code']}: source inconsistency documented - {row['verification_note'][:140]}")
    verification = Counter(row["verification"] for row in courses)
    types = Counter(row["type"] for row in courses)
    report.append(f"courses: {len(courses)} ({', '.join(f'{k} {v}' for k, v in sorted(types.items()))}); "
                  f"verification: {', '.join(f'{k} {v}' for k, v in sorted(verification.items()))}")

    prereqs = _csv(seed_dir / "prerequisites.csv", ("course_code", "requires_code", "group_id"))
    edges: dict[str, set[str]] = defaultdict(set)
    for row in prereqs:
        if row["course_code"] not in by_code or row["requires_code"] not in by_code:
            raise SeedDataError(f"unknown prerequisite reference: {row}")
        if row["course_code"] == row["requires_code"]:
            raise SeedDataError(f"{row['course_code']} cannot be its own prerequisite")
        edges[row["course_code"]].add(row["requires_code"])
    cycle = _find_cycle(edges)
    if cycle:
        raise SeedDataError(f"prerequisite cycle: {' -> '.join(cycle)}")
    report.append(f"prerequisites: {len(prereqs)} rows in AND-of-OR groups; no cycles")

    skills = _csv(seed_dir / "skills.csv", ("id", "name", "category", "description"))
    skill_ids = {row["id"] for row in skills}
    if len(skill_ids) != len(skills) or any(not row["name"] or not row["description"] for row in skills):
        raise SeedDataError("skills.csv has duplicate IDs or missing fields")
    skill_edges: dict[str, set[str]] = defaultdict(set)
    for row in _csv(seed_dir / "skill_prereqs.csv", ("skill_id", "requires_skill_id")):
        if row["skill_id"] not in skill_ids or row["requires_skill_id"] not in skill_ids:
            raise SeedDataError(f"skill_prereqs has an unknown skill: {row}")
        skill_edges[row["skill_id"]].add(row["requires_skill_id"])
    if _find_cycle(skill_edges):
        raise SeedDataError("skill prerequisite graph has a cycle")
    links = _csv(seed_dir / "course_skills.csv", ("course_code", "skill_id", "level"))
    for row in links:
        if row["course_code"] not in by_code or row["skill_id"] not in skill_ids or row["level"] not in {"1", "2", "3"}:
            raise SeedDataError(f"invalid course_skills row: {row}")
    modules = _csv(seed_dir / "modules.csv", ("id", "course_code", "position", "title", "kind", "est_hours", "skill_id"))
    if len({m["id"] for m in modules}) != len(modules):
        raise SeedDataError("duplicate module IDs")
    for m in modules:
        if m["course_code"] not in by_code or (m["skill_id"] and m["skill_id"] not in skill_ids) or m["kind"] not in {"intro", "core", "advanced"}:
            raise SeedDataError(f"invalid module row: {m['id']}")
    questions = _json(seed_dir / "questions.json")
    for q in questions:
        if q["skill_id"] not in skill_ids or q["difficulty"] not in (1, 2, 3) or not q.get("stem") or not q.get("source"):
            raise SeedDataError(f"invalid question {q.get('id')}")
        if q.get("options") and q.get("answer") not in q["options"]:
            raise SeedDataError(f"question {q['id']} answer is not one of its options")
        if q.get("options") and len(set(q["options"])) != len(q["options"]):
            raise SeedDataError(f"question {q['id']} has duplicate options")
        if not q.get("answer") and not q.get("rubric"):
            raise SeedDataError(f"question {q['id']} has neither an answer key nor a rubric")
    if len({q["id"] for q in questions}) != len(questions):
        raise SeedDataError("duplicate question IDs")
    exercises = _json(seed_dir / "exercises.json")
    for x in exercises:
        if x["skill_id"] not in skill_ids or not x.get("rubric") or x["est_hours"] <= 0:
            raise SeedDataError(f"invalid exercise {x.get('id')}")
    resources = _json(seed_dir / "resources.json")
    for r in resources:
        if r["skill_id"] not in skill_ids or not r["url"].startswith("http") or not r.get("licence") or not r.get("verified_on"):
            raise SeedDataError(f"resource {r.get('id')} is missing traceability fields")
    if len({r["id"] for r in resources}) != len(resources):
        raise SeedDataError("duplicate resource IDs")
    rules = _csv(seed_dir / "rules.csv", ("id", "kind", "params", "source_url", "verification", "note"))
    for row in rules:
        try:
            json.loads(row["params"])
        except json.JSONDecodeError as error:
            raise SeedDataError(f"rule {row['id']} params are not valid JSON") from error
        if not row["source_url"]:
            raise SeedDataError(f"rule {row['id']} is missing source_url")
    goals = _json(seed_dir / "goals.json")
    for g in goals:
        if any(s not in skill_ids for s in g["target_skills"]):
            raise SeedDataError(f"goal {g['id']} references an unknown skill")

    course_cover = defaultdict(int)
    for row in links:
        course_cover[row["skill_id"]] += 1
    q_cover = Counter(q["skill_id"] for q in questions)
    r_cover = Counter(r["skill_id"] for r in resources)
    x_cover = Counter(x["skill_id"] for x in exercises)
    thin = [s for s in sorted(skill_ids) if q_cover[s] < 3 or (course_cover[s] == 0 and r_cover[s] == 0)]
    if thin:
        raise SeedDataError(f"skills without enough questions or any course/resource: {thin}")
    report.append(f"skills: {len(skills)}; course-skill links: {len(links)}; skill prerequisites: {sum(len(v) for v in skill_edges.values())}")
    report.append(f"modules: {len(modules)}; questions: {len(questions)} (every skill has >= {min(q_cover.values())}); "
                  f"exercises/projects/mock assessments: {len(exercises)}; total practice items: {len(questions) + len(exercises)}")
    report.append(f"open resources: {len(resources)} ({', '.join(f'{k} {v}' for k, v in Counter(r['provider'] for r in resources).most_common())}); "
                  f"link-checked on {sorted({r['verified_on'] for r in resources})[-1]}")
    no_course = sorted(s for s in skill_ids if course_cover[s] == 0)
    if no_course:
        info.append(f"skills with no institute course in the KB (covered by open resources only): {', '.join(no_course)}")
    no_practice = sorted(s for s in skill_ids if x_cover[s] == 0)
    if no_practice:
        info.append(f"skills without a hands-on exercise (questions only): {', '.join(no_practice)}")
    rule_status = Counter(row["verification"] for row in rules)
    report.append(f"rules: {len(rules)} ({', '.join(f'{k} {v}' for k, v in sorted(rule_status.items()))}); goals: {len(goals)}")

    profiles = _json(seed_dir / "students.json")
    student_ids = {p["id"] for p in profiles}
    if len(student_ids) != len(profiles):
        raise SeedDataError("duplicate student IDs")
    for p in profiles:
        if not p.get("goal_text") or not p.get("programme") or not 0 <= float(p["cgpa"]) <= 10:
            raise SeedDataError(f"profile {p.get('id')} is missing fields or has an invalid CGPA")
        if not 1 <= int(p.get("current_semester", 1)) <= 8:
            raise SeedDataError(f"profile {p['id']} has an invalid current semester")
        for item in p.get("completed_courses", []):
            if item["code"] not in by_code:
                raise SeedDataError(f"profile {p['id']} completed an unknown course {item['code']}")
        for code in p.get("backlogs", []) + p.get("preferences", {}).get("exclude_courses", []):
            if code not in by_code:
                raise SeedDataError(f"profile {p['id']} references unknown course {code}")
        for pair in p.get("constraints", {}).get("not_together", []):
            if len(pair) != 2 or any(code not in by_code for code in pair):
                raise SeedDataError(f"profile {p['id']} has an invalid not_together pair")
        targets = p.get("goal_struct", {}).get("target_levels", {})
        if any(s not in skill_ids for s in targets) or any(s not in skill_ids for s in p.get("interests", [])):
            raise SeedDataError(f"profile {p['id']} references an unknown skill")
    evidence = _csv(seed_dir / "evidence.csv", ("id", "student_id", "skill_id", "kind", "value", "items", "attempts", "time_spent_s", "source"))
    for row in evidence:
        if row["student_id"] not in student_ids or row["skill_id"] not in skill_ids or row["kind"] not in EVIDENCE_KINDS:
            raise SeedDataError(f"invalid evidence row {row['id']}")
        if not 0 <= float(row["value"]) <= 1 or int(row["items"]) < 1 or int(row["attempts"]) < 1 or int(row["time_spent_s"]) < 0:
            raise SeedDataError(f"evidence {row['id']} has out-of-range values")
    report.append(f"students: {len(profiles)} synthetic profiles ({len({p.get('persona') for p in profiles})} personas); evidence rows: {len(evidence)}")
    return report + [f"note: {line}" for line in info]


def load_seed(db: Session, seed_dir: Path | None = None) -> list[str]:
    seed_dir = seed_dir or default_seed_dir()
    report = validate_seed(seed_dir)
    if db.scalar(select(Course.code).limit(1)) is not None:
        return report
    db.add_all(Skill(**row) for row in _csv(seed_dir / "skills.csv"))
    db.flush()
    db.add_all(SkillPrereq(**row) for row in _csv(seed_dir / "skill_prereqs.csv"))
    for row in _csv(seed_dir / "courses.csv"):
        db.add(Course(**{
            **row, "credits": int(row["credits"]), "contact_hours": int(row["contact_hours"]),
            "curriculum_semester": int(row["curriculum_semester"]) if row["curriculum_semester"] else None,
            "source_page": int(row["source_page"]) if row["source_page"] else None,
        }))
    db.flush()
    db.add_all(Prerequisite(course_code=r["course_code"], requires_code=r["requires_code"], group_id=int(r["group_id"]))
               for r in _csv(seed_dir / "prerequisites.csv"))
    db.add_all(CourseSkill(course_code=r["course_code"], skill_id=r["skill_id"], level=int(r["level"]))
               for r in _csv(seed_dir / "course_skills.csv"))
    db.add_all(Module(id=r["id"], course_code=r["course_code"], position=int(r["position"]), title=r["title"], kind=r["kind"],
                      est_hours=float(r["est_hours"]), skill_id=r["skill_id"] or None) for r in _csv(seed_dir / "modules.csv"))
    db.add_all(Question(**q) for q in _json(seed_dir / "questions.json"))
    db.add_all(Exercise(**x) for x in _json(seed_dir / "exercises.json"))
    db.add_all(Resource(**r) for r in _json(seed_dir / "resources.json"))
    for row in _csv(seed_dir / "rules.csv"):
        db.add(Rule(id=row["id"], kind=row["kind"], params=json.loads(row["params"]), source_url=row["source_url"],
                    verification=row["verification"], note=row["note"]))
    for g in _json(seed_dir / "goals.json"):
        db.add(Goal(id=g["id"], name=g["name"], keywords=g["keywords"], target_skills=g["target_skills"],
                    readiness=g["readiness"], milestones=g["milestones"], protect_cgpa=bool(g.get("protect_cgpa"))))
    db.flush()
    for profile in _json(seed_dir / "students.json"):
        db.add(Student(**{k: v for k, v in profile.items() if k in Student.__table__.columns.keys()}))
    db.flush()
    for row in _csv(seed_dir / "evidence.csv"):
        db.add(Evidence(id=row["id"], student_id=row["student_id"], skill_id=row["skill_id"], kind=row["kind"],
                        value=float(row["value"]), items=int(row["items"]), attempts=int(row["attempts"]),
                        time_spent_s=int(row["time_spent_s"]), source=row["source"], topic=row.get("topic") or None))
    db.commit()
    return report
