"use client";

import Header from "@/components/Header";

export default function Page({ title, description, children, actions }: { title: string; description?: string; children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <>
      <Header />
      <main className="mx-auto max-w-7xl px-4 py-6 sm:py-8">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
            {description && <p className="mt-1 max-w-3xl text-sm text-muted">{description}</p>}
          </div>
          {actions}
        </div>
        <div className="mt-6">{children}</div>
      </main>
    </>
  );
}
