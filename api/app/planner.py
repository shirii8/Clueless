"""Deterministic planner and validator.

The planner owns correctness: every course, slot, credit, hour and prerequisite decision is computed
here from the knowledge base and the cited rules. The language model never decides what goes in a
plan; it only explains plans that have already passed `validate`.

Plan shape (one dict per remaining semester):
    semester, season, label,
    core_codes      fixed curriculum courses (B.Tech CSE students only)
    courses         buddy-chosen courses: {code, title, credits, slot, skills, reason}
    course_codes    codes of `courses` (for quick display and diffs)
    activities      active practice: exercises, projects, case studies, mock tests/interviews
    resources       open learning resources (NPTEL, MIT OCW, ...), non-credit
    review_modules  remediation for repeatedly missed skills
    skip_modules    modules skipped because the skill is already demonstrated
    milestones      goal milestones beyond coursework (internships, exams, applications)
    load            additional credits, extra weekly hours and slot use vs. limits
"""
import math
from copy import deepcopy

from app.catalog import Catalog, StudentView, additional_eligible
from app.config import MAX_SEMESTER, level_target, season_of

SLOT_LABEL = {
    "elective": "elective slot",
    "lateral": "lateral slot",
    "additional": "additional credit",
    "backlog": "backlog re-registration",
}
FORMAT_PREFERENCE = {
    "videos": ["video", "course", "text", "practice"],
    "reading": ["text", "course", "video", "practice"],
    "projects": ["practice", "course", "video", "text"],
    "practice": ["practice", "course", "video", "text"],
}
ACTIVITY_PREFERENCE = {
    "projects": ["project", "case_study", "exercise"],
    "practice": ["exercise", "project", "case_study"],
}
ASSESSMENT_KINDS = {"mock_test", "mock_interview"}
SMALL_GAP = 0.08  # a tested skill this close to target needs practice, not another course


def hours_per_week(est_hours: float, pace: float = 1.0, weeks: int = 14) -> float:
    return max(0.5, math.ceil(est_hours / weeks * pace * 2) / 2)


def course_extra_hours(course: dict, cat: Catalog) -> float:
    per_credit = float(cat.rule("weekly_hours").get("self_study_hours_per_credit", 1.0))
    return float(course["contact_hours"]) + course["credits"] * per_credit


def is_theory(course: dict) -> bool:
    return not course["ltp"].startswith("0-0-")


def semesters_for(view: StudentView) -> list[int]:
    return list(range(view.current_semester, MAX_SEMESTER + 1))


def core_schedule(cat: Catalog, view: StudentView) -> dict[str, int]:
    """Fixed curriculum still ahead of a B.Tech CSE student (the buddy plans around it)."""
    if not view.is_cse:
        return {}
    return {
        code: course["curriculum_semester"]
        for code, course in cat.courses.items()
        if course["type"] in {"core", "project"} and course["curriculum_semester"]
        and course["curriculum_semester"] >= view.current_semester and code not in view.done
        and code not in view.backlogs
    }


def limits(cat: Catalog, view: StudentView) -> dict:
    credit_rule = cat.rule("credit_cap")
    headroom = int(view.constraints.get("credit_headroom", credit_rule.get("default_headroom", 6)))
    headroom = max(0, min(headroom, int(credit_rule.get("max_headroom", 12))))
    graduation = cat.rule("graduation")
    fraction = float(cat.rule("additional_credits").get("max_fraction_of_major", 0.33))
    sems = semesters_for(view)
    elective_rule = cat.rule("elective_slots").get("CS", {})
    lateral_rule = cat.rule("lateral_slots").get("non_CS", {})
    if view.is_cse:
        elective_cap = {s: int(elective_rule.get(str(s), 0)) for s in sems}
    else:
        declared = int(view.constraints.get("elective_slots", 0) or 0)
        elective_cap = {s: (2 if declared else 0) for s in sems}
    lateral_cap = {s: int(lateral_rule.get(str(s), 0)) for s in sems}
    elective_total = view.constraints.get("elective_slots")
    lateral_total = view.constraints.get("lateral_slots")
    return {
        "headroom": headroom,
        "weekly_hours": float(view.constraints.get("weekly_hours", 10)),
        "additional_total": int(fraction * int(graduation.get("min_credits", 172))),
        "elective_cap": elective_cap,
        "lateral_cap": lateral_cap,
        "elective_total": int(elective_total) if elective_total is not None else sum(elective_cap.values()),
        "lateral_total": int(lateral_total) if lateral_total is not None else sum(lateral_cap.values()),
        "not_together": [p for p in view.constraints.get("not_together", []) if isinstance(p, list) and len(p) == 2],
    }


