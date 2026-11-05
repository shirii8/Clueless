export const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const post = <T,>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const patch = <T,>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function currentStudentId(): string | null {
  return storage()?.getItem("clueless.studentId") ?? null;
}

export function saveStudentId(id: string): void {
  storage()?.setItem("clueless.studentId", id);
  window.dispatchEvent(new Event("clueless:student"));
}

export function chatSessionId(): string {
  const store = storage();
  const key = "clueless.chatSession";
  const today = new Date().toISOString().slice(0, 10);
  const existing = store?.getItem(key);
  if (existing && existing.startsWith(today)) return existing;
  const fresh = `${today}-${Math.random().toString(36).slice(2, 8)}`;
  store?.setItem(key, fresh);
  return fresh;
}

export const pct = (value: number | null | undefined) => (value == null ? "-" : `${Math.round(value * 100)}%`);

// ------------------------------------------------------------------ types
export type Skill = { id: string; name: string; category: string; description: string };
export type Course = {
  code: string; title: string; dept: string; credits: number; ltp: string; semester_offered: string; type: string;
  curriculum_semester: number | null; syllabus: string; objectives: string; prerequisite_text: string; source_url: string;
  verification: string; verification_note: string; skills: Record<string, number>; prerequisites: string[][];
};
export type Goal = { id: string; name: string; target_skills: Record<string, number> };
export type Exercise = { id: string; skill_id: string; kind: string; title: string; description: string; est_hours: number; rubric: string[] };
export type Catalog = { skills: Skill[]; courses: Course[]; goals: Goal[]; exercises: Exercise[]; rules: { id: string; kind: string; note: string; source_url: string; verification: string }[] };

export type PlanCourse = { code: string; title: string; credits: number; slot: string; skills: string[]; reason: string };
export type PlanItem = { id: string; title: string; kind?: string; skill_id: string | null; hours_per_week: number; reason: string; url?: string; provider?: string; licence?: string; format?: string };
export type Semester = {
  semester: number; season: string; label: string; core_codes: string[]; courses: PlanCourse[]; course_codes: string[];
  activities: PlanItem[]; resources: PlanItem[]; review_modules: { id: string; title: string; skill_id: string; reason: string; course_code: string }[];
  skip_modules: { id: string; title: string; course_code: string; reason: string }[]; milestones: { title: string; kind: string }[];
  load: { additional_credits: number; headroom: number; extra_hours: number; weekly_limit: number; elective_slots_used: number; elective_slots: number; lateral_slots_used: number; lateral_slots: number };
};
export type Gap = { skill_id: string; name: string; level: number; p_mastery: number; target: number; tested: boolean };
export type Plan = {
  student_id: string; version: number; semesters: Semester[]; rationale: string; change_explanation: string; trigger: string;
  created_by: string; created_at: string | null; diff: Record<string, unknown>;
  summary: { gaps: Gap[]; coverage: Record<string, { code: string; semester: number; via: string }[]>; notes: string[]; eligibility: { additional_credits: boolean; reason: string }; met_skills: string[] };
  constraint_checks: string[]; readiness: Readiness;
};
export type Readiness = { goal: string; ready: boolean; summary: string; criteria: { name: string; met: boolean; detail: string }[] };
export type SkillRow = { skill_id: string; name: string; p_mastery: number; mastered: boolean; goal_level: number | null; target: number | null; status: string; evidence: string; sources: string[]; interest: boolean; missed: number; missed_topics: string[] };
export type Diagnosis = {
  goal: string; goal_id: string | null; current_semester: number; pace: { factor: number; label: string };
  know: SkillRow[]; gaps: SkillRow[]; skills: SkillRow[]; mismatches: { skill_id: string; kind: string; message: string }[];
  eligibility: { additional_credits: boolean; reason: string; cgpa_to_unlock: number | null; minor: { possible: boolean; rule: string } };
  goal_fit: { goal_id: string; name: string; fit: number; gaps: string[]; current: boolean }[];
  constraints: Record<string, unknown>;
};
export type Student = { id: string; name: string; programme: string; year: number; current_semester: number; cgpa: number; goal_text: string; goal_struct: { goal_id?: string }; constraints: Record<string, unknown>; preferences: Record<string, unknown>; completed_courses: { code: string; grade?: string }[]; backlogs: string[]; interests: string[]; persona: string };
export type Dashboard = { student: Student; plan: Plan; diagnosis: Diagnosis; readiness: Readiness; next_actions: { kind: string; title: string; why: string }[] };
export type Question = { id: string; skill_id: string; difficulty: number; topic: string; stem: string; options: string[] | null };
