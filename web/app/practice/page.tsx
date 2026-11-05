"use client";

import { useEffect, useRef, useState } from "react";
import Page from "@/components/Page";
import { Badge, Button, Card, NeedStudent, Notice } from "@/components/ui";
import { api, Catalog, Dashboard, pct, post, Question } from "@/lib/api";
import { useLoader, useStudentId } from "@/lib/useStudent";

type PracticeQ = Question & { target_difficulty: number; p_mastery: number; attempt: number; pool: { unseen: number; to_retry: number; total: number } };
type Result = { correct: boolean; feedback: string; p_before: number; p_mastery: number; target: number; plan_changed: boolean; plan_change: string | null };
type Submission = { status: string; score: number | null; feedback: string; plan_change?: string | null };

export default function PracticePage() {
  const [studentId, ready] = useStudentId();
  const dash = useLoader<Dashboard>(studentId ? () => api<Dashboard>(`/students/${studentId}/dashboard`) : null, [studentId]);
  const catalog = useLoader<Catalog>(() => api<Catalog>("/catalog"), []);
  const [skill, setSkill] = useState("");
  const [question, setQuestion] = useState<PracticeQ | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const started = useRef(Date.now());

  useEffect(() => {
    if (!skill && dash.data) setSkill(dash.data.diagnosis.gaps[0]?.skill_id ?? dash.data.diagnosis.skills[0]?.skill_id ?? "");
  }, [dash.data, skill]);

  async function load(next = skill, generate = false) {
    setError(""); setResult(null); setAnswer("");
    try {
      const q = generate ? await post<PracticeQ>(`/students/${studentId}/practice/${next}/generate`) : await api<PracticeQ>(`/students/${studentId}/practice/${next}`);
      setQuestion(q); started.current = Date.now();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load a question."); }
  }

  async function submit() {
    if (!question || !answer) return;
    setBusy(true);
    try {
      setResult(await post<Result>(`/students/${studentId}/practice/answer`, { question_id: question.id, answer, time_spent_s: Math.round((Date.now() - started.current) / 1000) }));
      dash.reload();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not grade the answer."); }
    finally { setBusy(false); }
  }

  if (ready && !studentId) return <Page title="Practice"><NeedStudent /></Page>;
  const gaps = dash.data?.diagnosis.gaps ?? [];
  const activities = (dash.data?.plan.semesters ?? []).flatMap((s) => s.activities.map((a) => ({ ...a, semester: s.semester })));
  const exercises = new Map((catalog.data?.exercises ?? []).map((x) => [x.id, x]));
  const modules = (dash.data?.plan.semesters ?? []).flatMap((s) => s.review_modules);

  return (
    <Page title="Practise" description="Questions adapt to your current estimate and avoid ones you've already got right. Every answer is evidence: it updates your skill estimate and, when something important changes, your plan.">
      <div className="grid gap-5 lg:grid-cols-[1.3fr_0.7fr]">
        <Card title="Practice question">
          <div className="flex flex-wrap items-center gap-2">
            <select aria-label="Skill" value={skill} onChange={(e) => { setSkill(e.target.value); setQuestion(null); setResult(null); }} className="rounded-lg border px-3 py-2 text-sm">
              {gaps.length > 0 && <optgroup label="Your goal gaps">{gaps.map((g) => <option key={g.skill_id} value={g.skill_id}>{g.name} ({pct(g.p_mastery)})</option>)}</optgroup>}
              <optgroup label="All skills">{catalog.data?.skills.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</optgroup>
            </select>
            <Button disabled={!skill} onClick={() => load()}>Next question</Button>
            <Button kind="secondary" disabled={!skill} onClick={() => load(skill, true)} >Generate a new one (model)</Button>
          </div>
          {question && <div className="mt-5 border-t border-line pt-4">
            <div className="flex flex-wrap gap-2 text-xs"><Badge tone="brand">Difficulty {question.difficulty}</Badge><Badge>{question.topic}</Badge><Badge>Attempt {question.attempt}</Badge><Badge>{question.pool.unseen} unseen in bank</Badge></div>
            <h2 className="mt-3 text-lg font-semibold">{question.stem}</h2>
            <fieldset className="mt-3 space-y-2"><legend className="sr-only">Options</legend>
              {question.options?.map((o) => <label key={o} className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-sm ${answer === o ? "border-brand bg-brand-soft" : "border-line"}`}>
                <input type="radio" name="practice" checked={answer === o} onChange={() => setAnswer(o)} />{o}</label>)}
            </fieldset>
            <Button className="mt-3" disabled={!answer || busy || !!result} onClick={submit}>{busy ? "Checking..." : "Check answer"}</Button>
          </div>}
          {result && <div className="mt-4 space-y-2">
            <Notice tone={result.correct ? "good" : "warn"}>{result.feedback}</Notice>
            <p className="text-sm text-muted">Estimate {pct(result.p_before)} → {pct(result.p_mastery)} (goal target {pct(result.target)}).</p>
            {result.plan_change && <Notice tone="brand">Your plan changed: {result.plan_change}</Notice>}
          </div>}
          {error && <div className="mt-4"><Notice tone="bad">{error}</Notice></div>}
        </Card>
        <div className="space-y-5">
          {modules.length > 0 && <Card title="Review modules" subtitle="Added because you missed tested items more than once.">
            <ul className="space-y-2 text-sm">{modules.map((m) => <ModuleRow key={m.id} studentId={studentId!} id={m.id} title={`${m.title} (${m.course_code})`} />)}</ul>
          </Card>}
          <Card title="Hands-on activities in your plan" subtitle="Projects and exercises count as evidence only after a rubric grade.">
            <ul className="space-y-3">{activities.filter((a) => exercises.has(a.id)).map((a) => <ActivityRow key={a.id} studentId={studentId!} id={a.id} title={a.title} semester={a.semester} rubric={exercises.get(a.id)?.rubric ?? []} description={exercises.get(a.id)?.description ?? ""} />)}</ul>
            {!activities.length && <p className="text-sm text-muted">No activities in your plan yet.</p>}
          </Card>
        </div>
      </div>
    </Page>
  );
}

function ModuleRow({ studentId, id, title }: { studentId: string; id: string; title: string }) {
  const [note, setNote] = useState("");
  return <li className="flex items-start justify-between gap-2"><span>{title}{note && <span className="block text-xs text-muted">{note}</span>}</span>
    <Button kind="ghost" className="px-0" onClick={() => post<{ note: string }>(`/students/${studentId}/modules/${id}/complete`).then((r) => setNote(r.note)).catch((e: Error) => setNote(e.message))}>Mark done</Button></li>;
}

function ActivityRow({ studentId, id, title, semester, rubric, description }: { studentId: string; id: string; title: string; semester: number; rubric: string[]; description: string }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [checks, setChecks] = useState<boolean[]>(rubric.map(() => false));
  const [result, setResult] = useState<Submission | null>(null);
  const [error, setError] = useState("");
  return <li className="rounded-lg bg-subtle p-3 text-sm">
    <div className="flex items-start justify-between gap-2"><span className="font-medium">{title}</span><Badge>Sem {semester}</Badge></div>
    <button onClick={() => setOpen(!open)} className="mt-1 text-xs text-brand underline">{open ? "Hide" : "Submit work"}</button>
    {open && <div className="mt-2 space-y-2">
      <p className="text-xs text-muted">{description}</p>
      <ul className="space-y-1">{rubric.map((r, i) => <li key={r}><label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={checks[i]} onChange={(e) => setChecks(checks.map((c, j) => (j === i ? e.target.checked : c)))} />{r}</label></li>)}</ul>
      <textarea aria-label="Submission" value={text} onChange={(e) => setText(e.target.value)} placeholder="Link to your repo or write-up, and what you did" className="min-h-20 w-full rounded-lg border p-2 text-xs" />
      <Button disabled={!text.trim()} onClick={() => post<Submission>(`/students/${studentId}/activities/${id}`, { text, checklist: checks }).then(setResult).catch((e: Error) => setError(e.message))}>Submit</Button>
      {result && <Notice tone={result.status === "graded" ? "good" : "brand"}>{result.status === "graded" ? `Graded ${pct(result.score)}. ` : ""}{result.feedback}</Notice>}
      {error && <Notice tone="bad">{error}</Notice>}
    </div>}
  </li>;
}