def slot_options(course: dict, view: StudentView, eligible: bool) -> list[str]:
    options = []
    if course["type"] == "elective":
        options.append("elective")
    if course["type"] == "lateral" and course["dept"] != view.school:
        options.append("lateral")
    if not view.is_cse and course["type"] == "core" and course["dept"] == "CS":
        options.append("elective")  # a declared open/free elective slot may take a CSE subject
    if eligible:
        options.append("additional")
    return options


def plannable(course: dict, view: StudentView) -> bool:
    if course["type"] not in {"core", "elective", "lateral"} or not is_theory(course):
        return False
    if view.is_cse and course["type"] == "core":
        return False  # CSE core is fixed curriculum, never re-planned
    if view.is_cse and course["type"] == "lateral" and course["dept"] == "CS":
        return False  # CSE laterals are offered to other schools
    return True


class PlanState:
    def __init__(self, cat: Catalog, view: StudentView):
        self.cat, self.view = cat, view
        self.sems = semesters_for(view)
        self.limits = limits(cat, view)
        self.eligible, self.eligibility_reason = additional_eligible(cat, view)
        self.core_at = core_schedule(cat, view)
        self.data = {
            "placed": {},
            "items": {s: [] for s in self.sems},
            "credits": {s: 0 for s in self.sems},
            "hours": {s: 0.0 for s in self.sems},
            "slots": {s: {"elective": 0, "lateral": 0} for s in self.sems},
            "totals": {"elective": 0, "lateral": 0, "additional": 0},
            "activities": {s: [] for s in self.sems},
            "resources": {s: [] for s in self.sems},
        }
        self.visiting: set[str] = set()

    # ------------------------------------------------------------------ helpers
    def available_sem(self, code: str) -> int | None:
        if code in self.view.done:
            return -1
        if code in self.core_at:
            return self.core_at[code]
        return self.data["placed"].get(code)

    def codes_in(self, sem: int) -> set[str]:
        return {code for code, s in self.core_at.items() if s == sem} | {i["code"] for i in self.data["items"][sem]}

    def conflicts(self, code: str, sem: int) -> bool:
        present = self.codes_in(sem)
        return any(code in pair and (pair[1] if pair[0] == code else pair[0]) in present for pair in self.limits["not_together"])

    def fits(self, course: dict, sem: int, slot: str) -> bool:
        lim, data = self.limits, self.data
        if slot == "elective":
            return data["slots"][sem]["elective"] < lim["elective_cap"].get(sem, 0) and data["totals"]["elective"] < lim["elective_total"]
        if slot == "lateral":
            return data["slots"][sem]["lateral"] < lim["lateral_cap"].get(sem, 0) and data["totals"]["lateral"] < lim["lateral_total"]
        if slot == "additional":
            extra = course_extra_hours(course, self.cat)
            return (self.eligible and data["credits"][sem] + course["credits"] <= lim["headroom"]
                    and data["totals"]["additional"] + course["credits"] <= lim["additional_total"]
                    and data["hours"][sem] + extra <= lim["weekly_hours"])
        return False

    def assign(self, course: dict, sem: int, slot: str, reason: str, skill: str | None) -> None:
        data = self.data
        data["placed"][course["code"]] = sem
        if slot in ("elective", "lateral"):
            data["slots"][sem][slot] += 1
            data["totals"][slot] += 1
        if slot == "additional":
            data["credits"][sem] += course["credits"]
            data["totals"]["additional"] += course["credits"]
            data["hours"][sem] += course_extra_hours(course, self.cat)
        slot_text = {
            "elective": f"uses one of your elective slots in semester {sem}",
            "lateral": f"fills your lateral slot in semester {sem}",
            "additional": f"taken as an additional-credit subject ({self.eligibility_reason})",
            "backlog": "backlog subjects must be registered first when offered (Regulation 11.6)",
        }[slot]
        data["items"][sem].append({
            "code": course["code"], "title": course["title"], "credits": course["credits"], "slot": slot,
            "skills": sorted(self.cat.course_skills.get(course["code"], {})),
            "reason": f"{reason}; {slot_text}.",
        })

    def snapshot(self):
        return deepcopy(self.data)

    # ------------------------------------------------------------------ placement
    def place(self, code: str, min_sem: int, reason: str, skill: str | None, depth: int = 0) -> int | None:
        existing = self.available_sem(code)
        if existing is not None:
            return existing
        course = self.cat.courses.get(code)
        if (course is None or code in self.view.excluded or not plannable(course, self.view)
                or code in self.visiting or depth > 4):
            return None
        self.visiting.add(code)
        saved = self.snapshot()
        ready = min_sem
        for group in self.cat.prereq_groups.get(code, []):
            best = None
            for member in group:
                sem = self.available_sem(member)
                if sem is not None:
                    best = sem if best is None else min(best, sem)
            if best is None:
                for member in group:
                    sem = self.place(member, self.sems[0], f"Prerequisite for {code}", None, depth + 1)
                    if sem is not None:
                        best = sem
                        break
            if best is None:
                self.data = saved
                self.visiting.discard(code)
                return None
            ready = max(ready, best + 1)
        for sem in self.sems:
            if sem < ready or season_of(sem).lower() not in course["offered"] or self.conflicts(code, sem):
                continue
            for slot in slot_options(course, self.view, self.eligible):
                if self.fits(course, sem, slot):
                    self.assign(course, sem, slot, reason, skill)
                    self.visiting.discard(code)
                    return sem
        self.data = saved
        self.visiting.discard(code)
        return None

    SOFT_CAP = {"activities": 3, "resources": 3}

    def add_learning_item(self, kind: str, item: dict, preferred: int, hours: float, reason: str) -> int | None:
        order = [s for s in self.sems if s >= preferred] + [s for s in self.sems if s < preferred]
        # First pass respects a soft per-semester cap so work is spread out; second pass fills any time left.
        for capped in (True, False):
            for sem in order:
                if capped and len(self.data[kind][sem]) >= self.SOFT_CAP[kind]:
                    continue
                if self.data["hours"][sem] + hours <= self.limits["weekly_hours"]:
                    self.data["hours"][sem] += hours
                    self.data[kind][sem].append({**item, "hours_per_week": hours, "reason": reason})
                    return sem
        return None


