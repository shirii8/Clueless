"""Pure-data snapshots of the knowledge base and of one student, used by the planner and validator.

Keeping planning on plain data (no ORM objects) lets the same code validate live plans, run
what-if simulations and simulate multi-semester journeys without touching the database.
"""
from collections import defaultdict
from dataclasses import dataclass, field, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import bkt_config, level_target
from app.models import (
    Course, CourseSkill, Evidence, Exercise, Goal, Module, Prerequisite, Question, Resource, Rule, Skill,
    SkillPrereq, SkillState, Student,
)

PLANNABLE_TYPES = {"core", "elective", "lateral"}
SCHOOL_KEYWORDS = [
    ("computer science", "CS"), ("cse", "CS"), ("chemical", "CH"), ("mechanical", "ME"), ("electrical", "EE"),
    ("electronics", "EC"), ("civil", "CE"), ("metallurg", "MM"), ("materials", "MM"),
]


def school_of(programme: str) -> str:
    text = (programme or "").lower()
    for keyword, school in SCHOOL_KEYWORDS:
        if keyword in text:
            return school
    return "OTHER"


@dataclass
class Catalog:
    courses: dict[str, dict]
    prereq_groups: dict[str, list[list[str]]]
    course_skills: dict[str, dict[str, int]]
    skill_courses: dict[str, list[tuple[str, int]]]
    skills: dict[str, dict]
    skill_prereqs: dict[str, list[str]]
    modules: dict[str, list[dict]]
    resources: dict[str, list[dict]]
    exercises: dict[str, list[dict]]
    question_counts: dict[str, int]
    rules: dict[str, dict]
    rule_sources: dict[str, str]
    goals: dict[str, dict]
    config: dict

    def rule(self, kind: str) -> dict:
        return self.rules.get(kind, {})


def load_catalog(db: Session) -> Catalog:
    courses = {
        c.code: {
            "code": c.code, "title": c.title, "dept": c.dept, "credits": c.credits, "ltp": c.ltp,
            "contact_hours": c.contact_hours, "curriculum_semester": c.curriculum_semester,
            "offered": {s.strip().lower() for s in c.semester_offered.split("|") if s.strip()},
            "semester_offered": c.semester_offered, "type": c.type, "source_url": c.source_url,
            "verification": c.verification,
        }
        for c in db.scalars(select(Course)).all()
    }
    groups: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in db.scalars(select(Prerequisite)).all():
        groups[row.course_code][row.group_id].append(row.requires_code)
    prereq_groups = {code: [sorted(v) for _, v in sorted(g.items())] for code, g in groups.items()}
    course_skills: dict[str, dict[str, int]] = defaultdict(dict)
    skill_courses: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for row in db.scalars(select(CourseSkill)).all():
        course_skills[row.course_code][row.skill_id] = row.level
        skill_courses[row.skill_id].append((row.course_code, row.level))
    skill_prereqs: dict[str, list[str]] = defaultdict(list)
    for row in db.scalars(select(SkillPrereq)).all():
        skill_prereqs[row.skill_id].append(row.requires_skill_id)
    modules: dict[str, list[dict]] = defaultdict(list)
    for m in db.scalars(select(Module).order_by(Module.course_code, Module.position)).all():
        modules[m.course_code].append({"id": m.id, "title": m.title, "kind": m.kind, "skill_id": m.skill_id,
                                       "est_hours": m.est_hours, "course_code": m.course_code})
    resources: dict[str, list[dict]] = defaultdict(list)
    for r in db.scalars(select(Resource).order_by(Resource.id)).all():
        resources[r.skill_id].append({"id": r.id, "title": r.title, "url": r.url, "provider": r.provider,
                                      "licence": r.licence, "format": r.format, "est_hours": r.est_hours,
                                      "level": r.level, "skill_id": r.skill_id})
    exercises: dict[str, list[dict]] = defaultdict(list)
    for x in db.scalars(select(Exercise).order_by(Exercise.id)).all():
        exercises[x.skill_id].append({"id": x.id, "title": x.title, "kind": x.kind, "est_hours": x.est_hours,
                                      "level": x.level, "skill_id": x.skill_id, "rubric": x.rubric,
                                      "description": x.description})
    question_counts: dict[str, int] = defaultdict(int)
    for (skill_id,) in db.execute(select(Question.skill_id)):
        question_counts[skill_id] += 1
    rules, rule_sources = {}, {}
    for r in db.scalars(select(Rule)).all():
        rules[r.kind] = r.params
        rule_sources[r.kind] = r.source_url
    goals = {
        g.id: {"id": g.id, "name": g.name, "keywords": g.keywords, "target_skills": g.target_skills,
               "readiness": g.readiness, "milestones": g.milestones, "protect_cgpa": g.protect_cgpa}
        for g in db.scalars(select(Goal)).all()
    }
    skills = {s.id: {"id": s.id, "name": s.name, "category": s.category, "description": s.description}
              for s in db.scalars(select(Skill)).all()}
    return Catalog(courses, prereq_groups, dict(course_skills), dict(skill_courses), skills, dict(skill_prereqs),
                   dict(modules), dict(resources), dict(exercises), dict(question_counts), rules, rule_sources,
                   goals, bkt_config())


