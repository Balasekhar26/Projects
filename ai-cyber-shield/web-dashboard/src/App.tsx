export default function App() {
  return (
    <main className="shell">
      <h1>AI Cyber Shield</h1>
      <p>Defensive security dashboard for local monitoring, reports, and safe response workflows.</p>
      <section className="grid">
        <div className="card"><span>Status</span><div className="value">Protected</div></div>
        <div className="card"><span>Active Threats</span><div className="value">0</div></div>
        <div className="card"><span>Processes</span><div className="value">Monitored</div></div>
        <div className="card"><span>Reports</span><div className="value">Ready</div></div>
      </section>
      <p><button>Run Local Scan</button></p>
    </main>
  );
}
