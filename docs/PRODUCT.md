# Product rationale

## Target users and problem

**Users** are IIT Bhubaneswar B.Tech students, especially those whose ambition doesn't match their branch: a Chemical Engineering student aiming for software, a Civil student aiming for data science, any branch preparing for UPSC, or a CSE student switching to an MS. Faculty advisers and mentors are secondary users who grade submissions and correct data from the Admin page.

**The problem:** the academic journey is largely one-size-fits-all. Students discover useful electives, laterals, the additional-credit rule (CGPA ≥ 7.50 and no backlogs) and the Minor rule late, usually through seniors. They track neither what they can actually do nor whether their goal is realistic given their time.

## Survey findings

The survey instrument and analysis plan are in [SURVEY.md](SURVEY.md). **No responses have been collected yet, so no findings are reported here.** The hypotheses below (taken from the brief's personas and the regulations) are what the survey is designed to test. Replace this section with the results once responses come in.

| Hypothesis to test | Survey question(s) |
|---|---|
| Non-CS students find useful electives and laterals too late, mostly through seniors | Q6, Q7 |
| Students don't know the additional-credit / Minor CGPA rule | Q8 |
| Self-rated skill is higher than tested skill | Q10 versus the in-app diagnostic |
| Available time outside classes is under 10 h/week for most students | Q11 |
| Students would follow a plan that explains its reasons | Q13, Q14 |

## Personas

Each persona exists in the seed data.

| Persona (profile) | Goal | What the buddy does |
|---|---|---|
| S1024: ChemE, sem 5, CGPA 7.8, 8 h/week, 6 credits of headroom, 2 open-elective slots, no Discrete + DSA together | Software role | Programming practice → CS2L004 Data Structures (elective slot, sem 5) → CS2L002 Algorithms (sem 6) → Networks, OS, Databases as additional credits within 6 credits and 8 h; flags that Communication and mock interviews need more hours |
| P-CHE-SWE: 2nd-year ChemE | Software | Same sequence starting in semester 3, with no open slots, so additional credits are used |
| P-EE-MS: EE, CGPA 8.7 | PhD in ML | Research methods and writing via projects and papers; ML electives; GRE/TOEFL and SOP milestones; protects CGPA |
| P-ME-UPSC: Mechanical, CGPA 7.2 | UPSC | Civil laterals CE2L012 / CE3L031 in lateral slots; NCERT and NPTEL policy and economy; weekly answer writing; prelims timeline; no additional credits (CGPA < 7.5) |
| P-CSE-STARTUP | Startup | Software engineering, web and game-theory electives; customer interviews → MVP → pitch; incubation cell / E-Cell flagged as outside what the buddy tracks |
| P-CE-DS-MISMATCH: Civil, CGPA 6.9, weak linear algebra (D grade, 20% assessed), ML self-declared | Data science | Surfaces the goal-versus-evidence gap; open courses and practice for linear algebra first; shows goal fit to support reassessing the goal |
| P-CH-MINOR-CUTOFF: CGPA 7.49 | CSE Minor + analytics | Explains that the Minor needs 7.50; offers the best valid route now (laterals + open resources) |
| P-CSE-BACKLOG: 2 backlogs | GATE | Backlogs registered first; no additional credits; GATE mock tests; refuses to drop a backlog |
| P-CSE-GOALCHANGE | Placements → MS | Goal change produces a new plan version with an explanation |
| P-CSE-FINAL-SWE | Placement readiness | Readiness checklist: mock test, project and interviews |

## Prioritised requirements with acceptance criteria

| # | Requirement | Acceptance criteria |
|---|---|---|
| P0 | Valid plans | 100% of plans pass `validate()` (prerequisites, offerings, slots, headroom, hours, pairs, eligibility, backlogs). Verified over 72 profiles. |
| P0 | Grounded recommendations | Every course exists in the KB, is cited by code and has a reason; model text that mentions an unknown code is discarded |
| P0 | Evidence-weighted diagnosis | Self-declared skills never reach mastery; mastery requires tested evidence; the source of each item is shown |
| P0 | Short adaptive diagnostic | ≤ 3 questions per skill, adaptive difficulty, early stop, no repeated questions |
| P1 | Adaptation | A strong versus weak quiz produces different plans; repeated misses add review modules and refreshers; rejecting a course gives a valid replacement and explains the trade-off; a goal change re-plans with an explanation |
| P1 | Honest infeasibility | When something can't fit, the plan says what and gives the best valid option |
| P1 | Mastery ≠ completion | Progress separates "completed" from "demonstrated"; readiness needs tested, timed or graded evidence |
| P1 | Multi-turn buddy with memory | Answers why / next / ready / what-changed / what-if; returns to the plan; remembers across sessions; refuses injection and off-topic requests; asks a clarifying question for vague goals |
| P2 | Data control | Admin edits re-plan immediately; reset restores the seed; data-quality report available |

## Learning objectives (per goal)

These come from `goals.json`. Each goal lists target skills at levels 1 to 3. For example, software engineering needs programming, data structures and algorithms at level 3, and databases, OS, networks, software engineering and communication at level 2. The objective is that **every goal skill reaches its target with tested evidence by the semester of the goal's main milestone** (placements in semester 7, GATE in semester 8, and so on).

## Learning journey

Onboarding (4 steps) → diagnostic (≤ 3 questions per goal skill) → plan (what you know, what to improve, why each item, next steps) → practise (adaptive questions, hands-on activities, review modules) → adapt (each answer, grade or goal change re-plans with a visible diff) → demonstrate (timed mock test, graded project, mock interviews → readiness).

## Personalisation strategy and conflicting signals

- **Reliability weighting:** assessed and mock tests 0.95 > grades 0.90 × coverage depth > quiz 0.85 ≈ project > exercise 0.80 > mock interview 0.75 ≫ self-declared 0.15. Self-declared skills are capped below 0.49.
- **Interest versus evidence:** interest raises a skill's priority among gaps of the same level and breaks ties in course choice, but it never raises the estimate. When tested evidence is weak for an interest or a level-2+ goal skill, the buddy:
  1. surfaces the conflict as a "goal and evidence disagree" card;
  2. adds remediation and prerequisite refreshers;
  3. shows the fit of related goals so the student can reassess.

  Both signals stay visible; neither is ignored.
- **Learning style** changes which resource format and activity type come first, never whether practice happens.
- **Constraints** are hard: rules and stated preferences (pairs, exclusions, hours, headroom) are never violated.

## Mastery criteria (examples)

| Goal | Mastery / readiness |
|---|---|
| Software role | ≥ 75% of goal skills at target with tested evidence; timed mock test ≥ 70% within time; 1 graded project; 2 mock interviews ≥ 60% |
| Data science | same structure, with statistics/ML/data analysis skills and a timed SQL-and-statistics mock |
| Higher studies | ≥ 70% of skills at target; 1 research project graded |
| GATE | ≥ 80% of skills at target; mock test ≥ 65% |
| UPSC | ≥ 70% at target; prelims-style mock ≥ 60%; 1 mock interview |

## Success metrics

- **Plan quality:** validity rate (target 100%; currently 100% over 72 profiles), gap coverage (99.8%) and determinism (100%).
- **Learning:** change in diagnostic estimates over 4 weeks; share of goal skills moving to "demonstrated"; mock-test scores.
- **Engagement:** share of students following their plan for 4+ weeks (practice answers or submissions each week).
- **Trust:** student-rated usefulness of recommendations and explanations (in-app rating to add); rate of course rejections.
- **Cost:** tokens per active student per week (`/admin/llm-usage`) and fallback rate.

## Evaluation process

1. **Automated checklist over every profile** (`make evaluate`): valid, catalog-only, goal coverage, active practice, no repeats, explained, deterministic, adapts (strong versus weak quiz), override. Current result: 72/72 pass ([evaluation-report.md](evaluation-report.md)).
2. **Scenario tests** (`make test`): the brief's S1024 sequence and limits, eligibility at 7.49, backlogs first, mastered content never assigned, remediation after repeated misses, the chat guard against injection, the model path with fakes.
3. **Journey simulation:** strong versus weak semesters for the same persona (Plan page → "Simulate remaining semesters").
4. **User testing (planned):** 5 to 8 students from different branches complete onboarding and the diagnostic, then rate whether the plan is realistic and the reasons are clear.

## Key trade-offs

- **Skill-building electives versus CGPA and core workload:** additional credits consume the student's declared headroom and weekly hours, and goals that reward CGPA (higher studies, GATE, UPSC) keep extra subjects light when CGPA < 7.5.
- **Courses (credit, slower) versus open resources (no credit, flexible):** courses are preferred when a slot or eligibility allows; otherwise open resources plus graded practice.
- **Active practice before passive content:** practice and readiness demonstrations get weekly time before videos and readings.
- **Short diagnostic versus precision:** 3 questions per skill keeps onboarding to about 5 minutes. Precision improves continuously through practice evidence.
- **Deterministic planning versus model flexibility:** correctness and repeatability over model creativity. The model only explains and converses.
