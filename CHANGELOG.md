# Changelog

## 1.0.0 (2026-11-05)

### Knowledge base
- Replaced the SAMPLE catalog with IIT Bhubaneswar data, every course cited by PDF page: 61 courses (B.Tech CSE core, labs, projects, first year, 18 electives, 5 laterals), 213 modules, 29 skills with a prerequisite graph.
- Added 10 cited rules from the 2019 regulations, each with a verification status.
- Added 129 MCQs, 43 exercises/projects/mock assessments, 69 link-checked NPTEL / MIT OCW / OER resources, and 8 goal templates with readiness criteria and milestones.
- Added 72 fabricated profiles: the brief's S1024, the Appendix A personas, edge cases and 62 seeded synthetic profiles.
- Seed validation now checks references, cycles, answer keys and coverage, and documents cross-source inconsistencies.

### Planning and adaptation
- New deterministic planner and independent validator, covering:
  - remaining semesters with Autumn/Spring offerings;
  - fixed CSE curriculum; elective and lateral slots;
  - additional-credit eligibility, the 33% cap and the Minor rule;
  - backlogs first; credit headroom; weekly hours; not-together pairs;
  - AND-of-OR prerequisites; no mastered or completed content.
- Priority by goal level; active practice and readiness work scheduled before passive resources; remediation for repeatedly missed topics; honest infeasibility notes with the best valid option.
- Plan versions now carry a trigger, diff and explanation. Added overrides (backlogs protected), goal change with clarifying questions, strong-vs-weak quiz simulation, and a multi-semester journey simulation.

### Assessment and mastery
- Soft-evidence BKT with reliability weights, an attempt penalty, grade-derived evidence and a pace signal. Self-declared evidence is capped, and untested skills can't reach mastery.
- Multi-skill adaptive diagnostic (≤ 3 questions per skill, early stop, no repeats); adaptive practice; server-timed mock tests; rubric submissions (model-graded or mentor-graded); module completion tracked separately from mastery; goal readiness criteria.

### Conversation
- Guard against prompt injection, then a deterministic intent router, then the model with pinned context and a check for invented course codes, then a "back to your plan" line.
- Session history, rolling summaries, long-term memory and a "welcome back" message.

### Engineering
- LiteLLM gateway with retries, caching, a usage log and an offline cost map.
- Admin page and API for students, evidence, courses and submissions, plus reprocess, reset, data quality, the plan checklist and model usage.
- Evaluation harness: 72/72 profiles pass all 9 checks. 26 backend tests.
- Removed a real database credential from `.env.example`.

### Left to do
- Collect the student survey and replace the hypotheses in PRODUCT.md with findings.
- Run a live acceptance pass with the configured model and record it in the README.
- Confirm the inferred and assumed items in docs/DATA.md with the academic section (elective offerings, NPTEL credit transfer, Minor subject list).
- Add authentication before any deployment beyond a local machine.
