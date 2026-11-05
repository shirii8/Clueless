"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import Page from "@/components/Page";
import { Badge, Button, Card, Loading, NeedStudent, Notice } from "@/components/ui";
import { api, pct, post, Question } from "@/lib/api";
import { useStudentId } from "@/lib/useStudent";

type Step = {
  done: boolean; skill_id?: string; skill?: string; question?: Question; question_number?: number; maximum_questions?: number;
  progress: { skills_done: number; skills_total: number };
  results?: { skill_id: string; name: string; answered: number; correct: number; stop_reason: string; p_mastery: number | null }[];
};
type Answer = { correct: boolean; feedback: string; skill_done: boolean; stop_reason: string; p_mastery: number; target: number; plan_change: string | null };

const STOP: Record<string, string> = { confident_strong: "stopped early: consistently correct", confident_weak: "stopped early: clear gap", question_limit: "3 questions", no_more_questions: "question bank exhausted" };

export default function DiagnosticPage() {
  const [studentId, ready] = useStudentId();
  const [step, setStep] = useState<Step | null>(null);
  const [answer, setAnswer] = useState("");
  const [last, setLast] = useState<Answer | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const started = useRef(Date.now());

  const load = useCallback(async () => {
    if (!studentId) return;
    try { setStep(await api<Step>(`/students/${studentId}/diagnostic`)); started.current = Date.now(); setAnswer(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load the diagnostic."); }
  }, [studentId]);
  useEffect(() => { load(); }, [load]);

  async function submit() {
    if (!step?.question || !answer) return;
    setBusy(true); setError("");
    try {
      const result = await post<Answer>(`/students/${studentId}/diagnostic/answer`, {
        question_id: step.question.id, answer, time_spent_s: Math.round((Date.now() - started.current) / 1000),
      });
      setLast(result);
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not record the answer."); }
    finally { setBusy(false); }
  }

  async function restart() {
    await post(`/students/${studentId}/diagnostic/reset`);
    setLast(null);
    await load();
  }

  if (ready && !studentId) return <Page title="Diagnostic"><NeedStudent /></Page>;
  const total = step?.progress.skills_total ?? 0;
  const doneCount = step?.progress.skills_done ?? 0;
  return (
    <Page title="Short adaptive diagnostic" description="At most three questions per goal skill. Questions get harder after a correct answer and easier after a wrong one, and a skill stops early once the evidence is clear.">
      <div className="grid gap-5 lg:grid-cols-[1.4fr_0.6fr]">
        <Card>
          <div className="mb-4">
            <div className="flex justify-between text-xs text-muted"><span>Skills covered</span><span>{doneCount} / {total}</span></div>
            <div className="mt-1 h-2 rounded-full bg-subtle"><div className="h-2 rounded-full bg-brand" style={{ width: `${total ? (doneCount / total) * 100 : 0}%` }} /></div>
          </div>
          {!step && !error && <Loading />}
          {step && !step.done && step.question && <div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge tone="brand">{step.skill}</Badge>
              <Badge>Question {step.question_number} of up to {step.maximum_questions}</Badge>
              <Badge>Difficulty {step.question.difficulty}</Badge>
            </div>
            <h2 className="mt-3 text-lg font-semibold">{step.question.stem}</h2>
            <fieldset className="mt-4 space-y-2">
              <legend className="sr-only">Options</legend>
              {step.question.options?.map((option) => (
                <label key={option} className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 text-sm ${answer === option ? "border-brand bg-brand-soft" : "border-line"}`}>
                  <input type="radio" name="answer" value={option} checked={answer === option} onChange={() => setAnswer(option)} />{option}
                </label>
              ))}
            </fieldset>
            <div className="mt-4 flex gap-2">
              <Button disabled={!answer || busy} onClick={submit}>{busy ? "Checking..." : "Submit answer"}</Button>
              <Button kind="ghost" disabled={busy} onClick={() => { setAnswer("I don't know"); }}>I don&apos;t know</Button>
            </div>
          </div>}
          {step?.done && <div>
            <Notice tone="good">Diagnostic complete. Your evidence has been recorded and your plan rebuilt from it.</Notice>
            <table className="mt-4 w-full text-left text-sm">
              <thead className="text-xs text-muted"><tr><th className="py-1">Skill</th><th>Correct</th><th>Estimate</th><th>Why it stopped</th></tr></thead>
              <tbody>{step.results?.map((r) => <tr key={r.skill_id} className="border-t border-line"><td className="py-2">{r.name}</td><td>{r.correct}/{r.answered}</td><td>{pct(r.p_mastery)}</td><td className="text-xs text-muted">{STOP[r.stop_reason] ?? r.stop_reason}</td></tr>)}</tbody>
            </table>
            <div className="mt-4 flex gap-2"><Link href="/plan" className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white">See my plan</Link><Button kind="secondary" onClick={restart}>Retake</Button></div>
          </div>}
          {error && <div className="mt-4"><Notice tone="bad">{error}</Notice></div>}
        </Card>
        <Card title="Last answer">
          {last ? <div className="space-y-2 text-sm">
            <p className={last.correct ? "text-good" : "text-bad"}>{last.feedback}</p>
            <p className="text-muted">Estimate now {pct(last.p_mastery)} (goal target {pct(last.target)}).</p>
            {last.skill_done && <p className="text-muted">This skill is done ({STOP[last.stop_reason] ?? last.stop_reason}).</p>}
            {last.plan_change && <Notice tone="brand">{last.plan_change}</Notice>}
          </div> : <p className="text-sm text-muted">Feedback appears here after each answer. Answering &quot;I don&apos;t know&quot; is better than guessing - it keeps your plan honest.</p>}
        </Card>
      </div>
    </Page>
  );
}
