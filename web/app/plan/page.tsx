"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import Page from "@/components/Page";
import { Badge, Button, Card, Loading, Meter, NeedStudent, Notice, SLOT_LABEL, SLOT_TONE } from "@/components/ui";
import { api, Catalog, Dashboard, pct, post, put, Semester } from "@/lib/api";
import { useLoader, useStudentId } from "@/lib/useStudent";

type History = { version: number; trigger: string; created_by: string; created_at: string | null; change_explanation: string; diff: { added?: string[]; removed?: string[] } }[];
type Sim = Record<"strong" | "weak", { quiz_score: number; before: number; p_mastery: number; explanation: string; semesters: Semester[]; violations: string[] }>;
type Journey = { scenario: string; summary: string; timeline: { semester: number; season: string; goal_skills_met: number; goal_skills_total: number; this_semester: { courses: string[]; core: string[]; activities: string[]; review_modules: string[] }; change: string }[] };

export default function PlanPage() {
  const [studentId, ready] = useStudentId();
  const dash = useLoader<Dashboard>(studentId ? () => api<Dashboard>(`/students/${studentId}/dashboard`) : null, [studentId]);
  const catalog = useLoader<Catalog>(() => api<Catalog>("/catalog"), []);
  const history = useLoader<History>(studentId ? () => api<History>(`/students/${studentId}/plans`) : null, [studentId, dash.data?.plan.version]);
  const [message, setMessage] = useState<{ tone: "good" | "warn" | "bad" | "brand"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const courses = useMemo(() => new Map((catalog.data?.courses ?? []).map((c) => [c.code, c])), [catalog.data]);
  const skillName = (id: string | null | undefined) => catalog.data?.skills.find((s) => s.id === id)?.name ?? id ?? "";

  async function act(fn: () => Promise<string>) {
    setBusy(true); setMessage(null);
    try { setMessage({ tone: "good", text: await fn() }); await dash.reload(); }
    catch (e) { setMessage({ tone: "bad", text: e instanceof Error ? e.message : "That did not work." }); }
    finally { setBusy(false); }
  }
  const reject = (code: string) => act(async () => {
    const r = await post<{ tradeoffs: string[]; plan: { version: number } }>(`/students/${studentId}/override`, { exclude_course: code });
    return `${code} won't be recommended again (plan v${r.plan.version}). ${r.tradeoffs.join(" ") || "No goal skill lost coverage."}`;
  });
  const changeGoal = (goalId: string) => act(async () => {
    const r = await put<{ plan: { change_explanation: string } }>(`/students/${studentId}/goal`, { goal_id: goalId });
    return r.plan.change_explanation;
  });

  if (ready && !studentId) return <Page title="Your plan"><NeedStudent /></Page>;
  const d = dash.data;
  return (
    <Page title="Your learning plan" description="Built and checked by deterministic rules from the IIT Bhubaneswar curriculum and regulations; every item says why it is there."
      actions={d && <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge tone="brand">Version {d.plan.version}</Badge><Badge>{d.plan.created_by}</Badge>
        <Button kind="secondary" disabled={busy} onClick={() => act(async () => { await post(`/students/${studentId}/plan`); return "Plan re-checked against the latest evidence."; })}>Re-check</Button>
      </div>}>
      {dash.error && <Notice tone="bad">{dash.error}</Notice>}
      {!d && !dash.error && <Loading label="Building your plan..." />}
      {message && <div className="mb-4"><Notice tone={message.tone}>{message.text}</Notice></div>}
      {d && <div className="space-y-5">
        <div className="grid gap-5 lg:grid-cols-3">
          <Card className="lg:col-span-2" title={d.diagnosis.goal} subtitle={`${d.student.programme} · planning semester ${d.student.current_semester} · CGPA ${d.student.cgpa.toFixed(2)}`}
            action={<Badge tone={d.readiness.ready ? "good" : "warn"}>{d.readiness.ready ? "Goal-ready" : "Not ready yet"}</Badge>}>
            <p className="text-sm">{d.plan.rationale}</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {d.readiness.criteria.map((c) => <div key={c.name} className="flex items-start gap-2 text-sm"><span aria-hidden className={c.met ? "text-good" : "text-muted"}>{c.met ? "✓" : "○"}</span><span>{c.name} <span className="text-muted">({c.detail})</span></span></div>)}
            </div>
          </Card>
          <Card title="Next steps">
            <ol className="space-y-3 text-sm">
              {d.next_actions.map((a, i) => <li key={i}><p className="font-medium">{i + 1}. {a.title}</p>{a.why && <p className="text-xs text-muted">{a.why}</p>}</li>)}
            </ol>
            <div className="mt-4 flex flex-wrap gap-2 text-sm"><Link className="text-brand underline" href="/diagnostic">Diagnostic</Link><Link className="text-brand underline" href="/practice">Practice</Link><Link className="text-brand underline" href="/chat">Ask the buddy</Link></div>
          </Card>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <Card title="What you've shown you know" subtitle="Only tested evidence counts as demonstrated.">
            {d.diagnosis.know.length ? <ul className="space-y-3">{d.diagnosis.know.map((s) => <SkillLine key={s.skill_id} s={s} />)}</ul>
              : <p className="text-sm text-muted">Nothing demonstrated yet. The diagnostic takes about five minutes.</p>}
          </Card>
          <Card title="What to improve for this goal" subtitle="Black tick = this goal's target for the skill.">
            <ul className="space-y-3">{d.diagnosis.gaps.map((s) => <SkillLine key={s.skill_id} s={s} />)}</ul>
            {!d.diagnosis.gaps.length && <p className="text-sm text-good">Every goal skill meets its target.</p>}
          </Card>
        </div>

        {d.diagnosis.mismatches.length > 0 && <Card title="Your goal and your evidence disagree" subtitle="The plan closes the gap; you can also compare how well related goals fit your current evidence.">
          <ul className="list-inside list-disc space-y-1 text-sm">{d.diagnosis.mismatches.map((m, i) => <li key={i}>{m.message}</li>)}</ul>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {d.diagnosis.goal_fit.map((g) => <div key={g.goal_id} className={`rounded-lg border p-3 text-sm ${g.current ? "border-brand" : "border-line"}`}>
              <p className="font-medium">{g.name}</p><p className="text-xs text-muted">Fit {pct(g.fit)} · gaps: {g.gaps.slice(0, 3).join(", ") || "none"}</p>
              {!g.current && <Button kind="ghost" className="mt-1 px-0" disabled={busy} onClick={() => changeGoal(g.goal_id)}>Switch to this goal</Button>}
              {g.current && <Badge tone="brand">current goal</Badge>}
            </div>)}
          </div>
        </Card>}

        {d.plan.summary.notes.length > 0 && <Notice tone="warn"><ul className="list-inside list-disc space-y-1">{d.plan.summary.notes.map((n, i) => <li key={i}>{n}</li>)}</ul></Notice>}

        <Card title="What changed" subtitle={`Version ${d.plan.version} · ${d.plan.trigger.replace("_", " ")}`}>
          <p className="text-sm">{d.plan.change_explanation}</p>
          <details className="mt-3 text-sm"><summary className="cursor-pointer text-brand">Plan history ({history.data?.length ?? 0} versions)</summary>
            <ol className="mt-2 space-y-2">{history.data?.map((h) => <li key={h.version} className="rounded-lg bg-subtle p-2">
              <span className="font-mono text-xs">v{h.version}</span> <Badge>{h.trigger.replace("_", " ")}</Badge> <span className="text-xs text-muted">{h.created_at?.slice(0, 16).replace("T", " ")}</span>
              <p className="mt-1">{h.change_explanation}</p>
            </li>)}</ol>
          </details>
        </Card>

        <section aria-label="Semester plan">
          <h2 className="mb-3 text-lg font-semibold">Semester by semester</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {d.plan.semesters.map((s) => <SemesterCard key={s.semester} s={s} courses={courses} skillName={skillName} onReject={reject} busy={busy} />)}
          </div>
        </section>

        <Card title="Constraint checks">
          {d.plan.constraint_checks.length
            ? <ul className="list-inside list-disc text-sm text-bad">{d.plan.constraint_checks.map((c) => <li key={c}>{c}</li>)}</ul>
            : <p className="text-sm text-good">✓ Prerequisites · offerings (Autumn/Spring) · elective and lateral slots · credit headroom · weekly hours · not-together pairs · eligibility (Reg. 9-10) · backlogs first (Reg. 11.6) · no mastered or completed content</p>}
          <p className="mt-2 text-xs text-muted">{d.plan.summary.eligibility.additional_credits ? "Additional credits allowed: " : "Additional credits not allowed: "}{d.plan.summary.eligibility.reason}</p>
        </Card>

        {studentId && <Simulations studentId={studentId} gaps={d.plan.summary.gaps.map((g) => ({ id: g.skill_id, name: g.name }))} skills={catalog.data?.skills ?? []} />}
      </div>}
    </Page>
  );
}

function SkillLine({ s }: { s: Dashboard["diagnosis"]["skills"][number] }) {
  const tone = s.evidence.startsWith("strong") ? "good" : s.evidence.startsWith("moderate") ? "brand" : s.evidence.startsWith("weak") ? "warn" : "neutral";
  return <li>
    <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
      <span className="font-medium">{s.name}{s.interest && <span className="ml-1 text-xs text-muted">(interest)</span>}</span>
      <span className="flex items-center gap-2"><Badge tone={tone} title={s.sources.join(", ")}>{s.evidence}</Badge><span className="w-10 text-right tabular-nums">{pct(s.p_mastery)}</span></span>
    </div>
    <div className="mt-1.5"><Meter value={s.p_mastery} target={s.target} label={s.name} /></div>
    {s.missed > 1 && <p className="mt-1 text-xs text-bad">Missed {s.missed} tested items{s.missed_topics.length ? `: ${s.missed_topics.join(", ")}` : ""}</p>}
  </li>;
}

function SemesterCard({ s, courses, skillName, onReject, busy }: { s: Semester; courses: Map<string, Catalog["courses"][number]>; skillName: (id: string | null) => string; onReject: (code: string) => void; busy: boolean }) {
  const load = s.load;
  return <section className="flex flex-col rounded-xl border border-line bg-surface p-4">
    <div className="flex items-baseline justify-between"><h3 className="font-semibold">{s.label}</h3><span className="text-xs text-muted">+{load.additional_credits}/{load.headroom} cr · {load.extra_hours}/{load.weekly_limit} h/wk</span></div>
    <div className="mt-2 h-1.5 rounded-full bg-subtle" title="Extra weekly hours used"><div className="h-1.5 rounded-full bg-brand" style={{ width: `${load.weekly_limit ? Math.min(100, (load.extra_hours / load.weekly_limit) * 100) : 0}%` }} /></div>
    {s.core_codes.length > 0 && <details className="mt-3 text-xs text-muted"><summary className="cursor-pointer">Fixed curriculum: {s.core_codes.length} courses</summary><p className="mt-1">{s.core_codes.map((c) => `${c} ${courses.get(c)?.title ?? ""}`).join(" · ")}</p></details>}
    <ul className="mt-3 space-y-2">
      {s.courses.map((c) => <li key={c.code} className="rounded-lg bg-subtle p-3">
        <div className="flex items-start justify-between gap-2">
          <div><span className="font-mono text-sm font-semibold">{c.code}</span> <span className="text-sm">{c.title}</span></div>
          <span className="shrink-0 text-xs text-muted">{c.credits} cr</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-1"><Badge tone={SLOT_TONE[c.slot]}>{SLOT_LABEL[c.slot] ?? c.slot}</Badge>{c.skills.map((k) => <Badge key={k}>{skillName(k)}</Badge>)}</div>
        <details className="mt-2 text-xs"><summary className="cursor-pointer text-brand">Why this course?</summary>
          <p className="mt-1">{c.reason}</p>
          {courses.get(c.code) && <p className="mt-1 text-muted">{courses.get(c.code)?.objectives} <a className="underline" href={courses.get(c.code)?.source_url} target="_blank" rel="noreferrer">Source</a></p>}
        </details>
        {c.slot !== "backlog" && <button disabled={busy} onClick={() => onReject(c.code)} className="mt-2 text-xs text-muted underline disabled:opacity-50">I don&apos;t want this course</button>}
      </li>)}
      {!s.courses.length && <li className="text-xs text-muted">No extra courses this semester.</li>}
    </ul>
    <Section title="Practice (active)" items={s.activities.map((a) => ({ key: a.id, main: a.title, sub: `${a.hours_per_week} h/wk · ${a.reason}` }))} />
    <Section title="Open resources (non-credit)" items={s.resources.map((r) => ({ key: r.id, main: r.title, href: r.url, sub: `${r.provider} · ${r.licence} · ${r.hours_per_week} h/wk · ${r.reason}` }))} />
    <Section title="Review for repeatedly missed topics" tone="bad" items={s.review_modules.map((m) => ({ key: m.id, main: `${m.title} (${m.course_code})`, sub: m.reason }))} />
    <Section title="Milestones" items={s.milestones.map((m) => ({ key: m.title, main: m.title, sub: m.kind.replace("_", " ") }))} />
    {s.skip_modules.length > 0 && <details className="mt-3 text-xs text-muted"><summary className="cursor-pointer">Skipping {s.skip_modules.length} module(s) you already know</summary>
      <ul className="mt-1 list-inside list-disc">{s.skip_modules.map((m) => <li key={m.id}>{m.title} ({m.course_code}) - {m.reason}</li>)}</ul></details>}
  </section>;
}

function Section({ title, items, tone }: { title: string; items: { key: string; main: string; sub?: string; href?: string }[]; tone?: string }) {
  if (!items.length) return null;
  return <div className="mt-3 border-t border-line pt-2">
    <h4 className={`text-xs font-semibold uppercase tracking-wide ${tone === "bad" ? "text-bad" : "text-muted"}`}>{title}</h4>
    <ul className="mt-1 space-y-1.5 text-sm">{items.map((i) => <li key={i.key}>{i.href ? <a href={i.href} target="_blank" rel="noreferrer" className="font-medium text-brand underline">{i.main}</a> : <span className="font-medium">{i.main}</span>}{i.sub && <p className="text-xs text-muted">{i.sub}</p>}</li>)}</ul>
  </div>;
}

function Simulations({ studentId, gaps, skills }: { studentId: string; gaps: { id: string; name: string }[]; skills: { id: string; name: string }[] }) {
  const [skill, setSkill] = useState(gaps[0]?.id ?? skills[0]?.id ?? "");
  const [sim, setSim] = useState<Sim | null>(null);
  const [journey, setJourney] = useState<Record<string, Journey>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run<T>(fn: () => Promise<T>, set: (v: T) => void) {
    setBusy(true); setError("");
    try { set(await fn()); } catch (e) { setError(e instanceof Error ? e.message : "Simulation failed."); } finally { setBusy(false); }
  }
  return <Card title="Simulate adaptation" subtitle="Nothing here is saved. See how the same plan responds to a strong versus a weak mid-semester quiz, or to whole semesters of strong or weak results.">
    <div className="flex flex-wrap items-center gap-2">
      <select aria-label="Skill to simulate" value={skill} onChange={(e) => setSkill(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">
        {(gaps.length ? gaps : skills).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <Button disabled={busy || !skill} onClick={() => run(() => post<Sim>(`/students/${studentId}/simulate`, { skill_id: skill }), setSim)}>Strong vs weak quiz</Button>
      <Button kind="secondary" disabled={busy} onClick={() => run(() => Promise.all(["strong", "weak"].map((s) => post<Journey>(`/students/${studentId}/simulate/journey`, { scenario: s }))), (r) => setJourney({ strong: r[0], weak: r[1] }))}>Simulate remaining semesters</Button>
    </div>
    {error && <div className="mt-3"><Notice tone="bad">{error}</Notice></div>}
    {sim && <div className="mt-4 grid gap-4 md:grid-cols-2">
      {(["strong", "weak"] as const).map((k) => <div key={k} className="rounded-lg border border-line p-4 text-sm">
        <h3 className="font-semibold capitalize">{k} quiz ({pct(sim[k].quiz_score)})</h3>
        <p className="text-muted">Estimate {pct(sim[k].before)} → {pct(sim[k].p_mastery)}</p>
        <p className="mt-2">{sim[k].explanation}</p>
        <p className="mt-2 text-xs text-muted">{sim[k].semesters.map((s) => `S${s.semester}: ${s.course_codes.join(", ") || "-"}${s.review_modules.length ? ` +${s.review_modules.length} review` : ""}`).join(" · ")}</p>
      </div>)}
    </div>}
    {journey.strong && <div className="mt-4 grid gap-4 md:grid-cols-2">
      {(["strong", "weak"] as const).map((k) => journey[k] && <div key={k} className="rounded-lg border border-line p-4 text-sm">
        <h3 className="font-semibold capitalize">{k} semesters</h3><p className="text-muted">{journey[k].summary}</p>
        <ol className="mt-2 space-y-2">{journey[k].timeline.map((t) => <li key={t.semester} className="rounded bg-subtle p-2 text-xs">
          <span className="font-semibold">Semester {t.semester}</span> · goal skills at target {t.goal_skills_met}/{t.goal_skills_total}
          <p>Courses: {t.this_semester.courses.join(", ") || "none"}{t.this_semester.review_modules.length ? ` · review: ${t.this_semester.review_modules.length}` : ""}</p>
          <p className="text-muted">{t.change}</p>
        </li>)}</ol>
      </div>)}
    </div>}
  </Card>;
}
