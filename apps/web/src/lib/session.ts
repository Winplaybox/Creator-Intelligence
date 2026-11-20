"use client";
// Browser session for the Creator Intelligence API: short-lived access token in memory/localStorage,
// refresh token in an httpOnly cookie on the API domain (rotated by /v1/auth/refresh).
export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export type Session = {
  access_token: string;
  user: { id: string; email: string; username?: string | null; display_name: string; email_verified: boolean };
  workspace: { id: string; name: string; slug: string; role: string };
};
const KEY = "ci_session";
export function getSession(): Session | null {
  try { const raw = localStorage.getItem(KEY); return raw ? (JSON.parse(raw) as Session) : null; } catch { return null; }
}
export function setSession(s: Session | null) {
  try { if (s) localStorage.setItem(KEY, JSON.stringify(s)); else localStorage.removeItem(KEY); } catch { /* storage blocked */ }
}
async function refresh(): Promise<Session | null> {
  const r = await fetch(`${API}/v1/auth/refresh`, { method: "POST", credentials: "include" });
  if (!r.ok) { setSession(null); return null; }
  const s = (await r.json()) as Session; setSession(s); return s;
}
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const go = (s: Session | null) => fetch(`${API}${path}`, {
    ...init, credentials: "include",
    headers: { ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(s ? { Authorization: `Bearer ${s.access_token}` } : {}), ...(init.headers || {}) },
  });
  let r = await go(getSession());
  if (r.status === 401) { const s = await refresh(); if (s) r = await go(s); }
  return r;
}
export async function errorText(r: Response): Promise<string> {
  try { const d = await r.json(); const det = d?.detail; return typeof det === "string" ? det : det?.error || (Array.isArray(det) ? det[0]?.msg : "") || `Request failed (${r.status})`; }
  catch { return `Request failed (${r.status})`; }
}
export async function logout() {
  await fetch(`${API}/v1/auth/logout`, { method: "POST", credentials: "include" }).catch(() => undefined);
  setSession(null);
}
