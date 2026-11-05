"use client";

import { useEffect, useState } from "react";
import Page from "@/components/Page";
import { Badge, Button, Card, Loading, Meter, NeedStudent, Notice } from "@/components/ui";
import { api, pct, post, Question, Readiness, SkillRow } from "@/lib/api";
import { useLoader, useStudentId } from "@/lib/useStudent";

type Progress = {
  completed_courses: { code: string; title: string; grade: string | null; skills: string[]; demonstrated: string[]; status: string }[];
  assumed_completed: string[]; skills: SkillRow[]; readiness: Readiness; mastery_threshold: number;
  assessments: { id: string; kind: string; status: string; score: number | null; created_at: string | null; feedback: string; details: { over_time?: boolean } }[];
};
type Mock = { assessment_id: string; time_limit_s: number; questions: Question[] };
type MockResult = { score: number; elapsed_s: number; time_limit_s: number; over_time: boolean; per_skill: Record<string, number>; review: { question_id: string; stem: string; correct: boolean; feedback: string }[]; plan_change: string };

export default function ProgressPage() {
  const [studentId, ready] = useStudentId();
  const progress = useLoader<Progress>(studentId ? () => api<Progress>(`/students/${studentId}/progress`) : null, [studentId]);
  const [filter, setFilter] = useState<"goal" | "all">("goal");
  if (ready && !studentId) return <Page title="Progress"><NeedStudent /></Page>;
  const p = progress.data;
  const skills = (p?.skills ?? []).filter((s) => filter === "all" || s.goal_level).sort((a, b) => b.p_mastery - a.p_mastery);
  return (
    <Page title="Progress and mastery" description="Completing a course and demonstrating proficiency are tracked separately. Mastery means an 85%+ estimate backed by tested evidence; self-declared skills never count.">
      {progress.error && <Notice tone="bad">{progress.error}</Notice>}
      {!p && !progress.error && <Loading />}
      {p && <div className="space-y-5">
        <Card title={`Goal readiness: ${p.readiness.goal}`} action={<Badge tone={p.readiness.ready ? "good" : "warn"}>{p.readiness.ready ? "Ready" : "Not yet"}</Badge>}>
          <p className="text-sm">{p.readiness.summary}</p>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">{p.readiness.criteria.map((c) => <li key={c.name} className={`rounded-lg border p-3 text-sm ${c.met ? "border-good/40 bg-good-soft" : "border-line"}`}>
            <p className="font-medium">{c.met ? "✓ " : ""}{c.name}</p><p className="text-xs text-muted">{c.detail}</p></li>)}</ul>
        </Card>
        <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
          <Card title="Skill estimates" action={<div className="flex gap-1 text-xs">{(["goal", "all"] as const).map((f) => <button key={f} onClick={() => setFilter(f)} className={`rounded px-2 py-1 ${filter === f ? "bg-brand text-white" : "bg-subtle"}`}>{f === "goal" ? "Goal skills" : "All skills"}</button>)}</div>}>
            <ul className="space-y-4">{skills.map((s) => <li key={s.skill_id}>
              <div className="flex flex-wrap justify-between gap-2 text-sm"><span className="font-medium">{s.name}</span>
                <span className="flex items-center gap-2"><Badge tone={s.mastered ? "good" : s.status === "gap" ? "warn" : "neutral"}>{s.status}</Badge><span className="tabular-nums">{pct(s.p_mastery)}</span></span></div>
              <div className="mt-1.5"><Meter value={s.p_mastery} target={s.target} mastered={p.mastery_threshold} label={s.name} /></div>
              <p className="mt-1 text-xs text-muted">Evidence: {s.evidence}{s.sources.length ? ` (${s.sources.join(", ")})` : ""}</p>
            </li>)}</ul>
          </Card>
          <div className="space-y-5">
            {studentId && <MockTest studentId={studentId} onDone={progress.reload} />}
            <Card title="Completed vs demonstrated">
              <ul className="space-y-2 text-sm">{p.completed_courses.filter((c) => c.skills.length).map((c) => <li key={c.code} className="rounded-lg bg-subtle p-2">
                <div className="flex justify-between gap-2"><span><span className="font-mono text-xs">{c.code}</span> {c.title}</span><span className="text-xs">{c.grade ?? ""}</span></div>
                <p className={`text-xs ${c.status.includes("not yet") ? "text-warn" : "text-good"}`}>{c.status}</p>
              </li>)}</ul>
              {p.assumed_completed.length > 0 && <p className="mt-2 text-xs text-muted">Also assumed done from your curriculum position: {p.assumed_completed.length} courses.</p>}
            </Card>
            <Card title="Assessments">
              <ul className="space-y-2 text-sm">{p.assessments.map((a) => <li key={a.id} className="flex justify-between gap-2"><span>{a.kind.replace("_", " ")} <span className="text-xs text-muted">{a.created_at?.slice(0, 10)}</span></span>
                <span>{a.status === "graded" ? pct(a.score) : <Badge>{a.status.replace("_", " ")}</Badge>}{a.details?.over_time ? " (over time)" : ""}</span></li>)}</ul>
              {!p.assessments.length && <p className="text-sm text-muted">No mock tests or graded work yet.</p>}
            </Card>
          </div>
        </div>
      </div>}
    </Page>
  );
}