# ---------------------------------------------------------------------- gap analysis
def skill_depth(cat: Catalog, skill: str, seen: frozenset = frozenset()) -> int:
    if skill in seen:
        return 0
    parents = cat.skill_prereqs.get(skill, [])
    return 0 if not parents else 1 + max(skill_depth(cat, p, seen | {skill}) for p in parents)


def compute_gaps(cat: Catalog, view: StudentView) -> list[dict]:
    p_init = cat.config["p_init"]
    rows = []
    for order, (skill, level) in enumerate(view.target_skills.items()):
        p = view.mastery.get(skill, p_init)
        target = level_target(level)
        if p >= target:
            continue
        rows.append({
            "skill_id": skill, "name": cat.skills[skill]["name"], "level": level, "p_mastery": round(p, 3),
            "target": target, "gap": round(target - p, 3), "tested": skill in view.tested,
            "interest": skill in view.interests, "depth": skill_depth(cat, skill), "order": order,
            "small": skill in view.tested and target - p <= SMALL_GAP,
        })
    # Most important goal skills first (required level), then interests, then foundations before dependants.
    rows.sort(key=lambda r: (-r["level"], -int(r["interest"]), r["depth"], -r["gap"], r["order"]))
    return rows


def rank_candidates(cat: Catalog, view: StudentView, skill: str, level: int, gap_skills: set[str], eligible: bool) -> list[str]:
    threshold = cat.config["mastery_threshold"]
    ranked = []
    for code, cover in cat.skill_courses.get(skill, []):
        course = cat.courses[code]
        if code in view.done or code in view.excluded or not plannable(course, view):
            continue
        skills = cat.course_skills.get(code, {})
        if skills and all(view.mastery.get(s, 0) >= threshold for s in skills):
            continue
        options = slot_options(course, view, eligible)
        if not options:
            continue
        multi = len(gap_skills & set(skills)) - 1
        interest = len(set(view.interests) & set(skills))
        uses_slot = options[0] in ("elective", "lateral")
        ranked.append(((-int(cover >= min(level, 3)), -cover, -multi, -interest, -int(uses_slot), course["credits"], code), code))
    return [code for _, code in sorted(ranked)]


def pick_resources(cat: Catalog, view: StudentView, skill: str, count: int, used: set[str]) -> list[dict]:
    p = view.mastery.get(skill, cat.config["p_init"])
    wanted_level = 1 if p < 0.4 else 2 if p < 0.7 else 3
    style = str(view.preferences.get("learning_style", "")).lower()
    order = next((v for k, v in FORMAT_PREFERENCE.items() if k in style), FORMAT_PREFERENCE["videos"])
    pool = [r for r in cat.resources.get(skill, []) if r["id"] not in used and r["url"] not in {u for u in used}]
    pool.sort(key=lambda r: (abs(r["level"] - wanted_level), order.index(r["format"]) if r["format"] in order else 9, r["est_hours"], r["id"]))
    chosen, urls = [], set()
    for r in pool:
        if r["url"] in urls:
            continue
        chosen.append(r)
        urls.add(r["url"])
        if len(chosen) == count:
            break
    return chosen


