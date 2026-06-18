import { useEffect, useRef, useState } from "react";
import { fetchJarvisMode, saveJarvisMode, speakWithLocalVoice, fetchJarvisDiagnostics } from "../lib/api";

export function JarvisHud() {
  const [jarvisMode, setJarvisMode] = useState(false);
  const [reactorPower, setReactorPower] = useState(100);
  const [isSimulating, setIsSimulating] = useState(false);
  const [logs, setLogs] = useState<string[]>([
    "[SYSTEM] Welcome back, Mr. Stark.",
    "[SYSTEM] Holographic HUD operational.",
    "[SECURITY] Deflection deflectors active via Cyber Shield.",
    "[TELEMETRY] Delta sleep wave synchronization operational via NeuroSeed."
  ]);
  const [telemetry, setTelemetry] = useState<Record<string, string>>({
    neuroseed_brain_sync: "94% DELTA WAVE",
    cyber_shield_deflectors: "0 THREATS / SHIELD OK",
    universal_translation: "192HZ FREQ SYNC",
    pcb_doctor: "CALIBRATED",
    kairo: "ACTIVE",
    prism: "READY",
    tempo: "0.04s DILATION",
    portal: "COORDINATE LOCK",
    mira: "READY",
  });
  
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animationRef = useRef<number | null>(null);

  // Load JARVIS Mode state & periodic diagnostics telemetry
  useEffect(() => {
    let active = true;
    const init = async () => {
      try {
        const res = await fetchJarvisMode();
        if (active) setJarvisMode(res.enabled);
      } catch (err) {
        console.error("Failed to load Jarvis Mode:", err);
      }
    };
    init();

    const loadDiagnostics = async () => {
      try {
        const res = await fetchJarvisDiagnostics();
        if (active && res.ok) {
          setTelemetry(res.telemetry);
        }
      } catch (err) {
        console.error("Failed to load telemetry:", err);
      }
    };
    loadDiagnostics();
    const interval = setInterval(loadDiagnostics, 3000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  // Toggle JARVIS Mode
  const handleToggleJarvis = async (enabled: boolean) => {
    setJarvisMode(enabled);
    try {
      await saveJarvisMode(enabled);
      const greeting = enabled 
        ? "Jarvis mode initialized. At your service, Mr. Stark. How may I assist you today?"
        : "Standard assistant profile restored. Kattappa AI OS is online.";
      await speakWithLocalVoice(greeting);
      addLog(`[SYSTEM] Jarvis Tone: ${enabled ? "ENABLED" : "DISABLED"}`);
    } catch (err) {
      console.error("Failed to save Jarvis Mode:", err);
    }
  };

  const addLog = (msg: string) => {
    setLogs((prev) => [msg, ...prev.slice(0, 18)]);
  };

  // Trigger Arc Reactor Power Pulse
  const handlePulseReactor = async () => {
    setReactorPower(150);
    setTimeout(() => setReactorPower(100), 600);
    addLog(`[ENERGY] Repulsor core power output spikes to 150%!`);
    
    const responses = [
      "Repulsor energy core initialized at maximum output. Welcome back, Mr. Stark.",
      "Arc reactor output stabilized at one hundred percent capacity. Defensive shields fully operational.",
      "Power levels optimal. All auxiliary weapon and defense systems online.",
      "I have run a diagnostic sweep. All modules are green, sir."
    ];
    const speech = responses[Math.floor(Math.random() * responses.length)];
    try {
      await speakWithLocalVoice(speech);
    } catch (err) {
      console.error("Voice trigger failed:", err);
    }
  };

  // Run Atomic Reconstructor Particle Simulation
  const handleInitiateSynthesis = () => {
    if (isSimulating) return;
    setIsSimulating(true);
    addLog("[MIRA] Initiating atomic mapping for element replication...");
    
    setTimeout(() => {
      addLog("[PORTAL] Collapsing local spacetime dimensions (portal locking)...");
    }, 800);
    setTimeout(() => {
      addLog("[TEMPO] Dilation fields activated to synchronize lattice cooling...");
    }, 1600);
    setTimeout(() => {
      addLog("[PRISM] Adaptive cloaking shields maximized to contain radiation...");
    }, 2400);
    setTimeout(() => {
      addLog("[SYSTEM] Recombination complete. Stark Element Synthesized successfully!");
      setIsSimulating(false);
    }, 4000);
  };

  // Canvas Particle Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = (canvas.width = canvas.offsetWidth);
    let height = (canvas.height = canvas.offsetHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = canvas.offsetWidth;
      height = canvas.height = canvas.offsetHeight;
    };
    window.addEventListener("resize", handleResize);

    // Particles array
    const particleCount = 45;
    const particles: { x: number; y: number; vx: number; vy: number; radius: number }[] = [];
    for (let i = 0; i < particleCount; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 1.5,
        vy: (Math.random() - 0.5) * 1.5,
        radius: Math.random() * 2 + 1.5,
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, width, height);

      // Grid backing
      ctx.strokeStyle = "rgba(0, 243, 255, 0.04)";
      ctx.lineWidth = 1;
      const gridSize = 24;
      for (let x = 0; x < width; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Draw particle lattice
      ctx.fillStyle = "rgba(0, 243, 255, 0.8)";
      particles.forEach((p, index) => {
        // Move particles
        if (isSimulating) {
          // Attract to center (synthesis)
          const dx = width / 2 - p.x;
          const dy = height / 2 - p.y;
          p.x += dx * 0.05 + p.vx * 0.2;
          p.y += dy * 0.05 + p.vy * 0.2;
        } else {
          p.x += p.vx;
          p.y += p.vy;
        }

        // Boundary bounce
        if (p.x < 0 || p.x > width) p.vx *= -1;
        if (p.y < 0 || p.y > height) p.vy *= -1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fill();

        // Draw links
        for (let j = index + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const dist = Math.hypot(p.x - p2.x, p.y - p2.y);
          const maxDist = isSimulating ? 110 : 80;
          if (dist < maxDist) {
            ctx.strokeStyle = `rgba(0, 243, 255, ${0.45 * (1 - dist / maxDist)})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
          }
        }
      });

      // Holographic HUD rings
      ctx.strokeStyle = "rgba(0, 243, 255, 0.12)";
      ctx.beginPath();
      ctx.arc(width / 2, height / 2, 70, 0, Math.PI * 2);
      ctx.stroke();

      ctx.strokeStyle = "rgba(0, 243, 255, 0.06)";
      ctx.beginPath();
      ctx.arc(width / 2, height / 2, 110, 0, Math.PI * 2);
      ctx.stroke();

      animationRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener("resize", handleResize);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [isSimulating]);

  return (
    <section className="panelView jarvis-hud-container">
      {/* Scope-isolated high-tech styled stylesheet */}
      <style>{`
        .jarvis-hud-container {
          background: radial-gradient(circle at center, #091c24 0%, #03080c 100%);
          color: #00f0ff;
          font-family: 'Cascadia Code', monospace;
          display: grid;
          grid-template-rows: auto 1fr;
          gap: 20px;
          height: 100%;
        }
        .jarvis-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(0, 240, 255, 0.2);
          padding-bottom: 12px;
        }
        .jarvis-header h2 {
          margin: 0;
          font-size: 20px;
          text-shadow: 0 0 12px rgba(0, 240, 255, 0.6);
        }
        .jarvis-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 20px;
          min-height: 0;
        }
        .jarvis-card {
          border: 1px solid rgba(0, 240, 255, 0.25);
          background: rgba(0, 24, 36, 0.4);
          border-radius: 12px;
          padding: 16px;
          display: flex;
          flex-direction: column;
          box-shadow: inset 0 0 16px rgba(0, 240, 255, 0.05);
          position: relative;
          overflow: hidden;
        }
        .jarvis-card::before {
          content: "";
          position: absolute;
          top: 0; left: 0; right: 0; height: 3px;
          background: linear-gradient(90deg, #00f0ff, transparent);
        }
        .jarvis-card h3 {
          margin: 0 0 12px;
          font-size: 14px;
          text-transform: uppercase;
          letter-spacing: 1.5px;
          color: #e0faff;
          border-bottom: 1px dashed rgba(0, 240, 255, 0.15);
          padding-bottom: 6px;
        }
        /* Arc Reactor Widget styles */
        .reactor-wrapper {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          flex-grow: 1;
          gap: 16px;
        }
        .reactor-svg {
          width: 170px;
          height: 170px;
          cursor: pointer;
          filter: drop-shadow(0 0 16px rgba(0, 240, 255, 0.6));
          transition: transform 0.3s ease;
        }
        .reactor-svg:hover {
          transform: scale(1.06);
        }
        .reactor-ring-outer {
          transform-origin: 50% 50%;
          animation: jarvis-spin-cw 22s linear infinite;
        }
        .reactor-ring-inner {
          transform-origin: 50% 50%;
          animation: jarvis-spin-ccw 14s linear infinite;
        }
        @keyframes jarvis-spin-cw {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes jarvis-spin-ccw {
          from { transform: rotate(0deg); }
          to { transform: rotate(-360deg); }
        }
        /* Telemetry logs */
        .jarvis-log-feed {
          background: rgba(0, 8, 12, 0.85);
          border: 1px solid rgba(0, 240, 255, 0.12);
          border-radius: 6px;
          padding: 8px 12px;
          font-size: 11px;
          flex-grow: 1;
          overflow-y: auto;
          line-height: 1.5;
        }
        .jarvis-log-line {
          margin-bottom: 5px;
          color: rgba(0, 240, 255, 0.8);
          border-left: 2px solid rgba(0, 240, 255, 0.4);
          padding-left: 6px;
        }
        /* Mode toggle switch */
        .jarvis-toggle-switch {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          font-size: 13px;
          color: #9cf5ff;
        }
        .jarvis-toggle-switch input {
          width: 18px;
          height: 18px;
          cursor: pointer;
        }
        .canvas-container {
          flex-grow: 1;
          position: relative;
          min-height: 160px;
        }
        .canvas-container canvas {
          position: absolute;
          top: 0; left: 0; width: 100%; height: 100%;
          border-radius: 6px;
        }
        .jarvis-button {
          border: 1px solid #00f0ff;
          color: #00f0ff;
          border-radius: 6px;
          background: rgba(0, 240, 255, 0.08);
          padding: 8px 12px;
          font-family: inherit;
          cursor: pointer;
          text-transform: uppercase;
          font-size: 12px;
          letter-spacing: 1px;
          transition: all 0.25s ease;
          box-shadow: 0 0 10px rgba(0, 240, 255, 0.15);
        }
        .jarvis-button:hover {
          background: rgba(0, 240, 255, 0.22);
          box-shadow: 0 0 18px rgba(0, 240, 255, 0.45);
        }
        .jarvis-suit-telemetry {
          display: grid;
          gap: 8px;
          font-size: 11px;
        }
        .jarvis-telemetry-row {
          display: flex;
          justify-content: space-between;
          border-bottom: 1px solid rgba(0, 240, 255, 0.08);
          padding-bottom: 4px;
        }
        .jarvis-telemetry-row span:last-child {
          color: #e0faff;
        }
        .jarvis-active-badge {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 12px;
          color: #00f0ff;
          border: 1px solid rgba(0, 240, 255, 0.3);
          background: rgba(0, 240, 255, 0.06);
          padding: 6px 12px;
          border-radius: 20px;
          box-shadow: 0 0 10px rgba(0, 240, 255, 0.15);
          letter-spacing: 0.5px;
          font-weight: bold;
        }
        .pulse-dot {
          width: 8px;
          height: 8px;
          background-color: #00f0ff;
          border-radius: 50%;
          box-shadow: 0 0 0 0 rgba(0, 240, 255, 0.7);
          animation: pulse-ring 1.6s infinite cubic-bezier(0.66, 0, 0, 1);
        }
        @keyframes pulse-ring {
          0% {
            box-shadow: 0 0 0 0 rgba(0, 240, 255, 0.7);
          }
          70% {
            box-shadow: 0 0 0 8px rgba(0, 240, 255, 0);
          }
          100% {
            box-shadow: 0 0 0 0 rgba(0, 240, 255, 0);
          }
        }
      `}</style>

      {/* Header Panel */}
      <header className="jarvis-header">
        <h2>Kattappa JARVIS Core HUD</h2>
        <div className="jarvis-active-badge">
          <span className="pulse-dot"></span>
          <span>JARVIS COGNITIVE CORE: INTEGRATED</span>
        </div>
      </header>

      {/* Main Grid */}
      <div className="jarvis-grid">
        {/* Card 1: Arc Reactor Energy System */}
        <div className="jarvis-card">
          <h3>Stark Arc Reactor Core</h3>
          <div className="reactor-wrapper">
            <svg
              className="reactor-svg"
              viewBox="0 0 100 100"
              onClick={handlePulseReactor}
              style={{ filter: `drop-shadow(0 0 ${reactorPower * 0.15}px rgba(0, 243, 255, 0.7))` }}
            >
              {/* Core Glow */}
              <circle cx="50" cy="50" r="14" fill="#00f3ff" opacity="0.95" />
              <circle cx="50" cy="50" r="18" fill="none" stroke="#00f3ff" strokeWidth="2.5" opacity="0.75" />
              
              {/* Outer spinning triangles */}
              <g className="reactor-ring-outer">
                <circle cx="50" cy="50" r="38" fill="none" stroke="rgba(0, 243, 255, 0.2)" strokeWidth="4" />
                <path d="M 50,6 A 44,44 0 0,1 86,28 L 74,32 A 30,30 0 0,0 50,16 Z" fill="#00f3ff" />
                <path d="M 86,28 A 44,44 0 0,1 78,75 L 68,66 A 30,30 0 0,0 74,32 Z" fill="#00f3ff" opacity="0.8" />
                <path d="M 78,75 A 44,44 0 0,1 30,88 L 33,76 A 30,30 0 0,0 68,66 Z" fill="#00f3ff" />
                <path d="M 30,88 A 44,44 0 0,1 8,50 L 19,50 A 30,30 0 0,0 33,76 Z" fill="#00f3ff" opacity="0.8" />
                <path d="M 8,50 A 44,44 0 0,1 26,14 L 31,26 A 30,30 0 0,0 19,50 Z" fill="#00f3ff" />
                <path d="M 26,14 A 44,44 0 0,1 50,6 L 50,16 A 30,30 0 0,0 31,26 Z" fill="#00f3ff" opacity="0.8" />
              </g>

              {/* Inner spinning telemetry ring */}
              <g className="reactor-ring-inner" opacity="0.6">
                <circle cx="50" cy="50" r="28" fill="none" stroke="#00f3ff" strokeWidth="1" strokeDasharray="6,4,2,4" />
              </g>
            </svg>
            <strong>Core Stabilization: 99.9%</strong>
            <span>Power Output: {reactorPower}%</span>
            <button className="jarvis-button" onClick={handlePulseReactor}>Core Power Pulse</button>
          </div>
        </div>

        {/* Card 2: 12-Project Lab Telemetry */}
        <div className="jarvis-card">
          <h3>Mark XII Suit System Telemetry</h3>
          <div className="jarvis-suit-telemetry">
            <div className="jarvis-telemetry-row">
              <span>[07-NEUROSEED] BRAIN SYNC</span>
              <span>{telemetry.neuroseed_brain_sync}</span>
            </div>
            <div className="jarvis-telemetry-row">
              <span>[CYBER SHIELD] DEFLECTORS</span>
              <span>{telemetry.cyber_shield_deflectors}</span>
            </div>
            <div className="jarvis-telemetry-row">
              <span>[UNIVERSAL TRANSLATION] COGNITIVE AUDIT</span>
              <span>{telemetry.universal_translation}</span>
            </div>
            <div className="jarvis-telemetry-row">
              <span>[PCB DOCTOR] HARDWARE SCANNER</span>
              <span>{telemetry.pcb_doctor}</span>
            </div>
            <div className="jarvis-telemetry-row">
              <span>[KAIRO] TELEKINESIS DEPOLARIZER</span>
              <span>{telemetry.kairo}</span>
            </div>
            <div className="jarvis-telemetry-row">
              <span>[PRISM] CLOAKING MATRIX</span>
              <span>{telemetry.prism}</span>
            </div>
            <div className="jarvis-telemetry-row">
              <span>[TEMPO] TEMPORAL COMPACTION</span>
              <span>{telemetry.tempo}</span>
            </div>
            <div className="jarvis-telemetry-row">
              <span>[PORTAL] DISTANCE DIMENSION STRING</span>
              <span>{telemetry.portal}</span>
            </div>
            <div className="jarvis-telemetry-row">
              <span>[MIRA] ATOMIC LATTICE MAPPER</span>
              <span>{telemetry.mira}</span>
            </div>
          </div>
        </div>

        {/* Card 3: Deep Research Logs */}
        <div className="jarvis-card">
          <h3>Tactical Log Feed</h3>
          <div className="jarvis-log-feed">
            {logs.map((log, index) => (
              <div key={index} className="jarvis-log-line">
                {log}
              </div>
            ))}
          </div>
        </div>

        {/* Card 4: Holographic Reconstructor Simulator */}
        <div className="jarvis-card">
          <h3>MIRA Atomic Lattice Reconstructor</h3>
          <div className="canvas-container">
            <canvas ref={canvasRef} />
          </div>
          <button
            className="jarvis-button"
            onClick={handleInitiateSynthesis}
            disabled={isSimulating}
          >
            {isSimulating ? "Recombination in Progress..." : "Initiate Element Synthesis"}
          </button>
        </div>
      </div>
    </section>
  );
}
