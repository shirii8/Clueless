"use client";

import { useState } from "react";
import Page from "@/components/Page";
import { Badge, Button, Card, Notice } from "@/components/ui";
import { api, patch, pct, post } from "@/lib/api";
import { useLoader } from "@/lib/useStudent";

type Student = { id: string; name: string; programme: string; current_semester: number; cgpa: number; goal_text: string; goal_struct: { goal_id?: string }; constraints: { weekly_hours?: number; credit_headroom?: number }; backlogs: string[] };
type Evidence = { id: string; student_id: string; skill_id: string; kind: string; value: number; items: number; source: string };
type Course = { code: string; title: string; credits: number; semester_offered: string; type: string; source_url: string; verification: string };
type Submission = { id: string; student_id: string; kind: string; exercise_id: string | null; status: string; score: number | null; submission: string };
type Goal = { id: string; name: string };
type Tab = "students" | "evidence" | "courses" | "submissions" | "system";

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("students");
  const [notice, setNotice] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [filter, setFilter] = useState("");
  const students = useLoader<Student[]>(() => api("/admin/students"), []);
  const evidence = useLoader<Evidence[]>(() => api(`/admin/evidence${filter ? `?student_id=${encodeURIComponent(filter)}` : ""}`), [filter]);
  const courses = useLoader<Course[]>(() => api("/admin/courses"), []);
  const subs = useLoader<Submission[]>(() => api("/admin/assessments"), []);
  const goals = useLoader<{ goals: Goal[] }>(() => api("/catalog"), []);

  async function save(fn: () => Promise<unknown>, what: string) {
    setNotice(null);
    try {
      const r = (await fn()) as { reprocessed_students?: number; plan?: { version?: number } };
      setNotice({ tone: "good", text: `${what} saved. ${r?.reprocessed_students !== undefined ? `Re-planned ${r.reprocessed_students} students.` : r?.plan?.version ? `Skill estimates recomputed; plan is now v${r.plan.version}.` : "Re-processed."}` });
      students.reload(); evidence.reload(); courses.reload(); subs.reload();
    } catch (e) { setNotice({ tone: "bad", text: e instanceof Error ? e.message : "Save failed." }); }
  }

  return (
    <Page title="Admin and data control" description="Edits here go through validation and immediately recompute skill estimates and re-plan. Adminer (port 8080) is for inspection; direct SQL edits there bypass re-processing until you press 'Re-process everyone'.">
      <div className="mb-4 flex flex-wrap gap-2">
        {(["students", "evidence", "courses", "submissions", "system"] as Tab[]).map((t) => <button key={t} onClick={() => setTab(t)} className={`rounded-lg px-3 py-1.5 text-sm font-semibold capitalize ${tab === t ? "bg-brand text-white" : "border border-line bg-surface"}`}>{t === "evidence" ? "scores / evidence" : t}</button>)}
      </div>
      {notice && <div className="mb-4"><Notice tone={notice.tone}>{notice.text}</Notice></div>}

      {tab === "students" && <Table head={["Student", "Semester", "CGPA", "Weekly h", "Headroom", "Goal", ""]}>
        {students.data?.map((s) => <StudentRow key={s.id} s={s} goals={goals.data?.goals ?? []} onSave={(body) => save(() => patch(`/admin/students/${s.id}`, body), s.id)} />)}
      </Table>}

      {tab === "evidence" && <>
        <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by student ID, e.g. S1024" className="mb-3 w-64 rounded-lg border px-3 py-2 text-sm" />
        <Table head={["Evidence", "Student / skill", "Kind", "Items", "Value", ""]}>
          {evidence.data?.slice(0, 150).map((e) => <EvidenceRow key={e.id} e={e} onSave={(value) => save(() => patch(`/admin/evidence/${e.id}`, { value }), e.id)}
            onDelete={() => save(() => api(`/admin/evidence/${e.id}`, { method: "DELETE" }), `Deletion of ${e.id}`)} />)}
        </Table>
      </>}

      {tab === "courses" && <Table head={["Course", "Title", "Credits", "Offered", "Type", "Source", ""]}>
        {courses.data?.map((c) => <CourseRow key={c.code} c={c} onSave={(body) => save(() => patch(`/admin/courses/${c.code}`, body), c.code)} />)}
      </Table>}

      {tab === "submissions" && <Table head={["Submission", "Student", "Kind", "Status", "Score", ""]}>
        {subs.data?.map((s) => <SubmissionRow key={s.id} s={s} onGrade={(score) => save(() => patch(`/admin/assessments/${s.id}`, { score, feedback: "Graded by mentor in admin" }), s.id)} />)}
      </Table>}

      {tab === "system" && <System onDone={(t) => setNotice({ tone: "good", text: t })} onError={(t) => setNotice({ tone: "bad", text: t })} />}
    </Page>
  );
}

