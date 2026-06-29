import type { ResearchResult } from "../types";

type ResearchPanelProps = {
  researchDraft: { url: string; goal: string };
  researchResult: ResearchResult | null;
  onResearchDraftChange: (draft: { url: string; goal: string }) => void;
  onExtractResearch: () => void;
};

export function ResearchPanel({
  researchDraft,
  researchResult,
  onResearchDraftChange,
  onExtractResearch,
}: ResearchPanelProps) {
  return (
    <section className="panelView">
      <h2>Research</h2>
      <p>ScrapeGraphAI is optional; plain HTML extraction works locally with the existing backend.</p>
      <div className="taskComposer">
        <input
          value={researchDraft.url}
          onChange={(event) => onResearchDraftChange({ ...researchDraft, url: event.target.value })}
          placeholder="https://example.com"
        />
        <textarea
          value={researchDraft.goal}
          onChange={(event) => onResearchDraftChange({ ...researchDraft, goal: event.target.value })}
          rows={3}
        />
        <div className="taskControls">
          <button onClick={onExtractResearch}>Extract</button>
        </div>
      </div>
      {researchResult && (
        <div className="toolResult">
          <header>
            <strong>{String(researchResult.engine ?? "web research")}</strong>
            <span>{String(researchResult.title ?? researchResult.url ?? "result")}</span>
          </header>
          {typeof researchResult.summary_text === "string" && <p>{researchResult.summary_text}</p>}
          <pre>{JSON.stringify(researchResult, null, 2)}</pre>
        </div>
      )}
    </section>
  );
}
