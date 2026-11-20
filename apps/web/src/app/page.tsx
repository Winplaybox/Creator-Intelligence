const cards = [
  { title: "Channel analytics", description: "Understand performance, audience, and momentum.", status: "Foundation ready" },
  { title: "YouTube SEO", description: "Improve discovery with research-backed optimization.", status: "Planned" },
  { title: "Content planner", description: "Organize ideas and publishing workflow.", status: "Planned" },
  { title: "AI studio", description: "Create briefs, hooks, and scripts with AI assistance.", status: "Planned" }
];

export default function HomePage() {
  return <main style={{ maxWidth: 1180, margin: "0 auto", padding: "48px 24px" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 24, marginBottom: 64 }}>
      <div style={{ fontWeight: 750, letterSpacing: "-.04em", fontSize: 20 }}>Creator Intelligence <span style={{ color: "#a5b4fc" }}>Studio</span></div>
      <span style={{ color: "#aab2c2", fontSize: 14 }}>Platform foundation</span>
    </header>
    <section style={{ maxWidth: 760 }}>
      <p style={{ color: "#a5b4fc", fontWeight: 650, letterSpacing: ".12em", textTransform: "uppercase", fontSize: 12 }}>Creator workspace</p>
      <h1 style={{ fontSize: "clamp(40px, 7vw, 72px)", letterSpacing: "-.06em", lineHeight: 1.02, margin: "16px 0" }}>Make smarter moves.<br/>Grow with clarity.</h1>
      <p style={{ color: "#aab2c2", fontSize: 18, lineHeight: 1.7 }}>Your foundation for YouTube analytics, content intelligence, discovery, and AI-assisted workflows.</p>
    </section>
    <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16, marginTop: 48 }}>
      {cards.map(card => <article key={card.title} style={{ border: "1px solid #252b38", background: "#121620", borderRadius: 18, padding: 24 }}>
        <div style={{ color: "#a5b4fc", fontSize: 12, fontWeight: 650 }}>{card.status}</div>
        <h2 style={{ fontSize: 20, margin: "16px 0 8px" }}>{card.title}</h2>
        <p style={{ color: "#aab2c2", lineHeight: 1.6, margin: 0 }}>{card.description}</p>
      </article>)}
    </section>
    <footer style={{ marginTop: 72, color: "#737d90", fontSize: 13 }}>Early platform build · Features will become available as implementation progresses.</footer>
  </main>;
}