function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return <div className="overflow-x-auto rounded-xl border border-line bg-surface"><table className="w-full min-w-[760px] text-left text-sm">
    <thead className="bg-subtle text-xs text-muted"><tr>{head.map((h) => <th key={h} className="p-2.5">{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>;
}

const input = "rounded border px-2 py-1";

function StudentRow({ s, goals, onSave }: { s: Student; goals: Goal[]; onSave: (body: object) => void }) {
  const [sem, setSem] = useState(s.current_semester);
  const [cgpa, setCgpa] = useState(s.cgpa);
  const [hours, setHours] = useState(s.constraints.weekly_hours ?? 10);
  const [head, setHead] = useState(s.constraints.credit_headroom ?? 6);
  const [goal, setGoal] = useState(s.goal_struct?.goal_id ?? "");
  return <tr className="border-t border-line">
    <td className="p-2.5"><span className="font-mono text-xs">{s.id}</span><p className="max-w-56 truncate text-xs text-muted">{s.programme}{s.backlogs.length ? ` · backlogs: ${s.backlogs.join(", ")}` : ""}</p></td>
    <td className="p-2.5"><input aria-label="Semester" type="number" min={1} max={8} value={sem} onChange={(e) => setSem(Number(e.target.value))} className={`${input} w-14`} /></td>
    <td className="p-2.5"><input aria-label="CGPA" type="number" min={0} max={10} step={0.01} value={cgpa} onChange={(e) => setCgpa(Number(e.target.value))} className={`${input} w-20`} /></td>
    <td className="p-2.5"><input aria-label="Weekly hours" type="number" min={0} max={60} value={hours} onChange={(e) => setHours(Number(e.target.value))} className={`${input} w-16`} /></td>
    <td className="p-2.5"><input aria-label="Credit headroom" type="number" min={0} max={12} value={head} onChange={(e) => setHead(Number(e.target.value))} className={`${input} w-16`} /></td>
    <td className="p-2.5"><select aria-label="Goal" value={goal} onChange={(e) => setGoal(e.target.value)} className={`${input} max-w-44`}>{goals.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></td>
    <td className="p-2.5"><Button onClick={() => onSave({ current_semester: sem, cgpa, goal_id: goal, constraints: { weekly_hours: hours, credit_headroom: head } })}>Save</Button></td>
  </tr>;
}

function EvidenceRow({ e, onSave, onDelete }: { e: Evidence; onSave: (v: number) => void; onDelete: () => void }) {
  const [value, setValue] = useState(e.value);
  return <tr className="border-t border-line">
    <td className="p-2.5 font-mono text-xs">{e.id}<p className="font-sans text-muted">{e.source}</p></td>
    <td className="p-2.5 text-xs">{e.student_id}<br />{e.skill_id}</td>
    <td className="p-2.5"><Badge>{e.kind}</Badge></td><td className="p-2.5">{e.items}</td>
    <td className="p-2.5"><input aria-label="Value" type="number" min={0} max={1} step={0.05} value={value} onChange={(ev) => setValue(Number(ev.target.value))} className={`${input} w-20`} /></td>
    <td className="flex gap-2 p-2.5"><Button onClick={() => onSave(value)}>Save</Button><Button kind="secondary" onClick={onDelete}>Delete</Button></td>
  </tr>;
}

function CourseRow({ c, onSave }: { c: Course; onSave: (body: object) => void }) {
  const [title, setTitle] = useState(c.title);
  const [credits, setCredits] = useState(c.credits);
  const [offered, setOffered] = useState(c.semester_offered);
  return <tr className="border-t border-line">
    <td className="p-2.5 font-mono text-xs">{c.code}<p className="font-sans"><Badge tone={c.verification === "verified" ? "good" : "warn"}>{c.verification}</Badge></p></td>
    <td className="p-2.5"><input aria-label="Title" value={title} onChange={(e) => setTitle(e.target.value)} className={`${input} w-64`} /></td>
    <td className="p-2.5"><input aria-label="Credits" type="number" min={1} max={12} value={credits} onChange={(e) => setCredits(Number(e.target.value))} className={`${input} w-14`} /></td>
    <td className="p-2.5"><select aria-label="Offered" value={offered} onChange={(e) => setOffered(e.target.value)} className={input}>{["Autumn", "Spring", "Autumn|Spring"].map((o) => <option key={o}>{o}</option>)}</select></td>
    <td className="p-2.5 text-xs">{c.type}</td>
    <td className="p-2.5"><a className="text-xs text-brand underline" href={c.source_url} target="_blank" rel="noreferrer">PDF</a></td>
    <td className="p-2.5"><Button onClick={() => onSave({ title, credits, semester_offered: offered })}>Save + re-plan all</Button></td>
  </tr>;
}

function SubmissionRow({ s, onGrade }: { s: Submission; onGrade: (score: number) => void }) {
  const [score, setScore] = useState(s.score ?? 0.7);
  return <tr className="border-t border-line">
    <td className="p-2.5 font-mono text-xs">{s.id}<p className="max-w-64 truncate font-sans text-muted">{s.submission}</p></td>
    <td className="p-2.5 text-xs">{s.student_id}</td><td className="p-2.5 text-xs">{s.kind}{s.exercise_id ? ` · ${s.exercise_id}` : ""}</td>
    <td className="p-2.5"><Badge tone={s.status === "graded" ? "good" : "warn"}>{s.status.replace("_", " ")}</Badge></td>
    <td className="p-2.5">{s.status === "graded" ? pct(s.score) : <input aria-label="Score" type="number" min={0} max={1} step={0.05} value={score} onChange={(e) => setScore(Number(e.target.value))} className={`${input} w-20`} />}</td>
    <td className="p-2.5">{s.status !== "graded" && s.status !== "in_progress" && <Button onClick={() => onGrade(score)}>Grade</Button>}</td>
  </tr>;
}

function System({ onDone, onError }: { onDone: (t: string) => void; onError: (t: string) => void }) {
  const quality = useLoader<{ ok: boolean; report: string[] }>(() => api("/admin/data-quality"), []);
  const usage = useLoader<{ model: string | null; configured: boolean; failures: number; cache_hits: number; by_purpose: { purpose: string; calls: number; prompt_tokens: number; completion_tokens: number; avg_latency_ms: number }[] }>(() => api("/admin/llm-usage"), []);
  const [checks, setChecks] = useState<{ profiles: number; all_passed: number; pass_counts: Record<string, number>; gap_coverage_rate: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<string>) => { setBusy(true); try { onDone(await fn()); } catch (e) { onError(e instanceof Error ? e.message : "Failed"); } finally { setBusy(false); } };
  return <div className="grid gap-5 lg:grid-cols-2">
    <Card title="Data quality report" subtitle="Validation of data/seed: references, cycles, answer keys, coverage and documented source inconsistencies.">
      <ul className="space-y-1 text-xs">{quality.data?.report.map((l, i) => <li key={i} className={l.startsWith("note") ? "text-muted" : ""}>{l}</li>)}</ul>
    </Card>
    <div className="space-y-5">
      <Card title="Evaluation checklist" subtitle="Runs every profile through the buddy and checks each plan.">
        <Button disabled={busy} onClick={() => run(async () => { const r = await api<typeof checks & object>("/admin/plans/check"); setChecks(r); return `${r!.all_passed}/${r!.profiles} profiles pass every check.`; })}>Run checks</Button>
        {checks && <ul className="mt-3 grid grid-cols-2 gap-1 text-xs">{Object.entries(checks.pass_counts).map(([k, v]) => <li key={k}>{k}: {v}/{checks.profiles}</li>)}<li>gap coverage: {pct(checks.gap_coverage_rate)}</li></ul>}
      </Card>
      <Card title="Maintenance">
        <div className="flex flex-wrap gap-2">
          <Button kind="secondary" disabled={busy} onClick={() => run(async () => `Re-planned ${(await post<{ reprocessed_students: number }>("/admin/reprocess")).reprocessed_students} students.`)}>Re-process everyone</Button>
          <Button kind="secondary" disabled={busy} onClick={() => { if (confirm("Reset ALL data to the seed files? This deletes every edit, answer and plan.")) run(async () => { await post("/admin/reset"); return "Database restored to the seed state."; }); }}>Reset to seed</Button>
          <a href="http://localhost:8080" target="_blank" rel="noreferrer" className="rounded-lg border border-line px-4 py-2 text-sm font-semibold">Open Adminer</a>
        </div>
      </Card>
      <Card title="Model usage" subtitle={usage.data?.configured ? `Model: ${usage.data.model}` : "No model configured - all features run on deterministic fallbacks."}>
        <p className="text-xs text-muted">Failures: {usage.data?.failures ?? 0} · cache hits: {usage.data?.cache_hits ?? 0}</p>
        <ul className="mt-2 space-y-1 text-xs">{usage.data?.by_purpose.map((p) => <li key={p.purpose}>{p.purpose}: {p.calls} calls, {p.prompt_tokens}+{p.completion_tokens} tokens, {p.avg_latency_ms} ms avg</li>)}</ul>
      </Card>
    </div>
  </div>;
}
