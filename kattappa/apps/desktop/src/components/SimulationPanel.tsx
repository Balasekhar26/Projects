import type { SimulationResult } from "../types";

type SimulationPanelProps = {
  simulationDraft: { seed: string; horizon: string };
  simulationResult: SimulationResult | null;
  onSimulationDraftChange: (draft: { seed: string; horizon: string }) => void;
  onRunSimulation: () => void;
};

export function SimulationPanel({
  simulationDraft,
  simulationResult,
  onSimulationDraftChange,
  onRunSimulation,
}: SimulationPanelProps) {
  return (
    <section className="panelView">
      <h2>Simulation</h2>
      <p>MiroFish stays optional; the built-in lab can still sketch scenario outcomes without external code.</p>
      <div className="taskComposer">
        <textarea
          value={simulationDraft.seed}
          onChange={(event) => onSimulationDraftChange({ ...simulationDraft, seed: event.target.value })}
          placeholder="Describe a project decision, launch, feature, or what-if scenario"
          rows={5}
        />
        <div className="taskControls">
          <select
            value={simulationDraft.horizon}
            onChange={(event) => onSimulationDraftChange({ ...simulationDraft, horizon: event.target.value })}
          >
            <option value="short">Short</option>
            <option value="medium">Medium</option>
            <option value="long">Long</option>
          </select>
          <button onClick={onRunSimulation}>Run</button>
        </div>
      </div>
      {simulationResult && (
        <div className="toolResult">
          <header>
            <strong>{simulationResult.engine}</strong>
            <span>{simulationResult.scenario.horizon}</span>
          </header>
          <p>{simulationResult.warning}</p>
          <div className="scoutList">
            {simulationResult.predictions.map((item) => (
              <article key={item.outcome} className="scoutItem">
                <header>
                  <strong>{item.outcome}</strong>
                  <span>{item.confidence}</span>
                </header>
                <p>{item.signal}</p>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
