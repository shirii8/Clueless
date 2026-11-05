# Clueless: a personalised learning buddy for IIT Bhubaneswar students

Clueless takes a student's goal (a software role, data science, MS/PhD, GATE, UPSC, a startup, an MBA or security) and turns it into a semester-by-semester plan built from the **official IIT Bhubaneswar B.Tech CSE curriculum** and the **2019 B.Tech regulations**. It then keeps adapting that plan as the student is tested:

**Assess → Personalise → Learn → Practise → Adapt → Demonstrate mastery**

- A **short adaptive diagnostic** asks at most 3 questions per goal skill, adjusts difficulty, and stops early once the result is clear.
- **Evidence is weighted by how reliable it is.** It runs through Bayesian Knowledge Tracing: tested results count most, grades count less, and self-declared skills can never reach mastery.
- **Plans are built and verified by deterministic code.** The checks cover prerequisites (AND-of-OR), Autumn/Spring offerings, elective and lateral slots, credit headroom, weekly hours, courses the student won't take together, the CGPA ≥ 7.50 / no-backlog rule for additional credits (Reg. 9), the Minor rule (Reg. 10) and backlogs-first (Reg. 11.6). A plan never repeats completed or mastered content.
- **Active practice comes first:** exercises, projects, case studies, timed mock tests and mock interviews. Open resources (NPTEL, MIT OCW and others, all link-checked) only fill the time that's left.
- **The plan adapts** to scores, number of attempts, time spent, repeatedly missed topics, goal changes and rejected courses. Every change creates a new plan version with a diff and an explanation.
- **Mastery is separated from completion.** Readiness for a goal needs tested evidence: skills at target, a timed mock test, graded projects and mock interviews.
- **A multi-turn buddy** answers "why is CS2L004 in my plan?", "what next?", "am I ready?", "what if I score low in linear algebra?" and side questions. It remembers the student across sessions and refuses prompt injection and off-topic requests.

The model only parses goals, explains changes, answers open questions, generates validated questions and grades rubric items. Everything works without a model key through deterministic fallbacks.

## Run it

Requirements: Docker with Compose v2 (linux/amd64, no GPU). Images total well under 5 GB (Python slim, Node Alpine standalone, Postgres Alpine, Adminer).

```sh
cp .env.example .env          # PowerShell: Copy-Item .env.example .env
# put your provider key in LLM_API_KEY (optional - everything works without it)
docker compose up --build
```

| Service | URL |
|---|---|
| Web app | http://localhost:3001 |
| API + OpenAPI docs | http://localhost:8000/docs |
| Adminer (database viewer) | http://localhost:8080 (system PostgreSQL, server `db`, user/password/db from `.env`, default `clueless` / `clueless-local-only` / `clueless`) |

The first start loads the seed files and builds a validated plan for all 72 profiles, which takes about 20 to 60 seconds. Ports can be changed with `WEB_PORT`, `API_PORT` and `ADMINER_PORT`. If you change the API port, also update `NEXT_PUBLIC_API_URL` and rebuild the web image.

| Command | What it does |
|---|---|
| `make reset` / `docker compose run --rm api python -m app.reset` | Drops all tables, reloads `data/seed`, and rebuilds every plan. This restores the original state (destructive). The Admin → System page has the same button. |
| `make test` / `docker compose run --rm api pytest` | Runs 26 backend tests, including the model path against a fake LiteLLM. |
| `make evaluate` / `docker compose run --rm api python -m app.evaluate` | Runs the evaluation checklist over every profile (see [docs/evaluation-report.md](docs/evaluation-report.md)). |
| `make seed-report` | Prints the data-quality report for the seed files. |
| `make profiles` | Regenerates the synthetic profiles (seeded, reproducible). |

