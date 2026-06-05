export default function App() {
  return (
    <main className="shell">
      <h1>DEWS Safety Simulation</h1>
      <p>Safe-domain energy and environment awareness simulation with alerts and recommendations.</p>
      <section className="grid">
        <div className="card"><span>Energy Status</span><div className="value">Normal</div></div>
        <div className="card"><span>Environment</span><div className="value">Safe</div></div>
        <div className="card"><span>Safety Level</span><div className="value">Green</div></div>
        <div className="card"><span>Simulation</span><div className="value">Active</div></div>
      </section>
      <p><button>Run Simulation</button></p>
    </main>
  );
}
