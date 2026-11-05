"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Page from "@/components/Page";
import { Badge, Button, Card, NeedStudent, Notice } from "@/components/ui";
import { api, chatSessionId, post } from "@/lib/api";
import { useStudentId } from "@/lib/useStudent";

type Msg = { id: string; role: string; text: string; intent?: string; session_id?: string; created_at?: string | null };
const PROMPTS = ["What should I do next?", "Am I ready for my goal?", "What do I know and what should I improve?", "What changed in my plan?",
  "What if I score low in linear algebra?", "Am I eligible for additional credits or a minor?"];

export default function ChatPage() {
  const [studentId, ready] = useStudentId();
  const [session, setSession] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [earlier, setEarlier] = useState<Msg[]>([]);
  const [welcome, setWelcome] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!studentId) return;
    const id = chatSessionId();
    setSession(id);
    api<Msg[]>(`/students/${studentId}/chat/history?session_id=${id}`).then(setMessages).catch(() => setMessages([]));
    api<Msg[]>(`/students/${studentId}/chat/history`).then((all) => setEarlier(all.filter((m) => m.session_id !== id).slice(-6))).catch(() => undefined);
    api<{ text: string }>(`/students/${studentId}/chat/welcome?session_id=${id}`).then((w) => setWelcome(w.text)).catch(() => undefined);
  }, [studentId]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function send(message: string) {
    if (!message.trim() || !studentId) return;
    setBusy(true); setError(""); setText("");
    setMessages((m) => [...m, { id: `local-${Date.now()}`, role: "user", text: message }]);
    try {
      const r = await post<{ answer: string; intent: string; source: string }>(`/students/${studentId}/chat`, { message, session_id: session });
      setMessages((m) => [...m, { id: `a-${Date.now()}`, role: "assistant", text: r.answer, intent: `${r.intent} · ${r.source}` }]);
    } catch (e) { setError(e instanceof Error ? e.message : "The buddy is unavailable; your plan is unchanged."); }
    finally { setBusy(false); }
  }

  if (ready && !studentId) return <Page title="Ask the buddy"><NeedStudent /></Page>;
  return (
    <Page title="Ask your learning buddy" description="It remembers your goal, constraints, plan versions and past conversations. Side questions are welcome; it always brings you back to the plan.">
      <div className="grid gap-5 lg:grid-cols-[1.4fr_0.6fr]">
        <Card>
          <div className="flex h-[60vh] flex-col">
            <div className="flex-1 space-y-3 overflow-y-auto pr-1" aria-live="polite">
              {welcome && <Bubble role="assistant" text={welcome} intent="welcome" />}
              {messages.map((m) => <Bubble key={m.id} role={m.role} text={m.text} intent={m.intent} />)}
              {busy && <p className="animate-pulse text-sm text-muted">Thinking...</p>}
              <div ref={bottom} />
            </div>
            {error && <div className="mt-2"><Notice tone="bad">{error}</Notice></div>}
            <form onSubmit={(e: FormEvent) => { e.preventDefault(); send(text); }} className="mt-3 flex gap-2">
              <label htmlFor="msg" className="sr-only">Message</label>
              <input id="msg" value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Why is CS2L004 in my plan?" className="min-w-0 flex-1 rounded-lg border px-3 py-2" />
              <Button type="submit" disabled={busy || !text.trim()}>Send</Button>
            </form>
          </div>
        </Card>
        <div className="space-y-5">
          <Card title="Try asking">
            <div className="flex flex-wrap gap-2">{PROMPTS.map((p) => <button key={p} onClick={() => send(p)} disabled={busy} className="rounded-full border border-line px-3 py-1 text-left text-xs hover:border-brand">{p}</button>)}</div>
            <p className="mt-3 text-xs text-muted">You can also say &quot;I don&apos;t want CS6L034&quot;, &quot;change my goal to GATE&quot;, or ask a concept question.</p>
          </Card>
          {earlier.length > 0 && <Card title="From earlier sessions">
            <ul className="space-y-2 text-xs text-muted">{earlier.map((m) => <li key={m.id}><span className="font-semibold">{m.role === "user" ? "You" : "Buddy"}:</span> {m.text.slice(0, 160)}{m.text.length > 160 ? "..." : ""}</li>)}</ul>
          </Card>}
        </div>
      </div>
    </Page>
  );
}

function Bubble({ role, text, intent }: { role: string; text: string; intent?: string }) {
  const mine = role === "user";
  return <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
    <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${mine ? "bg-brand text-white" : "bg-subtle"}`}>
      {text}
      {!mine && intent && <div className="mt-1"><Badge>{intent}</Badge></div>}
    </div>
  </div>;
}