def pick_activity(cat: Catalog, view: StudentView, skill: str, used: set[str], kinds: list[str] | None = None) -> dict | None:
    style = str(view.preferences.get("learning_style", "")).lower()
    order = kinds or next((v for k, v in ACTIVITY_PREFERENCE.items() if k in style), ["exercise", "project", "case_study"])
    p = view.mastery.get(skill, cat.config["p_init"])
    wanted_level = 1 if p < 0.4 else 2 if p < 0.7 else 3
    pool = [x for x in cat.exercises.get(skill, []) if x["id"] not in used and x["kind"] in order]
    pool.sort(key=lambda x: (order.index(x["kind"]), abs(x["level"] - wanted_level), x["id"]))
    return pool[0] if pool else None


def milestone_semester(milestone: dict, sems: list[int]) -> int | None:
    first, last = sems[0], sems[-1]
    if "semester" in milestone:
        target = int(milestone["semester"])
        return target if first <= target <= last else (first if target < first and milestone.get("kind") not in {"placement", "exam", "application"} else None)
    if "season" in milestone:
        candidates = [s for s in sems if season_of(s) == milestone["season"] and (not milestone.get("before_final") or s <= 7)]
        preferred = [s for s in candidates if s >= 5] or candidates
        return preferred[0] if preferred else None
    return min(last, first + int(milestone.get("semester_offset", 0)))


