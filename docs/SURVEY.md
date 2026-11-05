# Student survey

**Status: instrument ready; responses not yet collected.** Don't report findings until real, anonymised responses are in [`data/survey/responses.csv`](../data/survey/responses_template.csv). Copy the template, keep the column names and run `python data/survey/summarise.py data/survey/responses.csv`.

## Consent and anonymity

Start the form with: "This survey is for a student project building a study-planning assistant at IIT Bhubaneswar. It is anonymous: do not enter your name, roll number or e-mail. Participation is voluntary and you can stop at any time." Collect only the fields below. Don't enable e-mail collection in the form tool.

## Questionnaire (about 5 minutes)

1. Programme (CSE / ECE / EE / ME / CE / CH / MM / other)
2. Current year (1-4/5)
3. Main goal after graduation (software / data / core engineering / higher studies India / higher studies abroad / GATE-PSU / UPSC or government / MBA / startup / undecided)
4. How sure are you about that goal? (1-5)
5. Is your goal outside your branch? (yes / no / partly)
6. How do you choose electives, laterals and breadth subjects? (seniors / faculty adviser / notice board / curriculum PDF / friends / other)
7. When did you first learn which electives or laterals would help your goal? (before 2nd year / 2nd year / 3rd year / 4th year / still don't know)
8. Do you know the CGPA and backlog conditions for additional credits and a Minor? (yes, exactly / roughly / no)
9. Have you used NPTEL, MIT OCW or similar? For what? (multi-select)
10. Rate yourself 1-5 on: programming, data structures and algorithms, maths, communication, your goal's main skill
11. Hours per week you can spend on learning outside classes (0-3 / 4-7 / 8-12 / 13-20 / 20+)
12. Biggest obstacle to preparing for your goal (open text)
13. Would you follow a semester plan that explains why each course is there? (1-5)
14. What would make you trust such a plan? (open text)
15. Preferred learning format (short videos / reading / projects / practice problems)

## Analysis plan

- Counts and percentages for Q1-Q9, Q11 and Q15; medians for Q4, Q10 and Q13.
- Cross-tabulate Q5 (goal outside branch) × Q7 (discovered too late) to test the "too late, through seniors" hypothesis.
- Compare Q10 self-ratings with in-app diagnostic results for volunteers, to calibrate the self-declared weight (currently 0.15).
- Code the open text (Q12, Q14) into themes. Each theme becomes a persona refinement or a requirement in [PRODUCT.md](PRODUCT.md).
- Feed findings back into the system: weekly-hour defaults, goal templates and learning-style options.

## Summary of results

_To be filled in from the collected responses._
