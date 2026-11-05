"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import Header from "@/components/Header";
import { Badge, Card, Loading, Notice } from "@/components/ui";
import { api, saveStudentId } from "@/lib/api";

type Row = { id: string; name: string; programme: string; current_semester: number; cgpa: number; goal_text: string; goal_id: string | null; persona: string };

const LOOP = ["Assess", "Personalise", "Learn", "Practise", "Adapt", "Demonstrate mastery"];

export default function Home() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { api<Row[]>("/students").then(setRows).catch((e: Error) => setError(e.message)); }, []);
  const featured = useMemo(() => (rows ?? []).filter((r) => !r.id.startsWith("SYN-") && !r.id.startsWith("STU-")), [rows]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (rows ?? []).filter((r) => !needle || `${r.id} ${r.programme} ${r.goal_text} ${r.persona}`.toLowerCase().includes(needle)).slice(0, 30);
  }, [rows, query]);
  const open = (id: string) => { saveStudentId(id); router.push("/plan"); };

  return (
    <>
      <Header />
      <main className="mx-auto max-w-7xl px-4 py-8">
        <section className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
          <div>
            <p className="text-sm font-semibold uppercase tracking-widest text-brand">Personalised learning buddy</p>
            <h1 className="mt-3 text-4xl font-bold leading-tight tracking-tight sm:text-5xl">A study plan built from your goal, your evidence and IIT Bhubaneswar&apos;s rules.</h1>
            <p className="mt-4 max-w-2xl text-muted">
              It reads the official CSE curriculum and 2019 B.Tech regulations, checks what you can actually do (not just what you&apos;ve completed),
              and keeps adapting the plan as you practise.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/onboarding" className="rounded-lg bg-brand px-5 py-3 font-semibold text-white hover:bg-brand-strong">Create my profile</Link>
              <a href="#profiles" className="rounded-lg border border-line bg-surface px-5 py-3 font-semibold">Try a sample student</a>
            </div>
          </div>
          <Card title="How it works">
            <ol className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {LOOP.map((step, i) => (
                <li key={step} className="rounded-lg bg-subtle p-3"><span className="font-mono text-xs text-brand">0{i + 1}</span><p className="mt-1 text-sm font-semibold">{step}</p></li>
              ))}
            </ol>
            <p className="mt-4 text-xs text-muted">Every plan is checked against prerequisites, offerings, slots, credit headroom, weekly hours and eligibility before you see it. Profiles here are fabricated samples, not real student records.</p>
          </Card>
        </section>

        <section id="profiles" className="mt-12">
          <h2 className="text-xl font-bold">Sample students</h2>
          <p className="mt-1 text-sm text-muted">The personas from the brief and edge cases first, then a search across all synthetic profiles.</p>
          {error && <div className="mt-4"><Notice tone="bad">{error} - is the API running on port 8000?</Notice></div>}
          {!rows && !error && <div className="mt-4"><Loading /></div>}
          <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {featured.map((r) => <ProfileCard key={r.id} row={r} onOpen={open} />)}
          </div>
          {rows && (
            <div className="mt-8">
              <label className="text-sm font-medium" htmlFor="search">Search all {rows.length} profiles</label>
              <input id="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. Mechanical, GATE, backlog, data science"
                className="mt-2 w-full max-w-lg rounded-lg border px-3 py-2" />
              <div className="mt-3 grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                {filtered.map((r) => <ProfileCard key={r.id} row={r} onOpen={open} compact />)}
              </div>
            </div>
          )}
        </section>
      </main>
    </>
  );
}

function ProfileCard({ row, onOpen, compact = false }: { row: Row; onOpen: (id: string) => void; compact?: boolean }) {
  return (
    <button onClick={() => onOpen(row.id)} className="rounded-xl border border-line bg-surface p-4 text-left transition hover:border-brand">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-brand">{row.id}</span>
        <Badge>{`Sem ${row.current_semester} · CGPA ${row.cgpa.toFixed(2)}`}</Badge>
      </div>
      {!compact && <p className="mt-2 text-sm font-semibold">{row.name.replace(/^(Persona|Edge case): /, "")}</p>}
      <p className="mt-1 text-sm text-muted">{row.programme.replace("B.Tech ", "")}</p>
      <p className="mt-1 line-clamp-2 text-xs text-muted">{row.goal_text}</p>
    </button>
  );
}
