import type { VisualGuidance } from "../types";

export function DesktopGuidanceOverlay({
  guidance,
  autoHideMs,
}: {
  guidance: VisualGuidance;
  autoHideMs: number;
}) {
  const target = guidance.target;
  if (!target) return null;

  return (
    <div
      className="desktopGuideOverlay"
      aria-hidden="true"
      data-auto-hide-ms={autoHideMs}
      style={{ animationDuration: `${autoHideMs}ms` }}
    >
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
        <strong>{guidance.requires_approval ? "Approve one step" : "Next safe step"}</strong>
        <span>{guidance.instruction}</span>
      </div>
    </div>
  );
}
