"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useStudentId } from "@/lib/useStudent";

const links = [
  ["Plan", "/plan"],
  ["Diagnostic", "/diagnostic"],
  ["Practice", "/practice"],
  ["Progress", "/progress"],
  ["Ask", "/chat"],
  ["Admin", "/admin"],
];

export default function Header() {
  const pathname = usePathname();
  const [studentId] = useStudentId();
  const [label, setLabel] = useState("");
  useEffect(() => {
    if (!studentId) return;
    api<{ id: string; name: string; programme: string }>(`/students/${studentId}`)
      .then((s) => setLabel(`${s.id} · ${s.programme.replace("B.Tech ", "")}`))
      .catch(() => setLabel(studentId));
  }, [studentId]);
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <Link href="/" className="font-bold tracking-tight text-brand">CLUELESS<span className="ml-2 hidden text-xs font-normal text-muted sm:inline">learning buddy · IIT Bhubaneswar</span></Link>
        <nav aria-label="Main navigation" className="flex flex-wrap items-center gap-1 text-sm">
          {links.map(([name, href]) => (
            <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined}
              className={`rounded-md px-2.5 py-1.5 ${pathname === href ? "bg-brand-soft font-semibold text-brand" : "text-muted hover:text-ink"}`}>{name}</Link>
          ))}
          <Link href="/" className="ml-1 max-w-56 truncate rounded-md border border-line px-2.5 py-1.5 text-xs text-muted hover:border-brand" title="Switch student">
            {studentId ? label || studentId : "Choose student"}
          </Link>
        </nav>
      </div>
    </header>
  );
}
