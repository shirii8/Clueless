"use client";

import { useCallback, useEffect, useState } from "react";
import { currentStudentId } from "@/lib/api";

export function useStudentId(): [string | null, boolean] {
  const [id, setId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const sync = () => setId(currentStudentId());
    sync();
    setReady(true);
    window.addEventListener("clueless:student", sync);
    return () => window.removeEventListener("clueless:student", sync);
  }, []);
  return [id, ready];
}

export function useLoader<T>(loader: (() => Promise<T>) | null, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const reload = useCallback(async () => {
    if (!loader) return;
    setLoading(true);
    setError("");
    try {
      setData(await loader());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, setData, error, setError, loading, reload };
}
