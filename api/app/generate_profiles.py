"""Generate the synthetic student profiles and their seed evidence (data/seed/students.json, evidence.csv).

All profiles are fabricated (no real student records). Ten hand-written personas cover the problem
statement's example (S1024), the Appendix A personas and the edge cases it asks for (backlogs,
changing goals, interest that conflicts with evidence, students just under an eligibility cut-off).
The rest are drawn from a seeded RNG so the set is reproducible and too varied to hand-tune for.

Usage: python -m app.generate_profiles [--count 62] [--seed-dir data/seed]
"""
import argparse
import csv
import json
import random
from pathlib import Path

GRADES = ["EX", "A", "B", "C", "D", "P"]
FIRST_YEAR = ["MA1L001", "PH1L001", "ME1L001", "EE1L001", "CS1L001", "CS1P001", "MA1L002", "CY1L001", "HS1L001"]
CSE_CORE_BY_SEM = {
    3: ["EC2L001", "ID2L002", "CS2L001", "CS2L004", "EC2L002", "EC2P001", "EC2P002", "CS2P002"],
    4: ["ID2L003", "MA2L006", "CS2L002", "EC2L004", "CS2P001", "EC2P004", "CS2S001"],
    5: ["CS3L001", "CS3L002", "CS3L005", "CS3P001", "CS3P003"],
    6: ["CS3L003", "CS3L006", "CS3P002", "CS3P004"],
    7: ["CS4L001", "CS4P001", "CS4D001", "CS4T001"],
}
PROGRAMMES = [
    ("B.Tech Computer Science and Engineering", 0.30), ("B.Tech Chemical Engineering", 0.12),
    ("B.Tech Mechanical Engineering", 0.14), ("B.Tech Electrical Engineering", 0.14),
    ("B.Tech Civil Engineering", 0.12), ("B.Tech Electronics and Communication Engineering", 0.10),
    ("B.Tech Metallurgical and Materials Engineering", 0.08),
]
GOALS = {
    "software_engineering": ("I want a software engineering job after graduation.", ["programming", "algorithms", "web_development", "machine_learning"]),
    "data_science": ("I want to become a data scientist or data analyst.", ["machine_learning", "data_analysis", "probability_statistics"]),
    "higher_studies": ("I plan to do an MS or PhD abroad and work in research.", ["machine_learning", "research_methods", "algorithms"]),
    "gate": ("I want to crack GATE and join an M.Tech at an IIT or IISc.", ["algorithms", "operating_systems", "databases"]),
    "upsc": ("I am preparing for the UPSC civil services exam.", ["public_policy", "economics", "environment_policy"]),
    "startup": ("I want to build and launch my own startup.", ["entrepreneurship", "web_development", "software_engineering"]),
    "mba": ("I want to do an MBA and move into product management.", ["economics", "communication", "data_analysis"]),
    "security": ("I want to work in cybersecurity.", ["security", "computer_networks", "programming"]),
}
GOAL_WEIGHTS = [("software_engineering", 0.27), ("data_science", 0.2), ("higher_studies", 0.14), ("gate", 0.1),
                ("upsc", 0.1), ("startup", 0.08), ("mba", 0.06), ("security", 0.05)]
GOAL_SKILLS = {
    "software_engineering": ["programming", "data_structures", "algorithms", "databases", "operating_systems", "computer_networks"],
    "data_science": ["programming", "probability_statistics", "linear_algebra", "data_analysis", "machine_learning", "databases"],
    "higher_studies": ["linear_algebra", "probability_statistics", "algorithms", "research_methods", "technical_writing"],
    "gate": ["discrete_math", "data_structures", "algorithms", "operating_systems", "databases", "computer_networks"],
    "upsc": ["public_policy", "economics", "communication", "environment_policy"],
    "startup": ["entrepreneurship", "software_engineering", "web_development", "communication"],
    "mba": ["probability_statistics", "economics", "communication", "data_analysis"],
    "security": ["programming", "computer_networks", "operating_systems", "security"],
}
STYLES = ["short videos and hands-on coding problems", "reading textbooks and notes", "projects", "practice problems", "videos"]