**Demo path (3 to 5 minutes):** see [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Model configuration (LiteLLM)

Every model call goes through LiteLLM ([api/app/llm.py](api/app/llm.py)). Model, key and endpoint come only from environment variables. Nothing is hard-coded in the code or the image.

| Variable | Meaning |
|---|---|
| `LLM_MODEL` | e.g. `gemini/gemini-2.5-flash` (default), `openai/<model>`, `azure/<deployment>` |
| `LLM_API_KEY` | provider key (leave blank to run fully deterministic) |
| `LLM_API_BASE` | optional, for Azure or self-hosted endpoints |
| `EMBEDDING_MODEL` | not used; retrieval is structured SQL over the knowledge base |
| `LLM_TIMEOUT_S` | per-call timeout before falling back (default 25) |

**Tested model:** the solution targets `gemini/gemini-2.5-flash` (the `.env.example` default) at temperature 0. The automated suite exercises the model path with a fake LiteLLM `completion` (answers, caching, invented-code rejection, timeouts). We have **not** yet recorded a live acceptance run against the provider. Run `make test` with a key and walk through the demo script before submitting. No embedding model is used.

No other runtime network calls are made. `LITELLM_LOCAL_MODEL_COST_MAP=True` stops LiteLLM from downloading its price map. The web app loads no remote fonts or scripts. Resource links are only opened by the student's browser when clicked.

### Which parts use the model and which are deterministic

| Concern | Who does it | Context passed to the model |
|---|---|---|
| Course selection, scheduling, slots, credits, hours, eligibility, prerequisites | **Deterministic** ([planner.py](api/app/planner.py)) | none |
| Plan validation | **Deterministic** (`validate`), run on every saved plan and shown as "Constraint checks" | none |
| Mastery estimates, readiness, gaps, mismatches, goal fit | **Deterministic** (BKT in [mastery.py](api/app/mastery.py), [insights.py](api/app/insights.py)) | none |
| MCQ grading, diagnostic adaptivity, mock-test timing | **Deterministic** ([assessment.py](api/app/assessment.py)) | none |
| Plan questions in chat (why X, what next, readiness, what changed, eligibility, what-if, reject a course, change goal) | **Deterministic intent router** ([chat.py](api/app/chat.py)) | none |
| Goal parsing from free text | Model, then validated against goal IDs (keyword fallback) | goal text (≤600 chars) + goal IDs + skill IDs |
| Explaining a plan change in plain words | Model, rejected if it mentions any course code outside the plan (deterministic text otherwise) | trigger + diff + deterministic facts |
| Open/side questions in chat | Model, with a pinned context block, rejected if it invents a course code | pinned context (≤3.5k chars) + rolling summary + last 8 turns |
| Rubric grading of free text, projects | Model; without one, work is stored as "awaiting review" until a mentor grades it | rubric + submission (≤6k chars) |
| New practice questions | Model; kept only if it has 4 distinct options and one keyed answer | skill + existing stems |
| Summarising long sessions into memory | Model (extractive fallback) | older turns (≤6k chars) |

## Where the data lives

| What | Where |
|---|---|
| Seed knowledge base (plain CSV/JSON, mounted read-only at `/data/seed`, loaded at startup when the DB is empty) | [data/seed/](data/seed) |
| Courses (61), prerequisites, course-skill links, modules (213) | `courses.csv`, `prerequisites.csv`, `course_skills.csv`, `modules.csv` |
| Skills (29) and skill prerequisites | `skills.csv`, `skill_prereqs.csv` |
| Questions (129 MCQs) and activities (43 exercises/projects/case studies/mock assessments) | `questions.json`, `exercises.json` |
| Open resources (69, link-checked) | `resources.json` |
| Academic rules with citations and verification status (10) | `rules.csv` |
| Goal templates: target skills, readiness criteria, milestones (8) | `goals.json` |
| BKT parameters and evidence reliability weights | `bkt.json` |
| Student profiles (72, fabricated) and their seed evidence (340 rows) | `students.json`, `evidence.csv` |
| Mutable state: evidence, skill state, plan versions + diffs, assessments, chat messages, memory, model-call log and cache | Postgres volume `postgres-data` (inspect with Adminer) |
| Schema | [api/app/models.py](api/app/models.py) and [docs/DATA.md](docs/DATA.md) |

## Data control

- **Admin page** (`/admin`) lets you view and edit students (semester, CGPA, weekly hours, headroom, goal), scores/evidence (edit/delete), courses (title, credits, offering) and submissions (grade). Every save validates the input, recomputes skill state and re-plans. A course edit re-plans every student.
- **API:** `GET/PATCH /admin/students[/{id}]`, `GET/PATCH/DELETE /admin/evidence[/{id}]`, `GET/POST/PATCH /admin/courses[/{code}]`, `GET/PATCH /admin/assessments[/{id}]`, `POST /admin/reprocess`, `POST /admin/reset`, `GET /admin/data-quality`, `GET /admin/plans/check`, `GET /admin/llm-usage`. Full list at `/docs`.
- **Adminer** is bundled for inspection. Direct SQL edits there bypass re-processing, so press **Re-process everyone** (Admin → System) or call `POST /admin/reprocess` afterwards.

This is a local prototype with no authentication. Don't expose it beyond a trusted machine.

## Documentation

- [docs/TECHNICAL.md](docs/TECHNICAL.md): architecture, learning / planning / solving, memory and context management, mastery evaluation, data flow
- [docs/PRODUCT.md](docs/PRODUCT.md): users, problem, personas, requirements with acceptance criteria, personalisation strategy, mastery criteria, success metrics, evaluation process, trade-offs
- [docs/DATA.md](docs/DATA.md): sources (cited), schema, how accuracy and completeness were checked, known gaps
- [docs/SURVEY.md](docs/SURVEY.md): the student survey instrument and analysis plan (responses still to be collected)
- [docs/evaluation-report.md](docs/evaluation-report.md) and [docs/data-quality-report.txt](docs/data-quality-report.txt): generated reports
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md): the 3 to 5 minute demo video script