# ---------------------------------------------------------------------- main entry
def build_plan(cat: Catalog, view: StudentView) -> dict:
    st = PlanState(cat, view)
    notes: list[str] = []
    if not st.sems:
        return {"semesters": [], "summary": {"gaps": [], "notes": ["No semesters remain to plan."]}, "rationale": "No semesters remain."}

    # 1. Backlogs first (Regulation 11.6).
    for code in view.backlogs:
        course = cat.courses[code]
        sem = next((s for s in st.sems if season_of(s).lower() in course["offered"]), None)
        if sem is None:
            notes.append(f"Backlog {code} is not offered in any remaining semester; speak to your faculty adviser.")
            continue
        st.assign(course, sem, "backlog", f"Clears your backlog in {code} {course['title']}", None)

    # 2. Courses for goal-skill gaps.
    gaps = compute_gaps(cat, view)
    gap_skills = {g["skill_id"] for g in gaps}
    coverage: dict[str, list[dict]] = {}
    uncovered: list[str] = []
    for gap in gaps:
        skill, level = gap["skill_id"], gap["level"]
        need = min(level, 2)
        covering = [(code, sem) for code, sem in st.core_at.items() if cat.course_skills.get(code, {}).get(skill, 0) >= need]
        covering += [(code, sem) for code, sem in st.data["placed"].items() if cat.course_skills.get(code, {}).get(skill, 0) >= need]
        if covering:
            coverage[skill] = [{"code": c, "semester": s, "via": "core" if c in st.core_at else "planned"} for c, s in sorted(covering, key=lambda x: x[1])]
            continue
        if gap["small"]:
            continue  # close to target: targeted practice is enough, no redundant course
        reason = (f"Closes your {gap['name']} gap (now {gap['p_mastery']:.0%}"
                  f"{'' if gap['tested'] else ', not yet tested'}; target {gap['target']:.0%} for this goal)")
        placed = None
        for code in rank_candidates(cat, view, skill, level, gap_skills, st.eligible):
            sem = st.place(code, st.sems[0], reason + f" - {code} covers it at level {cat.course_skills[code][skill]}", skill)
            if sem is not None:
                placed = (code, sem)
                break
        if placed:
            coverage[skill] = [{"code": placed[0], "semester": placed[1], "via": "planned"}]
        else:
            uncovered.append(skill)

    # 3. Active practice first, then open resources (passive content only fills remaining time).
    deferred_practice: list[tuple[str, float]] = []
    deferred_resources: list[tuple[str, float]] = []
    used_x: set[str] = set()
    used_r: set[str] = set()
    # Remediation for repeatedly missed skills comes before generic practice and content.
    threshold = int(cat.config.get("repeated_miss_threshold", 2))
    review_modules = []

    def add_refresher(res: dict, reason: str) -> None:
        item = {k: res[k] for k in ("id", "title", "url", "provider", "licence", "skill_id", "format", "est_hours")}
        if st.add_learning_item("resources", item, st.sems[0], hours_per_week(res["est_hours"] / 2, view.pace), reason) is None:
            deferred_resources.append((res["title"], 1.0))

    for skill, count in sorted(view.misses.items()):
        if count < threshold or view.mastery.get(skill, 0) >= view.target_for(skill):
            continue
        mods = [m for code, _ in cat.skill_courses.get(skill, []) for m in cat.modules.get(code, [])
                if m["skill_id"] == skill and m["kind"] in ("intro", "core")][:3]
        topics = ", ".join(view.missed_topics.get(skill, [])) or "recent questions"
        for m in mods:
            review_modules.append({**m, "reason": f"Missed {count} tested items on {cat.skills[skill]['name']} ({topics})"})
        for res in pick_resources(cat, view.evolve(mastery={**view.mastery, skill: 0.1}), skill, 1, used_r):
            used_r.update({res["id"], res["url"]})
            add_refresher(res, f"Extra explanation after repeated misses in {cat.skills[skill]['name']}")
        for parent in cat.skill_prereqs.get(skill, []):
            if view.mastery.get(parent, 0) < 0.7:
                for res in pick_resources(cat, view, parent, 1, used_r):
                    used_r.update({res["id"], res["url"]})
                    add_refresher(res, f"Prerequisite refresher: {cat.skills[parent]['name']} underpins {cat.skills[skill]['name']}")

    for gap in gaps:
        skill = gap["skill_id"]
        sem_pref = coverage[skill][0]["semester"] if skill in coverage else st.sems[0]
        sem_pref = max(st.sems[0], sem_pref)
        activity = pick_activity(cat, view, skill, used_x)
        if activity:
            used_x.add(activity["id"])
            hours = hours_per_week(activity["est_hours"], view.pace)
            sem = st.add_learning_item("activities", {k: activity[k] for k in ("id", "title", "kind", "skill_id", "est_hours")},
                                       sem_pref, hours, f"Hands-on practice to demonstrate {gap['name']}")
            if sem is None:
                deferred_practice.append((gap["name"], hours))
    # 5. Goal-level demonstrations of readiness.
    goal = cat.goals.get(view.goal_id or "", {})
    readiness = goal.get("readiness", {})
    late = max(st.sems[0], min(st.sems[-1], 6))
    projects = sum(1 for s in st.sems for a in st.data["activities"][s] if a["kind"] == "project")
    for skill in list(view.target_skills):
        if projects >= int(readiness.get("projects", 0)):
            break
        project = pick_activity(cat, view, skill, used_x, ["project"])
        if project and view.mastery.get(skill, 0) < cat.config["mastery_threshold"]:
            used_x.add(project["id"])
            if st.add_learning_item("activities", {k: project[k] for k in ("id", "title", "kind", "skill_id", "est_hours")},
                                    min(st.sems[-1], st.sems[0] + 1), hours_per_week(project["est_hours"], view.pace),
                                    "Goal readiness needs an end-to-end project as evidence") is not None:
                projects += 1
    if readiness.get("mock_test"):
        st.add_learning_item("activities", {"id": "MOCK-TEST", "title": "Timed mock test across your goal skills (in the app)",
                                            "kind": "mock_test", "skill_id": None, "est_hours": 2},
                             late, 0.5, f"Readiness needs {readiness['mock_test']['min_score']:.0%}+ on a timed mock test")
    for i in range(int(readiness.get("mock_interviews", 0))):
        st.add_learning_item("activities", {"id": f"MOCK-INTERVIEW-{i + 1}", "title": "Mock interview (placement cell, seniors or peers)",
                                            "kind": "mock_interview", "skill_id": "communication", "est_hours": 1},
                             min(st.sems[-1], late + i), 0.5, "Readiness needs mock interviews scored on a rubric")

    # Open resources only fill the time that is left.
    for gap in sorted(gaps, key=lambda g: g["skill_id"] in coverage):
        skill = gap["skill_id"]
        if gap["small"]:
            continue
        covered = skill in coverage
        count = 1 if covered else 2
        sem_pref = st.sems[0]
        if covered:
            course_sem = coverage[skill][0]["semester"]
            sem_pref = max(st.sems[0], course_sem - 1 if gap["p_mastery"] < 0.5 else course_sem)
        for k, res in enumerate(pick_resources(cat, view, skill, count, used_r)):
            used_r.update({res["id"], res["url"]})
            if not covered and k:
                sem_pref = st.sems[min(len(st.sems) - 1, st.sems.index(sem_pref) + 1)]  # second resource the next term
            why = (f"Prepares you for {coverage[skill][0]['code']}" if covered and sem_pref < coverage[skill][0]["semester"]
                   else f"Supports {coverage[skill][0]['code']}" if covered
                   else f"No course for {gap['name']} fits your slots and eligibility, so this open course closes the gap (non-credit)")
            item = {k: res[k] for k in ("id", "title", "url", "provider", "licence", "skill_id", "format", "est_hours")}
            res_hours = hours_per_week(res["est_hours"], view.pace)
            if st.add_learning_item("resources", item, sem_pref, res_hours, why) is None:
                deferred_resources.append((res["title"], res_hours))

    # 6. Eligibility notes and the best valid alternative when something is not possible.
    if not st.eligible:
        notes.append(f"Additional-credit subjects are not available: {st.eligibility_reason}. "
                     "The plan uses your slots and open resources instead.")
    if view.constraints.get("minor"):
        minor = cat.rule("minor")
        cs_subjects = [i for s in st.sems for i in st.data["items"][s] if cat.courses[i["code"]]["dept"] == "CS"]
        additional = [i for i in cs_subjects if i["slot"] == "additional"]
        if view.is_cse:
            notes.append("A Minor must be in a discipline other than your major.")
        elif not st.eligible:
            notes.append(f"A CSE Minor needs at least {minor.get('minimum_additional_subjects', 3)} subjects as additional credits, "
                         f"which requires CGPA >= {cat.rule('additional_credits').get('minimum_cgpa', 7.5)} with no backlogs. "
                         "Best valid option now: take CSE laterals and open resources, and revisit the Minor if your CGPA crosses the cut-off.")
        elif len(cs_subjects) < int(minor.get("subjects", 6)) or len(additional) < int(minor.get("minimum_additional_subjects", 3)):
            notes.append(f"This plan has {len(cs_subjects)} CSE subjects ({len(additional)} as additional credits); a Minor needs "
                         f"{minor.get('subjects', 6)} with at least {minor.get('minimum_additional_subjects', 3)} additional. "
                         "Raise your credit headroom or weekly hours to complete the Minor in time.")
    addressed = set(coverage) | {r["skill_id"] for s in st.sems for r in st.data["resources"][s]} | {
        a["skill_id"] for s in st.sems for a in st.data["activities"][s] if a.get("skill_id")}
    unaddressed = [g["skill_id"] for g in gaps if g["skill_id"] not in addressed]
    if deferred_practice or deferred_resources or unaddressed:
        short = sum(h for _, h in deferred_practice) + sum(h for _, h in deferred_resources)
        needed = st.limits["weekly_hours"] + math.ceil(short / max(1, len(st.sems)))
        message = (f"Not everything fits in {st.limits['weekly_hours']:g} h/week over {len(st.sems)} remaining semester(s). "
                   f"The plan does the highest-priority work first")
        if unaddressed:
            message += f"; {', '.join(cat.skills[s]['name'] for s in unaddressed)} could not be scheduled"
        message += f". Best options: raise your weekly hours to about {needed:g}, or narrow the goal (see goal fit)."
        if deferred_practice:
            message += " Deferred practice: " + ", ".join(n for n, _ in deferred_practice[:4]) + "."
        if deferred_resources:
            message += f" {len(deferred_resources)} open resource(s) deferred."
        notes.append(message)
    if goal.get("protect_cgpa") and (view.cgpa < 7.5 or view.backlogs):
        notes.append("Your goal rewards a strong CGPA: the plan keeps extra subjects light so core courses get priority.")

    # 7. Assemble semesters.
    semesters = []
    milestones = goal.get("milestones", [])
    for sem in st.sems:
        items = st.data["items"][sem]
        codes = [i["code"] for i in items]
        all_codes = codes + [c for c, s in st.core_at.items() if s == sem]
        skips = []
        for code in all_codes:
            for m in cat.modules.get(code, []):
                skill = m["skill_id"]
                if not skill:
                    continue
                p = view.mastery.get(skill, 0)
                if p >= cat.config["mastery_threshold"]:
                    skips.append({"id": m["id"], "title": m["title"], "skill_id": skill, "course_code": code,
                                  "reason": "Skill already demonstrated"})
                elif m["kind"] == "intro" and p >= 0.7 and skill in view.tested:
                    skips.append({"id": m["id"], "title": m["title"], "skill_id": skill, "course_code": code,
                                  "reason": "Introductory material you have already shown you know"})
        semesters.append({
            "semester": sem,
            "season": season_of(sem),
            "label": f"Semester {sem} · {season_of(sem)}",
            "core_codes": sorted(c for c, s in st.core_at.items() if s == sem),
            "courses": items,
            "course_codes": codes,
            "activities": st.data["activities"][sem],
            "resources": st.data["resources"][sem],
            "review_modules": review_modules if sem == st.sems[0] else [],
            "skip_modules": skips,
            "milestones": [{"title": m["title"], "kind": m["kind"]} for m in milestones if milestone_semester(m, st.sems) == sem],
            "load": {
                "additional_credits": st.data["credits"][sem], "headroom": st.limits["headroom"],
                "extra_hours": round(st.data["hours"][sem], 1),
                "weekly_limit": st.limits["weekly_hours"],
                "elective_slots_used": st.data["slots"][sem]["elective"], "elective_slots": st.limits["elective_cap"].get(sem, 0),
                "lateral_slots_used": st.data["slots"][sem]["lateral"], "lateral_slots": st.limits["lateral_cap"].get(sem, 0),
            },
        })
    met = [s for s in view.target_skills if s not in gap_skills]
    summary = {
        "goal": {"id": view.goal_id, "name": view.goal_name, "target_skills": view.target_skills},
        "gaps": gaps,
        "met_skills": met,
        "coverage": coverage,
        "uncovered": uncovered,
        "unaddressed": unaddressed,
        "eligibility": {"additional_credits": st.eligible, "reason": st.eligibility_reason},
        "limits": {k: v for k, v in st.limits.items() if k in ("headroom", "weekly_hours", "additional_total", "elective_total", "lateral_total")},
        "notes": notes,
    }
    return {"semesters": semesters, "summary": summary, "rationale": rationale_text(cat, view, summary)}