def grade_near(rng: random.Random, cgpa: float) -> str:
    points = max(5, min(10, round(rng.gauss(cgpa, 0.9))))
    return {10: "EX", 9: "A", 8: "B", 7: "C", 6: "D", 5: "P"}[points]


def completed_for(rng: random.Random, school: str, semester: int, cgpa: float, backlogs: list[str]) -> list[dict]:
    done = []
    first_year = FIRST_YEAR if semester >= 3 else FIRST_YEAR[:6] if semester == 2 else []
    for code in first_year:
        done.append({"code": code, "grade": grade_near(rng, cgpa)})
    if school == "CS":
        for sem in range(3, semester):
            for code in CSE_CORE_BY_SEM.get(sem, []):
                if code not in backlogs:
                    done.append({"code": code, "grade": grade_near(rng, cgpa)})
    return done


def persona_profiles() -> tuple[list[dict], list[list]]:
    profiles, evidence = [], []

    def add(profile, rows):
        profiles.append(profile)
        for i, (skill, kind, value, items, source) in enumerate(rows, start=1):
            evidence.append([f"EV-{profile['id']}-{i:02}", profile["id"], skill, kind, value, items, 1, 600 if kind == "assessed" else 0, source, ""])

    fy = lambda grades: [{"code": c, "grade": grades.get(c, "B")} for c in FIRST_YEAR]  # noqa: E731
    add({"id": "S1024", "name": "Persona: ChemE to software (problem-statement example)", "persona": "non-CS to software",
         "programme": "B.Tech Chemical Engineering", "year": 3, "current_semester": 5, "cgpa": 7.8,
         "goal_text": "Software engineering role after graduation",
         "goal_struct": {"goal": "Software engineering role", "goal_id": "software_engineering"},
         "completed_courses": fy({"CS1L001": "B"}), "backlogs": [], "interests": ["machine_learning"],
         "constraints": {"elective_slots": 2, "credit_headroom": 6, "weekly_hours": 8, "not_together": [["CS2L001", "CS2L004"]]},
         "preferences": {"learning_style": "short videos and hands-on coding problems", "exclude_courses": []}},
        [("programming", "assessed", 0.78, 5, "diagnostic"), ("discrete_math", "assessed", 0.55, 5, "diagnostic"),
         ("data_structures", "assessed", 0.32, 5, "diagnostic"), ("algorithms", "assessed", 0.32, 5, "diagnostic"),
         ("databases", "assessed", 0.10, 5, "diagnostic"), ("machine_learning", "self_declared", 0.9, 1, "onboarding")])
    add({"id": "P-CHE-SWE", "name": "Persona: 2nd-year ChemE aiming for software (Appendix A)", "persona": "non-CS to software",
         "programme": "B.Tech Chemical Engineering", "year": 2, "current_semester": 3, "cgpa": 8.1,
         "goal_text": "I want a software / IT role after graduation even though I am in Chemical Engineering.",
         "goal_struct": {"goal": "Software / IT role", "goal_id": "software_engineering"},
         "completed_courses": fy({"CS1L001": "A"}), "backlogs": [], "interests": ["web_development"],
         "constraints": {"elective_slots": 0, "credit_headroom": 6, "weekly_hours": 12, "not_together": []},
         "preferences": {"learning_style": "practice problems", "exclude_courses": []}},
        [("programming", "assessed", 0.7, 5, "diagnostic"), ("data_structures", "assessed", 0.3, 5, "diagnostic"),
         ("web_development", "self_declared", 0.8, 1, "onboarding")])
    add({"id": "P-EE-MS", "name": "Persona: EE student targeting an MS/PhD (Appendix A)", "persona": "higher studies",
         "programme": "B.Tech Electrical Engineering", "year": 3, "current_semester": 5, "cgpa": 8.7,
         "goal_text": "I want to do a PhD in machine learning abroad.",
         "goal_struct": {"goal": "Higher studies: PhD in ML", "goal_id": "higher_studies"},
         "completed_courses": fy({"MA1L002": "A", "CS1L001": "A"}), "backlogs": [], "interests": ["machine_learning"],
         "constraints": {"elective_slots": 1, "credit_headroom": 8, "weekly_hours": 14, "not_together": []},
         "preferences": {"learning_style": "reading textbooks and notes", "exclude_courses": []}},
        [("linear_algebra", "assessed", 0.82, 5, "diagnostic"), ("probability_statistics", "assessed", 0.6, 5, "diagnostic"),
         ("research_methods", "self_declared", 0.7, 1, "onboarding")])
    add({"id": "P-ME-UPSC", "name": "Persona: Mechanical student preparing for UPSC (Appendix A)", "persona": "civil services",
         "programme": "B.Tech Mechanical Engineering", "year": 2, "current_semester": 4, "cgpa": 7.2,
         "goal_text": "I am preparing for the UPSC civil services exam (IAS).",
         "goal_struct": {"goal": "UPSC civil services", "goal_id": "upsc"},
         "completed_courses": fy({}), "backlogs": [], "interests": ["public_policy"],
         "constraints": {"credit_headroom": 4, "weekly_hours": 12, "not_together": []},
         "preferences": {"learning_style": "reading textbooks and notes", "exclude_courses": []}},
        [("public_policy", "assessed", 0.4, 5, "diagnostic"), ("economics", "assessed", 0.35, 5, "diagnostic")])
    add({"id": "P-CSE-STARTUP", "name": "Persona: CSE student building a startup (Appendix A)", "persona": "startup",
         "programme": "B.Tech Computer Science and Engineering", "year": 2, "current_semester": 3, "cgpa": 8.0,
         "goal_text": "I want to build and launch a startup.",
         "goal_struct": {"goal": "Build and launch a venture", "goal_id": "startup"},
         "completed_courses": fy({}), "backlogs": [], "interests": ["entrepreneurship"],
         "constraints": {"credit_headroom": 4, "weekly_hours": 10, "not_together": []},
         "preferences": {"learning_style": "projects", "exclude_courses": []}},
        [("entrepreneurship", "self_declared", 0.9, 1, "onboarding"), ("web_development", "assessed", 0.45, 5, "diagnostic")])
    add({"id": "P-CE-DS-MISMATCH", "name": "Edge case: data science goal, weak linear algebra evidence", "persona": "interest-evidence mismatch",
         "programme": "B.Tech Civil Engineering", "year": 3, "current_semester": 5, "cgpa": 6.9,
         "goal_text": "I want a data science role, but maths has been difficult for me.",
         "goal_struct": {"goal": "Data science role", "goal_id": "data_science"},
         "completed_courses": fy({"MA1L002": "D", "MA1L001": "C"}), "backlogs": [], "interests": ["machine_learning", "data_analysis"],
         "constraints": {"credit_headroom": 4, "weekly_hours": 9, "not_together": []},
         "preferences": {"learning_style": "videos", "exclude_courses": []}},
        [("linear_algebra", "assessed", 0.2, 5, "diagnostic"), ("probability_statistics", "quiz", 0.35, 3, "practice"),
         ("machine_learning", "self_declared", 1.0, 1, "onboarding")])
    add({"id": "P-CH-MINOR-CUTOFF", "name": "Edge case: wants a CSE Minor at CGPA 7.49", "persona": "eligibility cut-off",
         "programme": "B.Tech Chemical Engineering", "year": 2, "current_semester": 4, "cgpa": 7.49,
         "goal_text": "I want a CSE minor and a data analytics job.",
         "goal_struct": {"goal": "Data analytics with a CSE minor", "goal_id": "data_science"},
         "completed_courses": fy({}), "backlogs": [], "interests": ["data_analysis"],
         "constraints": {"credit_headroom": 8, "weekly_hours": 14, "minor": True, "not_together": []},
         "preferences": {"learning_style": "practice problems", "exclude_courses": []}},
        [("programming", "self_declared", 1.0, 1, "onboarding"), ("probability_statistics", "assessed", 0.5, 5, "diagnostic")])
    add({"id": "P-CSE-BACKLOG", "name": "Edge case: CSE student with backlogs aiming for GATE", "persona": "backlogs",
         "programme": "B.Tech Computer Science and Engineering", "year": 3, "current_semester": 6, "cgpa": 6.4,
         "goal_text": "I want to clear GATE and do an M.Tech.",
         "goal_struct": {"goal": "GATE / M.Tech", "goal_id": "gate"},
         "completed_courses": fy({}), "backlogs": ["CS2L002", "MA2L006"], "interests": ["operating_systems"],
         "constraints": {"credit_headroom": 0, "weekly_hours": 10, "not_together": []},
         "preferences": {"learning_style": "practice problems", "exclude_courses": []}},
        [("algorithms", "assessed", 0.3, 5, "diagnostic"), ("operating_systems", "quiz", 0.6, 3, "practice"),
         ("probability_statistics", "quiz", 0.2, 3, "practice"), ("probability_statistics", "quiz", 0.3, 3, "practice")])
    add({"id": "P-CSE-GOALCHANGE", "name": "Edge case: switching from placements to higher studies", "persona": "changing goal",
         "programme": "B.Tech Computer Science and Engineering", "year": 3, "current_semester": 6, "cgpa": 8.9,
         "goal_text": "I was preparing for placements but now I want to do an MS in AI abroad.",
         "goal_struct": {"goal": "Higher studies: MS in AI", "goal_id": "higher_studies", "previous_goal_id": "software_engineering"},
         "completed_courses": fy({}), "backlogs": [], "interests": ["artificial_intelligence", "machine_learning"],
         "constraints": {"credit_headroom": 6, "weekly_hours": 12, "not_together": []},
         "preferences": {"learning_style": "reading textbooks and notes", "exclude_courses": []}},
        [("algorithms", "assessed", 0.85, 5, "diagnostic"), ("programming", "assessed", 0.9, 5, "diagnostic"),
         ("data_structures", "assessed", 0.88, 5, "diagnostic"), ("research_methods", "self_declared", 0.6, 1, "onboarding")])
    add({"id": "P-CSE-FINAL-SWE", "name": "Persona: final-year CSE student checking placement readiness", "persona": "placement readiness",
         "programme": "B.Tech Computer Science and Engineering", "year": 4, "current_semester": 7, "cgpa": 8.3,
         "goal_text": "I want to be ready for software placements this semester.",
         "goal_struct": {"goal": "Software engineering role", "goal_id": "software_engineering"},
         "completed_courses": fy({}), "backlogs": [], "interests": ["web_development"],
         "constraints": {"credit_headroom": 3, "weekly_hours": 10, "not_together": []},
         "preferences": {"learning_style": "practice problems", "exclude_courses": []}},
        [("algorithms", "mock_test", 0.75, 8, "mock test"), ("data_structures", "assessed", 0.85, 5, "diagnostic"),
         ("programming", "project", 0.9, 1, "project"), ("communication", "mock_interview", 0.7, 1, "mock interview")])
    # Completed CSE core for the CSE personas.
    rng = random.Random(7)
    for p in profiles:
        if "Computer Science" in p["programme"]:
            p["completed_courses"] += [{"code": c, "grade": grade_near(rng, p["cgpa"])}
                                       for s in range(3, p["current_semester"]) for c in CSE_CORE_BY_SEM.get(s, []) if c not in p["backlogs"]]
    return profiles, evidence


