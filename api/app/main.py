from contextlib import asynccontextmanager
import logging
import os
import threading
from typing import Any, AsyncIterator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import assessment, chat as chat_service
from app.catalog import build_view, load_catalog
from app.config import seed_dir
from app.db import Base, SessionLocal, engine, get_db
from app.insights import diagnose, goal_fit, next_actions, readiness
from app.llm import flush_bookkeeping, model_enabled, model_name
from app.models import (
    Assessment, Course, CourseSkill, Evidence, Exercise, Goal, LLMCall, Memory, Module, ModuleProgress, Plan, Question, Resource,
    Rule, Skill, SkillState, Student,
)
from app.seed import load_seed, validate_seed
from app.services import (
    change_goal, create_plan, current_plan, exclude_course, include_course, new_id, parse_goal, plan_payload, record_evidence,
    remember, reprocess_student, simulate_journey, simulate_quiz,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
EVIDENCE_KINDS = Literal["grade", "assessed", "mock_test", "quiz", "exercise", "project", "mock_interview", "self_declared"]


_initialized = False
_init_lock = threading.Lock()


def ensure_initialized() -> None:
    """Idempotent startup: also runs on the first request where a host skips ASGI lifespan events."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if not _initialized:
            initialize_database()
            _initialized = True


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for line in load_seed(db, seed_dir()):
            logger.info("Seed data: %s", line)
        for student in db.scalars(select(Student)).all():
            if current_plan(db, student.id) is None:
                reprocess_student(db, student, "seed", use_llm=False)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    ensure_initialized()
    yield


app = FastAPI(title="Clueless - personalised learning buddy (IIT Bhubaneswar)", version="1.0.0", lifespan=lifespan)
@app.middleware("http")
async def persist_model_bookkeeping(request, call_next):
    if not _initialized:
        from starlette.concurrency import run_in_threadpool

        await run_in_threadpool(ensure_initialized)
    response = await call_next(request)
    flush_bookkeeping()
    return response


app.add_middleware(CORSMiddleware, allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX", r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------- schemas
class Constraints(BaseModel):
    weekly_hours: float = Field(default=10, ge=0, le=60)
    credit_headroom: int = Field(default=6, ge=0, le=12)
    elective_slots: int | None = Field(default=None, ge=0, le=8)
    lateral_slots: int | None = Field(default=None, ge=0, le=3)
    not_together: list[list[str]] = Field(default_factory=list)
    minor: bool = False
    nptel_credits: int = Field(default=0, ge=0)


class Preferences(BaseModel):
    learning_style: str | None = Field(default=None, max_length=120)
    exclude_courses: list[str] = Field(default_factory=list)


class CompletedCourse(BaseModel):
    code: str
    grade: Literal["EX", "A", "B", "C", "D", "P"] | None = None


class StudentInput(BaseModel):
    name: str = Field(default="", max_length=120)
    programme: str = Field(min_length=3, max_length=100)
    current_semester: int = Field(ge=1, le=8)
    cgpa: float = Field(ge=0, le=10)
    goal_text: str = Field(min_length=3, max_length=600)
    goal_id: str | None = None
    completed_courses: list[CompletedCourse] = Field(default_factory=list)
    backlogs: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    self_ratings: dict[str, float] = Field(default_factory=dict)
    constraints: Constraints = Field(default_factory=Constraints)
    preferences: Preferences = Field(default_factory=Preferences)


class EvidenceInput(BaseModel):
    skill_id: str
    kind: EVIDENCE_KINDS
    value: float = Field(ge=0, le=1)
    items: int = Field(default=1, ge=1, le=50)
    attempts: int = Field(default=1, ge=1, le=20)
    time_spent_s: int = Field(default=0, ge=0)
    source: str = Field(default="api", max_length=120)


class AnswerInput(BaseModel):
    question_id: str
    answer: str = Field(min_length=1, max_length=4000)
    time_spent_s: int = Field(default=0, ge=0, le=36000)


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default="default", min_length=1, max_length=60)


class GoalInput(BaseModel):
    goal_text: str = Field(default="", max_length=600)
    goal_id: str | None = None


class SimulationInput(BaseModel):
    skill_id: str
    strong_score: float = Field(default=0.9, ge=0, le=1)
    weak_score: float = Field(default=0.2, ge=0, le=1)


class JourneyInput(BaseModel):
    scenario: Literal["strong", "weak", "mixed"] = "strong"


class OverrideInput(BaseModel):
    exclude_course: str | None = None
    include_course: str | None = None


class MockSubmit(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


class ActivitySubmit(BaseModel):
    text: str = Field(default="", max_length=8000)
    checklist: list[bool] = Field(default_factory=list)


class AssessmentInput(BaseModel):
    kind: Literal["mock_interview"] = "mock_interview"
    score: float = Field(ge=0, le=1)
    assessor: str = Field(default="mentor", max_length=60)
    notes: str = Field(default="", max_length=1000)
    skill_id: str = "communication"


class GradeInput(BaseModel):
    score: float = Field(ge=0, le=1)
    feedback: str = Field(default="", max_length=1000)
    assessor: str = Field(default="mentor", max_length=60)


class CourseInput(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    dept: str = Field(min_length=1, max_length=20)
    credits: int = Field(ge=1, le=12)
    ltp: str = Field(default="3-0-0", pattern=r"^\d-\d-\d{1,2}$")
    curriculum_semester: int | None = Field(default=None, ge=1, le=8)
    semester_offered: str = Field(pattern=r"^(Autumn|Spring)(\|(Autumn|Spring))?$")
    type: Literal["first_year", "core", "elective", "lateral", "project"]
    mode: str = Field(default="offline", max_length=30)
    syllabus: str = Field(min_length=1)
    objectives: str = Field(min_length=1)
    prerequisite_text: str = ""
    source_url: str = Field(pattern=r"^https?://")
    source_page: int | None = None
    verification: Literal["verified", "partial", "inferred", "assumed"] = "verified"
    verification_note: str = ""
    last_verified: str = Field(min_length=4, max_length=30)
    skills: dict[str, int] | None = None


class StudentPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    programme: str | None = Field(default=None, min_length=3, max_length=100)
    year: int | None = Field(default=None, ge=1, le=5)
    current_semester: int | None = Field(default=None, ge=1, le=8)
    cgpa: float | None = Field(default=None, ge=0, le=10)
    goal_text: str | None = None
    goal_id: str | None = None
    completed_courses: list[CompletedCourse] | None = None
    backlogs: list[str] | None = None
    interests: list[str] | None = None
    constraints: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None


class EvidencePatch(BaseModel):
    skill_id: str | None = None
    kind: EVIDENCE_KINDS | None = None
    value: float | None = Field(default=None, ge=0, le=1)
    items: int | None = Field(default=None, ge=1, le=50)
    attempts: int | None = Field(default=None, ge=1)
    time_spent_s: int | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------- helpers
def student_or_404(db: Session, student_id: str) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


def check_codes(db: Session, codes: set[str]) -> None:
    unknown = sorted(codes - set(db.scalars(select(Course.code)).all()))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown course code(s): {', '.join(unknown)}")


def check_skills(db: Session, skills: set[str]) -> None:
    unknown = sorted(skills - set(db.scalars(select(Skill.id)).all()))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown skill(s): {', '.join(unknown)}")


def check_constraints(db: Session, constraints: dict) -> None:
    pairs = constraints.get("not_together", [])
    if any(not isinstance(p, list) or len(p) != 2 for p in pairs):
        raise HTTPException(status_code=422, detail="Each not_together entry must be a pair of course codes")
    check_codes(db, {c for p in pairs for c in p})


def _plan_or_create(db: Session, student: Student) -> dict:
    plan = current_plan(db, student.id)
    if plan is None:
        reprocess_student(db, student, "refresh")
        plan = current_plan(db, student.id)
    return plan_payload(db, student, plan)


def handle_errors(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


# ---------------------------------------------------------------------- system and catalog
@app.get("/health")
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "model_configured": model_enabled(), "model": model_name() or None}


@app.get("/catalog")
def get_catalog(db: Session = Depends(get_db)):
    links: dict[str, dict[str, int]] = {}
    for row in db.scalars(select(CourseSkill)).all():
        links.setdefault(row.course_code, {})[row.skill_id] = row.level
    cat = load_catalog(db)
    return {
        "skills": db.scalars(select(Skill).order_by(Skill.name)).all(),
        "courses": [{**{c: getattr(course, c) for c in Course.__table__.columns.keys()}, "skills": links.get(course.code, {}),
                     "prerequisites": cat.prereq_groups.get(course.code, [])}
                    for course in db.scalars(select(Course).order_by(Course.code)).all()],
        "resources": db.scalars(select(Resource).order_by(Resource.skill_id, Resource.id)).all(),
        "exercises": db.scalars(select(Exercise).order_by(Exercise.skill_id, Exercise.id)).all(),
        "goals": db.scalars(select(Goal).order_by(Goal.name)).all(),
        "rules": db.scalars(select(Rule).order_by(Rule.id)).all(),
    }


@app.get("/courses/{code}")
def get_course(code: str, db: Session = Depends(get_db)):
    course = db.get(Course, code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    cat = load_catalog(db)
    return {"course": course, "skills": cat.course_skills.get(code, {}), "prerequisites": cat.prereq_groups.get(code, []),
            "modules": cat.modules.get(code, [])}


@app.post("/goals/parse")
def parse_goal_text(data: GoalInput, db: Session = Depends(get_db)):
    return parse_goal(load_catalog(db), data.goal_text)


# ---------------------------------------------------------------------- students
@app.get("/students")
def list_students(q: str | None = None, db: Session = Depends(get_db)):
    rows = db.scalars(select(Student).order_by(Student.id)).all()
    if q:
        needle = q.lower()
        rows = [s for s in rows if needle in f"{s.id} {s.name} {s.programme} {s.goal_text} {s.persona}".lower()]
    return [{"id": s.id, "name": s.name, "programme": s.programme, "year": s.year, "current_semester": s.current_semester,
             "cgpa": s.cgpa, "goal_text": s.goal_text, "goal_id": (s.goal_struct or {}).get("goal_id"), "persona": s.persona} for s in rows]


@app.post("/students")
def onboard_student(data: StudentInput, db: Session = Depends(get_db)):
    cat = load_catalog(db)
    check_codes(db, {c.code for c in data.completed_courses} | set(data.backlogs) | set(data.preferences.exclude_courses))
    check_constraints(db, data.constraints.model_dump())
    check_skills(db, set(data.interests) | set(data.self_ratings))
    goal = {"goal": data.goal_text, "goal_id": data.goal_id} if data.goal_id in cat.goals else parse_goal(cat, data.goal_text)
    if not goal.get("goal_id"):
        return {"clarifying_question": goal.get("clarifying_question"), "options": goal.get("options", []), "goal_struct": goal}
    student = Student(
        id=new_id("STU"), name=data.name, programme=data.programme, year=(data.current_semester + 1) // 2,
        current_semester=data.current_semester, cgpa=data.cgpa, goal_text=data.goal_text,
        goal_struct={"goal": data.goal_text, "goal_id": goal["goal_id"]},
        completed_courses=[c.model_dump() for c in data.completed_courses], backlogs=data.backlogs,
        interests=sorted(set(data.interests) | set(goal.get("interests", []))),
        constraints=data.constraints.model_dump(exclude_none=True), preferences=data.preferences.model_dump(exclude_none=True), persona="self-onboarded",
    )
    db.add(student)
    db.flush()
    for skill_id, rating in data.self_ratings.items():
        db.add(Evidence(id=new_id("EV"), student_id=student.id, skill_id=skill_id, kind="self_declared", value=max(0.0, min(1.0, rating)),
                        source="onboarding self-rating"))
    for skill_id in student.interests:
        if skill_id not in data.self_ratings:
            db.add(Evidence(id=new_id("EV"), student_id=student.id, skill_id=skill_id, kind="self_declared", value=0.7, source="onboarding interest"))
    remember(db, student.id, "preference", f"Onboarded: {data.programme}, semester {data.current_semester}, goal '{data.goal_text}', "
             f"learning style '{data.preferences.learning_style or 'not stated'}', {data.constraints.weekly_hours:g} h/week.")
    result = reprocess_student(db, student, "onboarding")
    return {"student": student, "plan": result["plan"]}


@app.get("/students/{student_id}")
def get_student(student_id: str, db: Session = Depends(get_db)):
    return student_or_404(db, student_id)


@app.get("/students/{student_id}/dashboard")
def dashboard(student_id: str, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    plan = _plan_or_create(db, student)
    cat = load_catalog(db)
    view = build_view(db, student, cat)
    return {"student": student, "plan": plan, "diagnosis": diagnose(db, cat, view), "readiness": plan["readiness"],
            "next_actions": next_actions(db, cat, view, plan)}


@app.get("/students/{student_id}/plan")
def get_plan(student_id: str, db: Session = Depends(get_db)):
    return _plan_or_create(db, student_or_404(db, student_id))


@app.post("/students/{student_id}/plan")
def refresh_plan(student_id: str, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    reprocess_student(db, student, "refresh")
    return plan_payload(db, student, current_plan(db, student.id))


@app.get("/students/{student_id}/plans")
def plan_history(student_id: str, db: Session = Depends(get_db)):
    student_or_404(db, student_id)
    plans = db.scalars(select(Plan).where(Plan.student_id == student_id).order_by(Plan.version.desc())).all()
    return [{"version": p.version, "trigger": p.trigger, "created_by": p.created_by, "created_at": p.created_at.isoformat() if p.created_at else None,
             "change_explanation": p.change_explanation, "diff": p.diff, "parent_version": p.parent_version,
             "course_codes": sorted({c for s in p.semesters for c in s.get("course_codes", [])})} for p in plans]


@app.get("/students/{student_id}/plans/{version}")
def plan_version(student_id: str, version: int, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    plan = db.scalar(select(Plan).where(Plan.student_id == student_id, Plan.version == version))
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan version not found")
    return plan_payload(db, student, plan)


@app.get("/students/{student_id}/diagnosis")
def get_diagnosis(student_id: str, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    cat = load_catalog(db)
    return diagnose(db, cat, build_view(db, student, cat))


@app.get("/students/{student_id}/progress")
def get_progress(student_id: str, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    cat = load_catalog(db)
    view = build_view(db, student, cat)
    d = diagnose(db, cat, view)
    completed = []
    for item in student.completed_courses or []:
        code = item.get("code")
        if code not in cat.courses:
            continue
        skills = cat.course_skills.get(code, {})
        demonstrated = [s for s in skills if view.mastery.get(s, 0) >= cat.config["mastery_threshold"]]
        completed.append({"code": code, "title": cat.courses[code]["title"], "grade": item.get("grade"),
                          "skills": [cat.skills[s]["name"] for s in skills],
                          "demonstrated": [cat.skills[s]["name"] for s in demonstrated],
                          "status": "completed and demonstrated" if skills and len(demonstrated) == len(skills)
                          else "completed - proficiency not yet demonstrated" if skills else "completed"})
    modules_done = db.scalars(select(ModuleProgress).where(ModuleProgress.student_id == student_id)).all()
    assessments = db.scalars(select(Assessment).where(Assessment.student_id == student_id).order_by(Assessment.created_at.desc())).all()
    return {"completed_courses": completed, "assumed_completed": sorted(view.assumed_completed), "skills": d["skills"],
            "readiness": readiness(db, cat, view), "modules_completed": [m.module_id for m in modules_done],
            "assessments": [{"id": a.id, "kind": a.kind, "status": a.status, "score": a.score, "exercise_id": a.exercise_id,
                             "feedback": a.feedback, "created_at": a.created_at.isoformat() if a.created_at else None,
                             "details": {k: v for k, v in (a.details or {}).items() if k in ("over_time", "elapsed_s", "time_limit_s", "per_skill")}}
                            for a in assessments[:20]],
            "mastery_threshold": cat.config["mastery_threshold"]}


@app.get("/students/{student_id}/readiness")
def get_readiness(student_id: str, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    cat = load_catalog(db)
    return readiness(db, cat, build_view(db, student, cat))


@app.get("/students/{student_id}/goal-fit")
def get_goal_fit(student_id: str, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    cat = load_catalog(db)
    return goal_fit(cat, build_view(db, student, cat))


@app.get("/students/{student_id}/evidence")
def list_evidence(student_id: str, db: Session = Depends(get_db)):
    student_or_404(db, student_id)
    return db.scalars(select(Evidence).where(Evidence.student_id == student_id).order_by(Evidence.created_at.desc())).all()


@app.post("/students/{student_id}/evidence")
def add_evidence(student_id: str, data: EvidenceInput, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    check_skills(db, {data.skill_id})
    evidence, result = record_evidence(db, student, data.model_dump())
    return {"evidence": evidence, "plan": result["plan"] if result else None}


@app.put("/students/{student_id}/goal")
def set_goal(student_id: str, data: GoalInput, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    cat = load_catalog(db)
    goal_id = data.goal_id
    if not goal_id:
        parsed = parse_goal(cat, data.goal_text)
        if not parsed.get("goal_id"):
            return {"clarifying_question": parsed.get("clarifying_question"), "options": parsed.get("options", [])}
        goal_id = parsed["goal_id"]
    result = handle_errors(change_goal, db, student, goal_id, data.goal_text or None)
    return {"goal_id": goal_id, "plan": result["plan"]}


@app.post("/students/{student_id}/override")
def add_override(student_id: str, data: OverrideInput, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    if data.exclude_course:
        check_codes(db, {data.exclude_course})
        return handle_errors(exclude_course, db, student, data.exclude_course)
    if data.include_course:
        check_codes(db, {data.include_course})
        return include_course(db, student, data.include_course)
    raise HTTPException(status_code=422, detail="Provide exclude_course or include_course")


@app.post("/students/{student_id}/simulate")
def simulate_plans(student_id: str, data: SimulationInput, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    return handle_errors(simulate_quiz, db, student, data.skill_id, data.strong_score, data.weak_score)


@app.post("/students/{student_id}/simulate/journey")
def simulate_student_journey(student_id: str, data: JourneyInput, db: Session = Depends(get_db)):
    return simulate_journey(db, student_or_404(db, student_id), data.scenario)


# ---------------------------------------------------------------------- assessment and practice
@app.get("/students/{student_id}/diagnostic")
def diagnostic_next(student_id: str, skill: str | None = None, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    if skill:
        check_skills(db, {skill})
    return assessment.next_diagnostic(db, student, skill)


@app.get("/students/{student_id}/diagnostic/{skill_id}")
def diagnostic_for_skill(student_id: str, skill_id: str, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    check_skills(db, {skill_id})
    return assessment.next_diagnostic(db, student, skill_id)


@app.post("/students/{student_id}/diagnostic/answer")
def diagnostic_answer(student_id: str, data: AnswerInput, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    return handle_errors(assessment.answer_diagnostic, db, student, data.question_id, data.answer, data.time_spent_s)


@app.post("/students/{student_id}/diagnostic/reset")
def diagnostic_reset(student_id: str, skill: str | None = None, db: Session = Depends(get_db)):
    assessment.reset_diagnostic(db, student_or_404(db, student_id), skill)
    return {"status": "reset"}


@app.get("/students/{student_id}/practice/{skill_id}")
def practice_question(student_id: str, skill_id: str, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    check_skills(db, {skill_id})
    return handle_errors(assessment.next_practice, db, student, skill_id)


@app.post("/students/{student_id}/practice/answer")
def practice_answer(student_id: str, data: AnswerInput, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    return handle_errors(assessment.answer_practice, db, student, data.question_id, data.answer, data.time_spent_s)


@app.post("/students/{student_id}/practice/{skill_id}/generate")
def generate_question(student_id: str, skill_id: str, db: Session = Depends(get_db)):
    student_or_404(db, student_id)
    question = handle_errors(assessment.generate_question, db, skill_id)
    return assessment.public_question(question)


@app.post("/students/{student_id}/mock-test")
def mock_test_start(student_id: str, db: Session = Depends(get_db)):
    return assessment.start_mock_test(db, student_or_404(db, student_id))


@app.post("/students/{student_id}/mock-test/{assessment_id}")
def mock_test_submit(student_id: str, assessment_id: str, data: MockSubmit, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    return handle_errors(assessment.submit_mock_test, db, student, assessment_id, data.answers)


@app.post("/students/{student_id}/activities/{exercise_id}")
def activity_submit(student_id: str, exercise_id: str, data: ActivitySubmit, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    return handle_errors(assessment.submit_activity, db, student, exercise_id, data.text, data.checklist)


@app.post("/students/{student_id}/assessments")
def record_assessment(student_id: str, data: AssessmentInput, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    check_skills(db, {data.skill_id})
    return assessment.record_mock_interview(db, student, data.score, data.assessor, data.notes, data.skill_id)


@app.post("/students/{student_id}/modules/{module_id}/complete")
def module_complete(student_id: str, module_id: str, db: Session = Depends(get_db)):
    return handle_errors(assessment.complete_module, db, student_or_404(db, student_id), module_id)


# ---------------------------------------------------------------------- conversation
@app.post("/students/{student_id}/chat")
def chat(student_id: str, data: ChatInput, db: Session = Depends(get_db)):
    return chat_service.handle_message(db, student_or_404(db, student_id), data.message, data.session_id)


@app.get("/students/{student_id}/chat/history")
def chat_history(student_id: str, session_id: str | None = None, db: Session = Depends(get_db)):
    return chat_service.history(db, student_or_404(db, student_id), session_id)


@app.get("/students/{student_id}/chat/welcome")
def chat_welcome(student_id: str, session_id: str = Query(default="default"), db: Session = Depends(get_db)):
    return chat_service.welcome(db, student_or_404(db, student_id), session_id)


@app.get("/students/{student_id}/memory")
def memory(student_id: str, db: Session = Depends(get_db)):
    student_or_404(db, student_id)
    return db.scalars(select(Memory).where(Memory.student_id == student_id).order_by(Memory.created_at.desc())).all()


# ---------------------------------------------------------------------- admin (every edit re-processes)
def _reprocess_all(db: Session) -> int:
    students = db.scalars(select(Student)).all()
    for student in students:
        reprocess_student(db, student, "admin_edit", "The course catalog was edited.", use_llm=False)
    return len(students)


@app.get("/admin/courses")
def admin_courses(db: Session = Depends(get_db)):
    return db.scalars(select(Course).order_by(Course.code)).all()


@app.post("/admin/courses")
def create_course(payload: CourseInput, db: Session = Depends(get_db)):
    data = payload.model_dump()
    skills = data.pop("skills") or {}
    check_skills(db, set(skills))
    if db.get(Course, data["code"]):
        raise HTTPException(status_code=409, detail="Course code already exists")
    data["contact_hours"] = sum(int(x) for x in data["ltp"].split("-"))
    db.add(Course(**data))
    db.flush()
    for skill_id, level in skills.items():
        db.add(CourseSkill(course_code=data["code"], skill_id=skill_id, level=max(1, min(3, int(level)))))
    db.flush()
    return {"course": db.get(Course, data["code"]), "reprocessed_students": _reprocess_all(db)}


@app.patch("/admin/courses/{code}")
def edit_course(code: str, payload: dict[str, Any], db: Session = Depends(get_db)):
    course = db.get(Course, code)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    allowed = set(CourseInput.model_fields) - {"code"}
    if not payload or set(payload) - allowed:
        raise HTTPException(status_code=422, detail=f"Allowed fields: {sorted(allowed)}")
    current = {key: getattr(course, key) for key in CourseInput.model_fields if key != "skills"}
    try:
        validated = CourseInput.model_validate({**current, **payload}).model_dump()
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    skills = validated.pop("skills")
    for key, value in validated.items():
        setattr(course, key, value)
    course.contact_hours = sum(int(x) for x in course.ltp.split("-"))
    if skills is not None:
        check_skills(db, set(skills))
        for row in db.scalars(select(CourseSkill).where(CourseSkill.course_code == code)).all():
            db.delete(row)
        db.flush()
        for skill_id, level in skills.items():
            db.add(CourseSkill(course_code=code, skill_id=skill_id, level=max(1, min(3, int(level)))))
    db.flush()
    return {"course": course, "reprocessed_students": _reprocess_all(db)}


@app.get("/admin/students")
def admin_students(db: Session = Depends(get_db)):
    return db.scalars(select(Student).order_by(Student.id)).all()


@app.patch("/admin/students/{student_id}")
def edit_student(student_id: str, payload: StudentPatch, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates or any(value is None for value in updates.values()):
        raise HTTPException(status_code=422, detail="Provide at least one non-null field to update")
    cat = load_catalog(db)
    if "completed_courses" in updates:
        check_codes(db, {c["code"] for c in updates["completed_courses"]})
    if "backlogs" in updates:
        check_codes(db, set(updates["backlogs"]))
    if "interests" in updates:
        check_skills(db, set(updates["interests"]))
    if "constraints" in updates:
        updates["constraints"] = {**(student.constraints or {}), **updates["constraints"]}
        check_constraints(db, updates["constraints"])
    if "preferences" in updates:
        updates["preferences"] = {**(student.preferences or {}), **updates["preferences"]}
        check_codes(db, set(updates["preferences"].get("exclude_courses", [])))
    goal_id = updates.pop("goal_id", None)
    clarifying = None
    if goal_id or "goal_text" in updates:
        if not goal_id:
            parsed = parse_goal(cat, updates["goal_text"])
            goal_id, clarifying = parsed.get("goal_id"), parsed.get("clarifying_question")
        if goal_id and goal_id not in cat.goals:
            raise HTTPException(status_code=422, detail=f"Unknown goal: {goal_id}")
        if goal_id:
            student.goal_struct = {**(student.goal_struct or {}), "goal_id": goal_id, "goal": updates.get("goal_text", student.goal_text)}
    if "current_semester" in updates and "year" not in updates:
        updates["year"] = (updates["current_semester"] + 1) // 2
    for key, value in updates.items():
        setattr(student, key, value)
    db.flush()
    result = reprocess_student(db, student, "admin_edit", "Your profile was edited.", use_llm=False)
    return {"student": student, "clarifying_question": clarifying, **result}


@app.get("/admin/evidence")
def admin_evidence(student_id: str | None = None, db: Session = Depends(get_db)):
    query = select(Evidence).order_by(Evidence.created_at.desc())
    if student_id:
        query = query.where(Evidence.student_id == student_id)
    return db.scalars(query.limit(500)).all()


@app.patch("/admin/evidence/{evidence_id}")
def edit_evidence(evidence_id: str, payload: EvidencePatch, db: Session = Depends(get_db)):
    evidence = db.get(Evidence, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    updates = payload.model_dump(exclude_unset=True)
    if not updates or any(value is None for value in updates.values()):
        raise HTTPException(status_code=422, detail="Provide at least one non-null evidence field to update")
    if "skill_id" in updates:
        check_skills(db, {updates["skill_id"]})
    for key, value in updates.items():
        setattr(evidence, key, value)
    db.flush()
    result = reprocess_student(db, student_or_404(db, evidence.student_id), "admin_edit", "A score was edited.", use_llm=False)
    return {"evidence": evidence, **result}


@app.delete("/admin/evidence/{evidence_id}")
def delete_evidence(evidence_id: str, db: Session = Depends(get_db)):
    evidence = db.get(Evidence, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    student = student_or_404(db, evidence.student_id)
    db.delete(evidence)
    db.flush()
    return reprocess_student(db, student, "admin_edit", "A score was deleted.", use_llm=False)


@app.get("/admin/assessments")
def admin_assessments(status: str | None = None, db: Session = Depends(get_db)):
    query = select(Assessment).order_by(Assessment.created_at.desc())
    if status:
        query = query.where(Assessment.status == status)
    return db.scalars(query.limit(200)).all()


@app.patch("/admin/assessments/{assessment_id}")
def grade_submission(assessment_id: str, data: GradeInput, db: Session = Depends(get_db)):
    return handle_errors(assessment.grade_assessment, db, assessment_id, data.score, data.feedback, data.assessor)


@app.post("/admin/reprocess")
def reprocess_everyone(db: Session = Depends(get_db)):
    """Use after direct SQL edits in Adminer, which bypass application re-processing."""
    return {"reprocessed_students": _reprocess_all(db)}


@app.post("/admin/reset")
def reset_everything():
    from app.reset import reset_database

    return {"status": "reset", "report": reset_database()}


@app.get("/admin/data-quality")
def data_quality():
    try:
        return {"ok": True, "report": validate_seed(seed_dir())}
    except Exception as error:  # report the problem instead of failing the admin page
        return {"ok": False, "report": [str(error)]}


@app.get("/admin/llm-usage")
def llm_usage(db: Session = Depends(get_db)):
    flush_bookkeeping()
    rows = db.execute(select(LLMCall.purpose, func.count(), func.sum(LLMCall.prompt_tokens), func.sum(LLMCall.completion_tokens),
                             func.avg(LLMCall.latency_ms)).group_by(LLMCall.purpose)).all()
    failures = db.scalar(select(func.count()).select_from(LLMCall).where(LLMCall.ok.is_(False))) or 0
    cached = db.scalar(select(func.count()).select_from(LLMCall).where(LLMCall.cached.is_(True))) or 0
    return {"model": model_name() or None, "configured": model_enabled(), "failures": failures, "cache_hits": cached,
            "by_purpose": [{"purpose": r[0], "calls": r[1], "prompt_tokens": int(r[2] or 0), "completion_tokens": int(r[3] or 0),
                            "avg_latency_ms": int(r[4] or 0)} for r in rows]}


@app.get("/admin/plans/check")
def check_all_plans(db: Session = Depends(get_db)):
    from app.evaluate import evaluate_all

    return evaluate_all(db)


@app.post("/admin/students/{student_id}/delete")
def delete_student(student_id: str, db: Session = Depends(get_db)):
    student = student_or_404(db, student_id)
    try:
        db.delete(student)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not delete the student") from error
    return {"deleted": student_id}
