import type { OperatorMode } from "../types";

const operatorModes: OperatorMode[] = ["observe", "guide", "teach", "assist", "autonomous"];

type OperatorModeSelectorProps = {
  operatorMode: OperatorMode;
  onChange: (mode: OperatorMode) => void;
  compact?: boolean;
};

export function OperatorModeSelector({ operatorMode, onChange, compact = false }: OperatorModeSelectorProps) {
  return (
    <div className={compact ? "modeSelector compact" : "modeSelector"} aria-label="Operator mode">
      {operatorModes.map((mode) => (
        <button
          key={mode}
          className={operatorMode === mode ? "active" : ""}
          onClick={() => onChange(mode)}
          title={`${mode} mode`}
        >
          {mode}
        </button>
      ))}
    </div>
  );
}
