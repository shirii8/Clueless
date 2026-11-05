# Data and knowledge base

## Scope

The knowledge base covers **one programme in depth**: the B.Tech in Computer Science and Engineering at IIT Bhubaneswar. That includes the common first year, every core and lab course, the project and training courses, 18 electives, and the three CSE laterals offered to other schools. It also includes two Civil laterals that matter for policy-oriented goals. Students of other programmes are served through those laterals, declared open-elective slots and additional credits.

| Item | Count | Target in brief |
|---|---|---|
| Courses | 61 | 20-40 |
| Modules / lessons | 213 | 100-300 |
| Skills | 29 | 20-30 |
| Assessment questions + exercises/projects/mock assessments | 129 + 43 = 172 | 100+ |
| Open learning resources | 69 | - |
| Rules (cited) | 10 | - |
| Goal templates | 8 | - |
| Student profiles | 72 | 50-100 |

## Sources

| Source | Used for |
|---|---|
| IIT Bhubaneswar, *Curriculum Booklet: B.Tech CSE and Dual Degree CSE*, https://www.iitbbs.ac.in/curriculum_doc/Curriculum_Booklet-BTech_CSE-Dual-Degree_CSE_CSE.pdf | course codes, titles, L-T-P, credits, semester positions, prerequisites, syllabi, elective list (p.19), lateral list (p.74), elective/lateral slot structure (pp.17-18) |
| IIT Bhubaneswar, *B.Tech and Dual Degree Curriculum and Syllabus (SIF, 2019)*, https://www.iitbbs.ac.in/curriculum_doc/B.Tech.%20and%20Dual%20Curriculum%20and%20Syllabus%20Final%20SIF_21082019.pdf | Civil laterals CE2L012 (p.92) and CE3L031 (p.94) |
| IIT Bhubaneswar, *B.Tech Regulations (revised 2019)*, https://www.iitbbs.ac.in/curriculum_doc/B-Tech-Regulations-2019-31102020.pdf | additional credits (cl. 9, p.12), Minor (cl. 10, p.12), backlog registration and 28-contact-hour cap (cl. 11.6, p.14), graduation credits and Hons CGPA (cl. 15, p.22) |
| NPTEL (CC BY-SA), MIT OpenCourseWare (CC BY-NC-SA 4.0), Harvard CS50, MIT Missing Semester, OSTEP, Open Data Structures, NCERT, ACM CCR | 69 open resources, each with URL, provider, licence, format, estimated hours and level |
| Team-authored (CC BY 4.0) | 129 MCQs with explanations; 43 exercises, projects, case studies and mock assessments with rubrics; module breakdowns written from the syllabus topics |

Every course row carries `source_url` with a `#page=` anchor, `source_page`, `verification`, `verification_note` and `last_verified`. Every rule carries `source_url`, `verification` and `note`.

## Schema (reasoning-oriented)

- `courses` (code PK, credits, `ltp`, `contact_hours`, `curriculum_semester`, `semester_offered` Autumn/Spring, `type` first_year/core/elective/lateral/project, syllabus, objectives, `prerequisite_text` verbatim, source fields)
- `prerequisites(course_code, requires_code, group_id)`: rows in the same group are **OR** alternatives and groups are **AND**ed. Example: NLP needs MLDA-I *or* Data Mining.
- `skills`, `skill_prereqs` (a DAG used to order learning and pick refreshers), `course_skills(level 1-3)`
- `modules(course, position, kind intro/core/advanced, est_hours, skill)`: used for skipping material the student already knows and for review
- `questions(skill, difficulty 1-3, topic, options, answer, explanation)` and `exercises(kind, est_hours, level, rubric)`
- `resources(skill, url, provider, licence, format, est_hours, level, verified_on)`
- `rules(kind unique, params JSON, source_url, verification)`, read by the planner by kind (`additional_credits`, `minor`, `backlog_registration`, `credit_cap`, `elective_slots`, `lateral_slots`, `seasons`, `graduation`, `weekly_hours`, `nptel_credit`)
- `goals(target_skills{skill: level}, readiness criteria, milestones)`
- Student-side: `students`, `evidence`, `skill_state`, `diagnostic_progress`, `module_progress`, `assessments`, `plans` (versions + diff), `messages`, `memory`, `llm_calls`, `llm_cache`

## How accuracy and completeness were checked

1. **Transcription.** Course facts were extracted from the official PDFs with `pdftotext`, parsed from the per-course "Subject Code / Name / L-T-P / Credit / Prerequisite" headers, and checked by hand against the semester tables. Page anchors were verified per course.
2. **Automated checks** run at every start, at reset and via `make seed-report` ([seed.py](../api/app/seed.py)). Any failure stops loading:
   - unique IDs and codes; required fields; https sources;
   - credits and L-T-P are integers; types and seasons are valid;
   - every reference resolves; **no prerequisite cycles** (course or skill graph);
   - every MCQ's answer is one of its options, and options are distinct;
   - every skill has at least 3 questions and at least one course or resource;
   - profile references and ranges are valid.
3. **Cross-source consistency** checks are reported as notes rather than errors:
   - season versus curriculum semester parity;
   - credits versus L + T + ⌈P/2⌉;
   - documented conflicts between the institute's own documents:
     - CS3P001-CS3P004 lab credits: the syllabus says 2, but the semester totals imply 3;
     - CS6L008 / CS6L002: the elective list says 3-1-0 / 4 credits, the dual-degree section says 3-0-0 / 3.
   We keep the elective-list or syllabus value and record the conflict.
4. **Links.** Every resource URL was fetched on 2026-11-05 (HTTP 200). NPTEL course titles were confirmed from the page body, and six candidate URLs that returned 404 were dropped.
5. **Plan-level check.** `make evaluate` runs all 72 profiles through the planner and validator ([evaluation-report.md](evaluation-report.md)).

The current report is in [data-quality-report.txt](data-quality-report.txt).

## Verification status and known gaps (must read before advising real students)

| Status | Meaning | Items |
|---|---|---|
| verified | transcribed from the cited page | 35 courses; rules: additional credits, Minor, backlogs, elective slots, seasons, graduation |
| partial | code/credits from the table, syllabus from another school's document | ID2L003, MA2L006, CS2S001 |
| inferred | fact stated, offering season inferred | the 18 electives (which ones run is announced each semester); laterals' seasons from slot positions; the lateral-slot rule for non-CSE programmes |
| assumed | not found in the regulations; a conservative team assumption | per-semester credit headroom (student-declared, default 6, max 12); 1 h self-study per credit; **NPTEL credit transfer set to 0** (planned as non-credit learning until the academic section confirms a rule) |

Other gaps:
- The HSS breadth-course list isn't published in these documents, so humanities goals use the Civil laterals, first-year English and open resources.
- The specific CSE Minor subject list is not published; any CSE theory subject is treated as a candidate.
- The current semester's subject list (which electives run) should be checked each semester.

## Data ethics

We use only public institute documents, openly licensed content and team-authored items. All 72 student profiles are **fabricated**: 10 hand-written personas and 62 drawn from a seeded generator ([generate_profiles.py](../api/app/generate_profiles.py)). They contain no real grades or personal details. Survey responses (see [SURVEY.md](SURVEY.md)) are to be collected anonymously and stored without names, roll numbers or e-mails.
