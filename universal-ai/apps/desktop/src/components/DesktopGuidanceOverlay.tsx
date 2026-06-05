import type { VisualGuidance } from "../types";

export function DesktopGuidanceOverlay({ guidance }: { guidance: VisualGuidance }) {
  const target = guidance.target;
  if (!target) return null;

  return (
    <div className="desktopGuideOverlay" aria-hidden="true">
      <div
        className="desktopGuideTarget"
        style={{
          left: `${target.x * 100}%`,
          top: `${target.y * 100}%`,
          width: `${target.width * 100}%`,
          height: `${target.height * 100}%`,
        }}
      />
      <div
        className="desktopGuideCursor"
        style={{
          left: `${target.x * 100}%`,
          top: `${target.y * 100}%`,
        }}
      />
      <div className="desktopGuideHint">
        <strong>{guidance.requires_approval ? "Approve one step" : guidance.mode === "teach" ? "Teach mode" : "Guide mode"}</strong>
        <span>{guidance.instruction}</span>
      </div>
    </div>
  );
}