def rationale_text(cat: Catalog, view: StudentView, summary: dict) -> str:
    parts = [f"Goal: {view.goal_name}."]
    total = len(view.target_skills)
    met = summary["met_skills"]
    if total:
        parts.append(f"{len(met)} of {total} goal skills already meet their target"
                     + (f" ({', '.join(cat.skills[s]['name'] for s in met)})." if met else "."))
    closing = []
    for gap in summary["gaps"]:
        cover = summary["coverage"].get(gap["skill_id"])
        if cover:
            closing.append(f"{gap['name']} via {cover[0]['code']} (semester {cover[0]['semester']}{', core' if cover[0]['via'] == 'core' else ''})")
        else:
            closing.append(f"{gap['name']} via open resources and practice")
    if closing:
        parts.append("Gaps are closed in prerequisite order: " + "; ".join(closing) + ".")
    parts.append(("Additional credits allowed: " if summary["eligibility"]["additional_credits"] else "Additional credits not allowed: ")
                 + summary["eligibility"]["reason"] + ".")
    return " ".join(parts)


# ---------------------------------------------------------------------- validation
def validate(cat: Catalog, view: StudentView, semesters: list[dict]) -> list[str]:
    violations: list[str] = []
    lim = limits(cat, view)
    eligible, reason = additional_eligible(cat, view)
    core_at = core_schedule(cat, view)
    threshold = cat.config["mastery_threshold"]
    online = cat.rule("nptel_credit")
    if int(view.constraints.get("nptel_credits", 0)) > int(online.get("maximum_credits", 0)):
        violations.append(f"NPTEL credit total {view.constraints.get('nptel_credits')} exceeds the {online.get('maximum_credits', 0)}-credit rule")
    placed: dict[str, int] = {}
    totals = {"elective": 0, "lateral": 0, "additional": 0}
    previous = view.current_semester - 1
    for semester in semesters:
        if not isinstance(semester, dict):
            violations.append("Each semester must be an object")
            continue
        sem = semester.get("semester")
        if not isinstance(sem, int) or not view.current_semester <= sem <= MAX_SEMESTER:
            violations.append(f"Semester {sem!r} is outside the remaining semesters {view.current_semester}-{MAX_SEMESTER}")
            continue
        if sem <= previous:
            violations.append(f"Semester {sem} is out of order")
        previous = sem
        season = season_of(sem).lower()
        items = semester.get("courses")
        if items is None:
            items = [{"code": code, "slot": "additional"} for code in semester.get("course_codes", [])]
        credits = 0
        hours = 0.0
        slots = {"elective": 0, "lateral": 0}
        codes = []
        for item in items:
            code, slot = item.get("code"), item.get("slot", "additional")
            course = cat.courses.get(code)
            if course is None:
                violations.append(f"Unknown course code: {code}")
                continue
            codes.append(code)
            if code in view.excluded and slot != "backlog":
                violations.append(f"{code} is excluded by the student")
            if code in view.done:
                violations.append(f"{code} is already completed")
            if code in placed or code in core_at:
                violations.append(f"{code} is assigned more than once")
            if season not in course["offered"]:
                violations.append(f"{code} is not offered in {season_of(sem)} (semester {sem})")
            for group in cat.prereq_groups.get(code, []):
                if not any(m in view.done or (m in core_at and core_at[m] < sem) or (m in placed and placed[m] < sem) for m in group):
                    violations.append(f"{code} is missing prerequisite(s): {' or '.join(group)}")
            if slot == "backlog":
                if code not in view.backlogs:
                    violations.append(f"{code} is not a backlog")
            else:
                if not plannable(course, view):
                    violations.append(f"{code} cannot be chosen by this student (fixed curriculum, lab or project)")
                if slot not in slot_options(course, view, eligible):
                    violations.append(f"{code} cannot use the {SLOT_LABEL.get(slot, slot)}" + ("" if eligible or slot != "additional" else f": {reason}"))
                skills = cat.course_skills.get(code, {})
                if skills and all(view.mastery.get(s, 0) >= threshold for s in skills):
                    violations.append(f"{code} only covers already-mastered content")
                if slot == "additional":
                    credits += course["credits"]
                    hours += course_extra_hours(course, cat)
                    totals["additional"] += course["credits"]
                elif slot in slots:
                    slots[slot] += 1
                    totals[slot] += 1
            placed[code] = sem
        for kind in ("activities", "resources"):
            for entry in semester.get(kind, []):
                skill = entry.get("skill_id")
                if skill and entry.get("kind") not in ASSESSMENT_KINDS and view.mastery.get(skill, 0) >= threshold:
                    violations.append(f"{entry.get('title', entry.get('id'))} assigns already-mastered {skill} content")
                hours += float(entry.get("hours_per_week", 0))
        if credits > lim["headroom"]:
            violations.append(f"Semester {sem}: {credits} additional credits exceeds your {lim['headroom']}-credit headroom")
        if hours > lim["weekly_hours"] + 1e-9:
            violations.append(f"Semester {sem}: {hours:g} extra hours/week exceeds your {lim['weekly_hours']:g}-hour limit")
        if slots["elective"] > lim["elective_cap"].get(sem, 0):
            violations.append(f"Semester {sem}: {slots['elective']} elective slots used, only {lim['elective_cap'].get(sem, 0)} available")
        if slots["lateral"] > lim["lateral_cap"].get(sem, 0):
            violations.append(f"Semester {sem}: {slots['lateral']} lateral slots used, only {lim['lateral_cap'].get(sem, 0)} available")
        present = set(codes) | {c for c, s in core_at.items() if s == sem}
        for pair in lim["not_together"]:
            if set(pair) <= present:
                violations.append(f"Semester {sem}: {pair[0]} and {pair[1]} cannot be taken together")
    if totals["elective"] > lim["elective_total"]:
        violations.append(f"{totals['elective']} elective slots used, only {lim['elective_total']} remain")
    if totals["lateral"] > lim["lateral_total"]:
        violations.append(f"{totals['lateral']} lateral slots used, only {lim['lateral_total']} remain")
    if totals["additional"] > lim["additional_total"]:
        violations.append(f"{totals['additional']} additional credits exceed the {lim['additional_total']}-credit limit (33% of the major)")
    for code in view.backlogs:
        course = cat.courses[code]
        first = next((s for s in range(view.current_semester, MAX_SEMESTER + 1) if season_of(s).lower() in course["offered"]), None)
        if first is not None and placed.get(code) != first:
            violations.append(f"Backlog {code} must be registered in semester {first}, its first offering (Regulation 11.6)")
    return violations


def validate_plan(db, student, semesters: list[dict], mastery: dict[str, float] | None = None) -> list[str]:
    from app.catalog import build_view, load_catalog

    cat = load_catalog(db)
    view = build_view(db, student, cat, mastery)
    return validate(cat, view, semesters)


def greedy_plan(db, student, mastery: dict[str, float] | None = None) -> tuple[list[dict], str]:
    from app.catalog import build_view, load_catalog

    cat = load_catalog(db)
    view = build_view(db, student, cat, mastery)
    plan = build_plan(cat, view)
    return plan["semesters"], plan["rationale"]
