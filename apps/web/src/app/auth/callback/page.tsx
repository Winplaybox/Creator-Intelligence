"use client";
import { useEffect, useState } from "react";
import { API, setSession, errorText } from "../../../lib/session";

// Landing page for the server-side Google OAuth redirect: redeems the one-time ticket for a session.
export default function GoogleCallback() {
  const [error, setError] = useState("");
  useEffect(() => {
    const ticket = new URLSearchParams(window.location.search).get("ticket");
    if (!ticket) { setError("Sign-in link is missing or expired."); return; }
    fetch(`${API}/v1/auth/google/ticket?ticket=${encodeURIComponent(ticket)}`, { method: "POST", credentials: "include" })
      .then(async r => { if (!r.ok) throw new Error(await errorText(r)); setSession(await r.json()); window.location.replace("/studio"); })
      .catch(e => setError(e instanceof Error ? e.message : "Sign-in failed"));
  }, []);
  return <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
    {error ? <p role="alert">{error} <a href="/login">Try again</a></p> : <p>Signing you in…</p>}
  </main>;
}
