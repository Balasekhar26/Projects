export default function App() {
  return (
    <main className="shell">
      <h1>PCB Doctor</h1>
      <p>Guided electronics diagnostics for safe manual measurements and fault tracing.</p>
      <section className="grid">
        <div className="card"><span>Board Model</span><div className="value">Loaded</div></div>
        <div className="card"><span>Measurements</span><div className="value">Ready</div></div>
        <div className="card"><span>Fault Rules</span><div className="value">Active</div></div>
        <div className="card"><span>Next Step</span><div className="value">Inspect</div></div>
      </section>
      <p><button>Start Diagnosis</button></p>
    </main>
  );
}
