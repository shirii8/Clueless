"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import Page from "@/components/Page";
import { Badge, Button, Card, Notice } from "@/components/ui";
import { api, Catalog, post, saveStudentId } from "@/lib/api";

const PROGRAMMES = [
  "B.Tech Computer Science and Engineering", "B.Tech Chemical Engineering", "B.Tech Mechanical Engineering", "B.Tech Electrical Engineering",
  "B.Tech Civil Engineering", "B.Tech Electronics and Communication Engineering", "B.Tech Metallurgical and Materials Engineering",
];
const GRADES = ["EX", "A", "B", "C", "D", "P"];
const STYLES = ["short videos and hands-on coding problems", "reading textbooks and notes", "projects", "practice problems"];
const STEPS = ["About you", "Courses so far", "Your goal", "Time and preferences"];

type Result = { clarifying_question?: string; options?: { goal_id: string; name: string }[]; student?: { id: string } };

export default function OnboardingPage() {
  const router = useRouter();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [step, setStep] = useState(0);
  const [programme, setProgramme] = useState(PROGRAMMES[1]);
  const [semester, setSemester] = useState(3);
  const [cgpa, setCgpa] = useState(7.5);
  const [grades, setGrades] = useState<Record<string, string>>({});
  const [backlogs, setBacklogs] = useState<string[]>([]);
  const [goalText, setGoalText] = useState("");
  const [goalId, setGoalId] = useState<string | null>(null);
  const [interests, setInterests] = useState<string[]>([]);
  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [hours, setHours] = useState(10);
  const [headroom, setHeadroom] = useState(6);
  const [slots, setSlots] = useState(0);
  const [minor, setMinor] = useState(false);
  const [style, setStyle] = useState(STYLES[0]);
  const [clarify, setClarify] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api<Catalog>("/catalog").then(setCatalog).catch((e: Error) => setError(e.message)); }, []);
  const isCse = programme.includes("Computer Science");
  const past = useMemo(() => (catalog?.courses ?? []).filter((c) => c.curriculum_semester && c.curriculum_semester < semester
    && (c.type === "first_year" || (isCse && (c.type === "core" || c.type === "project")))), [catalog, semester, isCse]);
  const goal = catalog?.goals.find((g) => g.id === goalId);

  async function submit(chosenGoal = goalId) {
    setBusy(true); setError("");
    try {
      const result = await post<Result>("/students", {
        programme, current_semester: semester, cgpa, goal_text: goalText || goal?.name || "", goal_id: chosenGoal,
        completed_courses: past.filter((c) => !backlogs.includes(c.code)).map((c) => ({ code: c.code, grade: grades[c.code] || null })),
        backlogs, interests, self_ratings: ratings,
        constraints: { weekly_hours: hours, credit_headroom: headroom, elective_slots: isCse ? null : slots, not_together: [], minor },
        preferences: { learning_style: style, exclude_courses: [] },
      });
      if (result.clarifying_question) { setClarify(result); return; }
      if (!result.student) throw new Error("The API did not return a profile.");
      saveStudentId(result.student.id);
      router.push("/diagnostic");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not create the profile."); }
    finally { setBusy(false); }
  }

  return (
    <Page title="Create your profile" description="Four short steps. Anything you self-declare is treated as a weak signal until a diagnostic or graded work backs it up.">
      <ol className="mb-5 flex flex-wrap gap-2 text-sm" aria-label="Steps">
        {STEPS.map((name, i) => <li key={name}><button onClick={() => setStep(i)} className={`rounded-full px-3 py-1 ${i === step ? "bg-brand text-white" : i < step ? "bg-brand-soft text-brand" : "bg-subtle text-muted"}`}>{i + 1}. {name}</button></li>)}
      </ol>
      <Card className="max-w-4xl">
        {step === 0 && <div className="grid gap-4 md:grid-cols-3">
          <label className="text-sm font-medium md:col-span-3">Programme
            <select value={programme} onChange={(e) => setProgramme(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2">{PROGRAMMES.map((p) => <option key={p}>{p}</option>)}</select>
          </label>
          <label className="text-sm font-medium">Semester you are planning next
            <select value={semester} onChange={(e) => setSemester(Number(e.target.value))} className="mt-1 w-full rounded-lg border px-3 py-2">{[1, 2, 3, 4, 5, 6, 7, 8].map((s) => <option key={s} value={s}>{s} ({s % 2 ? "Autumn" : "Spring"})</option>)}</select>
          </label>
          <label className="text-sm font-medium">CGPA
            <input type="number" min={0} max={10} step={0.01} value={cgpa} onChange={(e) => setCgpa(Number(e.target.value))} className="mt-1 w-full rounded-lg border px-3 py-2" />
          </label>
          <p className="self-end text-xs text-muted">Additional-credit subjects and a Minor need CGPA 7.50+ with no backlogs (Regulation 9-10).</p>
        </div>}

        {step === 1 && <div>
          <p className="text-sm text-muted">These are the courses your curriculum had before semester {semester}. Add grades if you have them (grades are strong evidence), and mark any backlog.</p>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {past.map((c) => <div key={c.code} className="flex items-center justify-between gap-2 rounded-lg border border-line p-2 text-sm">
              <span><span className="font-mono text-xs text-brand">{c.code}</span> {c.title}</span>
              <span className="flex items-center gap-2">
                <select aria-label={`Grade for ${c.code}`} value={grades[c.code] ?? ""} onChange={(e) => setGrades({ ...grades, [c.code]: e.target.value })} className="rounded border px-1 py-0.5 text-xs">
                  <option value="">grade?</option>{GRADES.map((g) => <option key={g}>{g}</option>)}
                </select>
                <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={backlogs.includes(c.code)} onChange={(e) => setBacklogs(e.target.checked ? [...backlogs, c.code] : backlogs.filter((b) => b !== c.code))} />backlog</label>
              </span>
            </div>)}
            {!past.length && <p className="text-sm text-muted">Nothing yet - you are at the start of the programme.</p>}
          </div>
        </div>}

        {step === 2 && <div className="space-y-4">
          <label className="block text-sm font-medium">In your own words, what do you want this plan to get you to?
            <textarea value={goalText} onChange={(e) => { setGoalText(e.target.value); setGoalId(null); }} placeholder="e.g. A software role after graduation, even though I'm in Chemical Engineering" className="mt-1 min-h-24 w-full rounded-lg border px-3 py-2" />
          </label>
          <div>
            <p className="text-sm font-medium">Or pick the closest goal</p>
            <div className="mt-2 flex flex-wrap gap-2">{catalog?.goals.map((g) => <button key={g.id} onClick={() => setGoalId(g.id)} className={`rounded-full border px-3 py-1 text-sm ${goalId === g.id ? "border-brand bg-brand-soft text-brand" : "border-line"}`}>{g.name}</button>)}</div>
          </div>
          <div>
            <p className="text-sm font-medium">Interests and how confident you feel (self-declared, weak evidence)</p>
            <div className="mt-2 grid gap-2 md:grid-cols-3">
              {catalog?.skills.map((s) => <div key={s.id} className="flex items-center justify-between gap-2 rounded-lg border border-line px-2 py-1 text-sm">
                <label className="flex items-center gap-2"><input type="checkbox" checked={interests.includes(s.id)} onChange={(e) => setInterests(e.target.checked ? [...interests, s.id] : interests.filter((x) => x !== s.id))} />{s.name}</label>
                {interests.includes(s.id) && <select aria-label={`Confidence in ${s.name}`} value={ratings[s.id] ?? ""} onChange={(e) => setRatings({ ...ratings, [s.id]: Number(e.target.value) })} className="rounded border text-xs">
                  <option value="">confidence</option><option value={0.3}>low</option><option value={0.6}>medium</option><option value={0.9}>high</option></select>}
              </div>)}
            </div>
          </div>
        </div>}

        {step === 3 && <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm font-medium">Hours per week you can spend outside classes
            <input type="number" min={1} max={60} value={hours} onChange={(e) => setHours(Number(e.target.value))} className="mt-1 w-full rounded-lg border px-3 py-2" />
          </label>
          <label className="text-sm font-medium">Extra credits you could take per semester (headroom)
            <input type="number" min={0} max={12} value={headroom} onChange={(e) => setHeadroom(Number(e.target.value))} className="mt-1 w-full rounded-lg border px-3 py-2" />
          </label>
          {!isCse && <label className="text-sm font-medium">Open/free elective slots you can fill with CSE subjects
            <input type="number" min={0} max={6} value={slots} onChange={(e) => setSlots(Number(e.target.value))} className="mt-1 w-full rounded-lg border px-3 py-2" />
            <span className="mt-1 block text-xs text-muted">Check with your faculty adviser; lateral slots are counted automatically.</span>
          </label>}
          {!isCse && <label className="flex items-center gap-2 text-sm font-medium"><input type="checkbox" checked={minor} onChange={(e) => setMinor(e.target.checked)} /> I want a CSE Minor</label>}
          <label className="text-sm font-medium md:col-span-2">How do you like to learn?
            <select value={style} onChange={(e) => setStyle(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2">{STYLES.map((s) => <option key={s}>{s}</option>)}</select>
          </label>
        </div>}

        {clarify && <div className="mt-5"><Notice tone="brand">
          <p className="font-semibold">{clarify.clarifying_question}</p>
          <div className="mt-2 flex flex-wrap gap-2">{clarify.options?.map((o) => <button key={o.goal_id} onClick={() => { setGoalId(o.goal_id); setClarify(null); submit(o.goal_id); }} className="rounded-full border border-brand px-3 py-1 text-sm">{o.name}</button>)}</div>
        </Notice></div>}
        {error && <div className="mt-4"><Notice tone="bad">{error}</Notice></div>}
        <div className="mt-6 flex justify-between">
          <Button kind="secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</Button>
          {step < 3 ? <Button onClick={() => setStep(step + 1)}>Next</Button>
            : <Button disabled={busy || (!goalText.trim() && !goalId)} onClick={() => submit()}>{busy ? "Building your plan..." : "Create profile and start the diagnostic"}</Button>}
        </div>
        {goal && <p className="mt-3 text-xs text-muted">Goal skills: {Object.keys(goal.target_skills).map((s) => <Badge key={s}>{catalog?.skills.find((k) => k.id === s)?.name ?? s}</Badge>)}</p>}
      </Card>
    </Page>
  );
}
