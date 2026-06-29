import type { WritingResult } from "../types";

type WritingPanelProps = {
  writingDraft: { text: string; tone: string };
  writingResult: WritingResult | null;
  onWritingDraftChange: (draft: { text: string; tone: string }) => void;
  onCheckWriting: () => void;
  onRewriteWriting: () => void;
};

export function WritingPanel({
  writingDraft,
  writingResult,
  onWritingDraftChange,
  onCheckWriting,
  onRewriteWriting,
}: WritingPanelProps) {
  return (
    <section className="panelView">
      <h2>Writing</h2>
      <p>Harper is used when available; the built-in local checker stays ready as the fallback.</p>
      <div className="taskComposer">
        <textarea
          value={writingDraft.text}
          onChange={(event) => onWritingDraftChange({ ...writingDraft, text: event.target.value })}
          placeholder="Paste email, resume text, notes, or documentation"
          rows={7}
        />
        <div className="taskControls">
          <select
            value={writingDraft.tone}
            onChange={(event) => onWritingDraftChange({ ...writingDraft, tone: event.target.value })}
          >
            <option value="clear">Clear</option>
            <option value="professional">Professional</option>
            <option value="friendly">Friendly</option>
            <option value="concise">Concise</option>
          </select>
          <button onClick={onCheckWriting}>Check</button>
          <button onClick={onRewriteWriting}>Rewrite</button>
        </div>
      </div>
      {writingResult && (
        <div className="toolResult">
          <header>
            <strong>{writingResult.engine}</strong>
            <span>{writingResult.issue_count ?? writingResult.grammar?.issue_count ?? 0} issues</span>
          </header>
          {writingResult.corrected_text && <p>{writingResult.corrected_text}</p>}
          {writingResult.rewritten_text && <p>{writingResult.rewritten_text}</p>}
          {writingResult.note && <small>{writingResult.note}</small>}
        </div>
      )}
    </section>
  );
}