function MockTest({ studentId, onDone }: { studentId: string; onDone: () => void }) {
  const [mock, setMock] = useState<Mock | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [left, setLeft] = useState(0);
  const [result, setResult] = useState<MockResult | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!mock || result) return;
    const timer = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(timer);
  }, [mock, result]);
  async function start() {
    setError(""); setResult(null); setAnswers({});
    try { const m = await post<Mock>(`/students/${studentId}/mock-test`); setMock(m); setLeft(m.time_limit_s); } catch (e) { setError(e instanceof Error ? e.message : "Could not start."); }
  }
  async function submit() {
    if (!mock) return;
    try { setResult(await post<MockResult>(`/students/${studentId}/mock-test/${mock.assessment_id}`, { answers })); onDone(); } catch (e) { setError(e instanceof Error ? e.message : "Could not submit."); }
  }
  return <Card title="Timed mock test" subtitle="Mixed questions across your goal skills, timed by the server. Readiness only counts tests finished within the limit.">
    {!mock && <Button onClick={start}>Start a mock test</Button>}
    {mock && !result && <div>
      <p className={`text-sm font-semibold tabular-nums ${left < 60 ? "text-bad" : ""}`}>Time left {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</p>
      <ol className="mt-3 space-y-4">{mock.questions.map((q, i) => <li key={q.id} className="text-sm"><p className="font-medium">{i + 1}. {q.stem}</p>
        <div className="mt-1 space-y-1">{q.options?.map((o) => <label key={o} className="flex items-center gap-2 text-xs"><input type="radio" name={q.id} checked={answers[q.id] === o} onChange={() => setAnswers({ ...answers, [q.id]: o })} />{o}</label>)}</div></li>)}</ol>
      <Button className="mt-3" onClick={submit}>Submit test</Button>
    </div>}
    {result && <div className="space-y-2 text-sm">
      <Notice tone={result.score >= 0.7 && !result.over_time ? "good" : "warn"}>Score {pct(result.score)} in {Math.round(result.elapsed_s / 60)} min{result.over_time ? " - over the time limit" : ""}.</Notice>
      <ul className="space-y-1 text-xs">{result.review.filter((r) => !r.correct).map((r) => <li key={r.question_id}><span className="font-medium">{r.stem}</span> - {r.feedback}</li>)}</ul>
      <p className="text-xs text-muted">{result.plan_change}</p>
      <Button kind="secondary" onClick={start}>Take another</Button>
    </div>}
    {error && <div className="mt-2"><Notice tone="bad">{error}</Notice></div>}
  </Card>;
}
