"use client";
import { useEffect, useRef, useState } from "react";
import { API, setSession, errorText } from "../../lib/session";
import "../studio/studio.css";

declare global { interface Window { google?: any } }
const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

export default function Login() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [identifier, setIdentifier] = useState(""), [password, setPassword] = useState("");
  const [name, setName] = useState(""), [workspace, setWorkspace] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const gBtn = useRef<HTMLDivElement>(null);

  function done(data: any) { setSession(data); window.location.href = "/studio"; }

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client"; s.async = true;
    s.onload = () => {
      window.google?.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async (resp: { credential: string }) => {
          setBusy(true); setError("");
          const r = await fetch(`${API}/v1/auth/google`, { method: "POST", credentials: "include",
            headers: { "Content-Type": "application/json" }, body: JSON.stringify({ credential: resp.credential }) });
          setBusy(false);
          if (r.ok) done(await r.json()); else setError(await errorText(r));
        },
      });
      if (gBtn.current) window.google?.accounts.id.renderButton(gBtn.current, { theme: "filled_black", size: "large", width: 320 });
    };
    document.head.appendChild(s);
    return () => { s.remove(); };
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    const body = mode === "signin"
      ? { identifier: identifier.trim(), password }
      : { email: identifier.trim(), password, display_name: name.trim() || identifier.split("@")[0], workspace_name: workspace.trim() || "My channel" };
    try {
      const r = await fetch(`${API}/v1/auth/${mode === "signin" ? "login" : "register"}`, { method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (r.ok) done(await r.json()); else setError(await errorText(r));
    } catch { setError("Could not reach the server. Please try again."); }
    finally { setBusy(false); }
  }

  return <main className="ci-auth">
    <form onSubmit={submit} className="ci-auth-card">
      <b className="ci-brand">Creator Intelligence <em>STUDIO</em></b>
      <h1>{mode === "signin" ? "Welcome back" : "Create your account"}</h1>
      {GOOGLE_CLIENT_ID && <><div ref={gBtn} className="ci-google" /><p className="ci-or">or</p></>}
      {mode === "signup" && <input placeholder="Your name" value={name} onChange={e => setName(e.target.value)} autoComplete="name" />}
      <input placeholder={mode === "signin" ? "Email or username" : "Email"} type={mode === "signin" ? "text" : "email"}
        value={identifier} onChange={e => setIdentifier(e.target.value)} autoComplete={mode === "signin" ? "username" : "email"} autoCapitalize="none" required />
      <input placeholder={mode === "signin" ? "Password" : "Password (10+ characters)"} type="password" value={password}
        onChange={e => setPassword(e.target.value)} autoComplete={mode === "signin" ? "current-password" : "new-password"}
        minLength={mode === "signup" ? 10 : 1} required />
      {mode === "signup" && <input placeholder="Channel / workspace name" value={workspace} onChange={e => setWorkspace(e.target.value)} />}
      {error && <p className="ci-error" role="alert">{error}</p>}
      <button disabled={busy}>{busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}</button>
      <button type="button" className="ci-link" onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(""); }}>
        {mode === "signin" ? "New here? Create an account" : "Already have an account? Sign in"}
      </button>
      {mode === "signup" && <small>A unique username is created for you; you can sign in with it or your email.</small>}
    </form>
  </main>;
}