@dataclass
class StudentView:
    id: str
    programme: str
    school: str
    year: int
    current_semester: int
    cgpa: float
    completed: dict[str, str | None]
    assumed_completed: set[str]
    backlogs: list[str]
    excluded: set[str]
    goal_id: str | None
    goal_name: str
    target_skills: dict[str, int]
    constraints: dict
    preferences: dict
    interests: list[str]
    mastery: dict[str, float]
    tested: set[str] = field(default_factory=set)
    misses: dict[str, int] = field(default_factory=dict)
    missed_topics: dict[str, list[str]] = field(default_factory=dict)
    pace: float = 1.0

    @property
    def is_cse(self) -> bool:
        return self.school == "CS"

    @property
    def done(self) -> set[str]:
        return set(self.completed) | self.assumed_completed

    def target_for(self, skill_id: str) -> float:
        return level_target(self.target_skills.get(skill_id, 2))

    def evolve(self, **changes) -> "StudentView":
        return replace(self, **changes)


def additional_eligible(cat: Catalog, view: StudentView) -> tuple[bool, str]:
    rule = cat.rule("additional_credits")
    minimum = float(rule.get("minimum_cgpa", 7.5))
    if rule.get("requires_no_backlog", True) and view.backlogs:
        return False, f"you have {len(view.backlogs)} backlog subject(s); additional credits need no backlogs (Regulation 9)"
    if view.cgpa < minimum:
        return False, f"your CGPA {view.cgpa:.2f} is below the {minimum:.2f} needed for additional credits (Regulation 9)"
    return True, f"CGPA {view.cgpa:.2f} >= {minimum:.2f} with no backlogs (Regulation 9)"


def build_view(db: Session, student: Student, cat: Catalog, mastery: dict[str, float] | None = None) -> StudentView:
    if mastery is None:
        mastery = {s.skill_id: s.p_mastery for s in db.scalars(select(SkillState).where(SkillState.student_id == student.id)).all()}
    tested = {s.skill_id for s in db.scalars(select(SkillState).where(SkillState.student_id == student.id, SkillState.tested.is_(True))).all()}
    config = cat.config
    tested_kinds = set(config.get("tested_kinds", []))
    misses: dict[str, int] = defaultdict(int)
    missed_topics: dict[str, list[str]] = defaultdict(list)
    ratios = []
    expected = config.get("expected_seconds_per_question", 90)
    for e in db.scalars(select(Evidence).where(Evidence.student_id == student.id).order_by(Evidence.created_at)).all():
        if e.kind in tested_kinds:
            tested.add(e.skill_id)
            if e.value < 0.5:
                misses[e.skill_id] += 1
                if e.topic and e.topic not in missed_topics[e.skill_id]:
                    missed_topics[e.skill_id].append(e.topic)
        if e.kind == "quiz" and e.time_spent_s > 0:
            ratios.append(e.time_spent_s / max(1, e.items) / expected)
    ratios.sort()
    pace = ratios[len(ratios) // 2] if ratios else 1.0
    pace = max(0.75, min(1.5, pace))
    return view_from_student(student, cat, mastery, tested, dict(misses), dict(missed_topics), pace)


def view_from_student(student: Student, cat: Catalog, mastery: dict[str, float], tested: set[str] | None = None,
                      misses: dict[str, int] | None = None, missed_topics: dict[str, list[str]] | None = None,
                      pace: float = 1.0) -> StudentView:
    school = school_of(student.programme)
    completed = {item["code"]: item.get("grade") for item in (student.completed_courses or []) if item.get("code") in cat.courses}
    backlogs = [code for code in (student.backlogs or []) if code in cat.courses]
    current = max(1, min(8, int(student.current_semester or 1)))
    assumed: set[str] = set()
    for code, course in cat.courses.items():
        sem = course["curriculum_semester"]
        if code in completed or code in backlogs or not sem or sem >= current:
            continue
        if course["type"] == "first_year" or (school == "CS" and course["type"] in {"core", "project"}):
            assumed.add(code)
    goal = student.goal_struct or {}
    goal_id = goal.get("goal_id")
    template = cat.goals.get(goal_id or "", {})
    targets = goal.get("target_levels") or template.get("target_skills") or {s: 2 for s in goal.get("target_skills", [])}
    targets = {k: int(v) for k, v in targets.items() if k in cat.skills}
    preferences = dict(student.preferences or {})
    return StudentView(
        id=student.id, programme=student.programme, school=school, year=student.year, current_semester=current,
        cgpa=float(student.cgpa), completed=completed, assumed_completed=assumed, backlogs=backlogs,
        excluded=set(preferences.get("exclude_courses", [])), goal_id=goal_id,
        goal_name=template.get("name") or goal.get("goal") or student.goal_text, target_skills=targets,
        constraints=dict(student.constraints or {}), preferences=preferences,
        interests=[i for i in (student.interests or []) if i in cat.skills], mastery=dict(mastery),
        tested=set(tested or set()), misses=dict(misses or {}), missed_topics=dict(missed_topics or {}), pace=pace,
    )