def weighted(rng: random.Random, pairs):
    return rng.choices([p for p, _ in pairs], weights=[w for _, w in pairs])[0]


def generate(count: int, seed: int = 2026) -> tuple[list[dict], list[list]]:
    profiles, evidence = persona_profiles()
    rng = random.Random(seed)
    for index in range(1, count + 1):
        programme = weighted(rng, PROGRAMMES)
        school = "CS" if "Computer Science" in programme else "OTHER"
        semester = rng.choice([2, 3, 3, 4, 4, 5, 5, 6, 6, 7])
        cgpa = round(min(9.8, max(5.4, rng.gauss(7.6, 1.0))), 2)
        if rng.random() < 0.12:
            cgpa = rng.choice([7.45, 7.49, 7.5, 7.52])  # near the additional-credit cut-off
        goal_id = weighted(rng, GOAL_WEIGHTS)
        goal_text, interest_pool = GOALS[goal_id]
        backlogs = []
        if rng.random() < 0.12 and semester >= 4:
            pool = [c for s in range(3, semester) for c in CSE_CORE_BY_SEM.get(s, []) if c.startswith(("CS2L", "CS3L", "MA2L"))] if school == "CS" else []
            backlogs = rng.sample(pool, k=min(len(pool), rng.choice([1, 2]))) if pool else []
            cgpa = min(cgpa, round(rng.uniform(5.6, 6.9), 2))
        interests = rng.sample(interest_pool, k=rng.choice([1, 2]))
        goal_struct = {"goal": goal_text.rstrip("."), "goal_id": goal_id}
        if rng.random() < 0.1:
            goal_struct["previous_goal_id"] = rng.choice([g for g in GOALS if g != goal_id])
        sid = f"SYN-{index:03}"
        constraints = {
            "credit_headroom": rng.choice([0, 3, 4, 6, 6, 8]),
            "weekly_hours": rng.choice([6, 8, 10, 12, 15, 20]),
            "not_together": [],
        }
        if school != "CS" and rng.random() < 0.4:
            constraints["elective_slots"] = rng.choice([1, 2])
        if school != "CS" and goal_id in ("software_engineering", "data_science") and rng.random() < 0.3:
            constraints["minor"] = True
        excluded = []
        if rng.random() < 0.15:
            excluded = [rng.choice(["CS6L034", "ID6L004", "CS6L011", "CS4L012", "CE2L012", "CS3L007", "CS6L019"])]
        if rng.random() < 0.15:
            constraints["not_together"] = [rng.choice([["CS6L034", "CS6L011"], ["ID6L004", "CS4L012"], ["CS2L001", "CS2L004"]])]
        profiles.append({
            "id": sid, "name": f"Synthetic profile {index}", "persona": f"synthetic:{goal_id}",
            "programme": programme, "year": (semester + 1) // 2, "current_semester": semester, "cgpa": cgpa,
            "goal_text": goal_text, "goal_struct": goal_struct,
            "completed_courses": completed_for(rng, "CS" if school == "CS" else "X", semester, cgpa, backlogs),
            "backlogs": backlogs, "interests": interests, "constraints": constraints,
            "preferences": {"learning_style": rng.choice(STYLES), "exclude_courses": excluded},
        })
        skills = rng.sample(GOAL_SKILLS[goal_id], k=rng.choice([2, 3, 4]))
        base = (cgpa - 5) / 5
        for i, skill in enumerate(skills, start=1):
            value = round(min(1, max(0, rng.gauss(base * 0.8, 0.22))), 2)
            evidence.append([f"EV-{sid}-{i:02}", sid, skill, "assessed", value, 5, 1, rng.randint(300, 1200), "diagnostic", ""])
        for j, skill in enumerate(interests, start=len(skills) + 1):
            evidence.append([f"EV-{sid}-{j:02}", sid, skill, "self_declared", 0.9, 1, 1, 0, "onboarding", ""])
        if rng.random() < 0.2:  # topics repeatedly missed
            skill = skills[0]
            for k in range(2):
                evidence.append([f"EV-{sid}-M{k + 1}", sid, skill, "quiz", 0.0, 1, rng.choice([1, 2, 3]), rng.randint(90, 300), "practice", "fundamentals"])
    return profiles, evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=62)
    parser.add_argument("--seed-dir", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "seed")
    args = parser.parse_args()
    profiles, evidence = generate(args.count)
    (args.seed_dir / "students.json").write_text(json.dumps(profiles, indent=1) + "\n", encoding="utf-8")
    with (args.seed_dir / "evidence.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "student_id", "skill_id", "kind", "value", "items", "attempts", "time_spent_s", "source", "topic"])
        writer.writerows(evidence)
    print(f"Wrote {len(profiles)} profiles and {len(evidence)} evidence rows to {args.seed_dir}")


if __name__ == "__main__":
    main()
