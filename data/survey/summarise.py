"""Summarise anonymised survey responses: python summarise.py responses.csv"""
import csv
import statistics
import sys
from collections import Counter

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
if not rows:
    sys.exit("No responses yet.")
print(f"Responses: {len(rows)}")
for field in ("programme", "year", "goal", "goal_outside_branch", "elective_source", "discovered_when", "knows_cgpa_rules", "weekly_hours", "preferred_format"):
    counts = Counter(r[field] for r in rows if r[field])
    print(f"\n{field}: " + ", ".join(f"{k} {v} ({v / len(rows):.0%})" for k, v in counts.most_common()))
for field in ("goal_certainty", "self_programming", "self_dsa", "self_maths", "self_communication", "self_goal_skill", "would_follow_plan"):
    values = [float(r[field]) for r in rows if r[field]]
    if values:
        print(f"{field}: median {statistics.median(values)}")
late = [r for r in rows if r["goal_outside_branch"] == "yes"]
if late:
    share = sum(r["discovered_when"] in ("3rd year", "4th year", "still don't know") for r in late) / len(late)
    print(f"\nGoal outside branch and discovered electives in 3rd year or later: {share:.0%} of {len(late)}")
