import { useEffect, useState } from "react";
import {
  fetchKronosStatus,
  runFinanceComparison,
  runFinanceCsvComparison,
  runFinanceCsvForecast,
  runFinanceForecast,
} from "../lib/api";
import type {
  FinanceComparisonResult,
  FinanceForecastResult,
  KronosStatus,
  OhlcvCandle,
} from "../types";

const sampleCandles: OhlcvCandle[] = [
  { timestamp: "2026-06-01T09:15:00", open: 101.25, high: 103.1, low: 100.9, close: 102.8, volume: 15420 },
  { timestamp: "2026-06-01T09:20:00", open: 102.8, high: 104.2, low: 102.1, close: 103.6, volume: 18310 },
  { timestamp: "2026-06-01T09:25:00", open: 103.6, high: 104.0, low: 101.7, close: 102.4, volume: 16680 },
  { timestamp: "2026-06-01T09:30:00", open: 102.4, high: 105.3, low: 102.2, close: 104.9, volume: 21430 },
  { timestamp: "2026-06-01T09:35:00", open: 104.9, high: 106.1, low: 104.4, close: 105.6, volume: 19870 },
  { timestamp: "2026-06-01T09:40:00", open: 105.6, high: 106.0, low: 103.8, close: 104.2, volume: 17640 },
];

const samplePayload = JSON.stringify(
  {
    candles: sampleCandles,
    horizon: 3,
    use_kronos: false,
  },
  null,
  2,
);

type FinanceMode = "candles" | "csv";

export function FinancePlayground() {
  const [mode, setMode] = useState<FinanceMode>("candles");
  const [payloadText, setPayloadText] = useState(samplePayload);
  const [csvPath, setCsvPath] = useState("");
  const [horizon, setHorizon] = useState(3);
  const [status, setStatus] = useState<KronosStatus | null>(null);
  const [singleResult, setSingleResult] = useState<FinanceForecastResult | null>(null);
  const [comparison, setComparison] = useState<FinanceComparisonResult | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);

  useEffect(() => {
    void refreshStatus();
  }, []);

  const refreshStatus = async () => {
    try {
      setStatus(await fetchKronosStatus());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not read Kronos status.");
    }
  };

  const loadSample = () => {
    setMode("candles");
    setPayloadText(samplePayload);
    setHorizon(3);
    setError("");
    setSingleResult(null);
    setComparison(null);
  };

  const runBaselineOnly = async () => {
    setError("");
    setSingleResult(null);
    setComparison(null);
    setRunning(true);
    try {
      if (mode === "csv") {
        const path = requireCsvPath(csvPath);
        setSingleResult(await runFinanceCsvForecast({ path, horizon: validateHorizon(horizon), use_kronos: false }));
        return;
      }

      const payload = parsePayload(payloadText);
      setSingleResult(await runFinanceForecast({ ...payload, use_kronos: false }));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Finance request failed.");
    } finally {
      setRunning(false);
    }
  };

  const runComparison = async () => {
    setError("");
    setSingleResult(null);
    setComparison(null);
    setRunning(true);
    try {
      if (mode === "csv") {
        const path = requireCsvPath(csvPath);
        setComparison(await runFinanceCsvComparison({ path, horizon: validateHorizon(horizon), use_kronos: true }));
        await refreshStatus();
        return;
      }

      const payload = parsePayload(payloadText);
      setComparison(await runFinanceComparison({ ...payload, use_kronos: true }));
      await refreshStatus();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Finance comparison failed.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="panelView">
      <h2>Finance Brain</h2>
      <p>Run the owned local OHLCV baseline and the optional Kronos adapter against the same candles or CSV, then compare the outputs before analysis.</p>

      <div className="financeStatusPanel">
        <header>
          <strong>Kronos readiness</strong>
          <button onClick={refreshStatus}>Refresh</button>
        </header>
        {status ? (
          <div className="statusGrid">
            <article className={status.installed ? "ready" : "missing"}>
              <strong>{status.installed ? "Installed" : "Needs setup"}</strong>
              <span>{status.path}</span>
            </article>
            <article className={status.ready_for_real_kronos ? "ready" : "missing"}>
              <strong>{status.ready_for_real_kronos ? "Ready" : "Fallback likely"}</strong>
              <span>{missingImports(status).join(", ") || "All runtime imports found"}</span>
            </article>
            <article>
              <strong>{status.default_model}</strong>
              <span>{status.first_real_run_note}</span>
            </article>
          </div>
        ) : (
          <p>Kronos status has not been loaded yet.</p>
        )}
      </div>

      <div className="segmentedControl" aria-label="Finance request type">
        <button className={mode === "candles" ? "active" : ""} onClick={() => setMode("candles")}>Candles</button>
        <button className={mode === "csv" ? "active" : ""} onClick={() => setMode("csv")}>CSV Path</button>
      </div>

      {mode === "candles" ? (
        <div className="taskComposer">
          <textarea
            value={payloadText}
            onChange={(event) => setPayloadText(event.target.value)}
            rows={13}
            spellCheck={false}
            aria-label="Finance forecast JSON payload"
          />
        </div>
      ) : (
        <div className="taskComposer">
          <input
            value={csvPath}
            onChange={(event) => setCsvPath(event.target.value)}
            placeholder="C:\\data\\ohlcv.csv"
          />
          <label className="inlineField standaloneField">
            <span>Horizon</span>
            <input
              type="number"
              min={1}
              max={512}
              value={horizon}
              onChange={(event) => setHorizon(Number(event.target.value))}
            />
          </label>
        </div>
      )}

      <div className="taskControls">
        <button onClick={loadSample}>Load Sample</button>
        <button onClick={runBaselineOnly} disabled={running}>{running ? "Running..." : "Run Baseline"}</button>
        <button onClick={runComparison} disabled={running}>{running ? "Running..." : "Compare Baseline vs Kronos"}</button>
      </div>

      {error && <div className="errorPanel">{error}</div>}

      {singleResult && (
        <div className="comparisonGrid">
          <ResultCard title="Local baseline" result={singleResult} />
        </div>
      )}

      {comparison && (
        <>
          <div className="comparisonGrid">
            <ResultCard title="Local baseline" result={comparison.baseline} />
            <ResultCard
              title="Kronos"
              result={comparison.kronos ?? comparison.fallback_after_kronos_error}
              fallback={comparison.kronos ? "" : comparison.kronos_error || "Kronos did not return a real forecast."}
            />
          </div>
          <div className="toolResult">
            <header>
              <strong>Comparison payload</strong>
              <span>{comparison.input_candles} candles, horizon {comparison.horizon}</span>
            </header>
            <p>{comparison.risk_warning}</p>
            {comparison.kronos_error && <div className="errorPanel">Kronos detail: {comparison.kronos_error}</div>}
            <pre>{JSON.stringify(comparison, null, 2)}</pre>
          </div>
        </>
      )}
    </section>
  );
}

function ResultCard(props: { title: string; result: FinanceForecastResult | null; fallback?: string }) {
  const result = props.result;
  if (!result) {
    return (
      <article className="financeResultCard missing">
        <header>
          <strong>{props.title}</strong>
          <span>No result</span>
        </header>
        {props.fallback && <p>{props.fallback}</p>}
      </article>
    );
  }

  return (
    <article className={`financeResultCard ${props.fallback ? "missing" : "ready"}`}>
      <header>
        <strong>{props.title}</strong>
        <span>{result.engine}</span>
      </header>
      <div className="summaryGrid compact">
        <article>
          <strong>{result.summary.trend_signal}</strong>
          <span>trend</span>
        </article>
        <article>
          <strong>{result.summary.predicted_change_percent}%</strong>
          <span>change</span>
        </article>
        <article>
          <strong>{result.summary.confidence}</strong>
          <span>confidence</span>
        </article>
      </div>
      {props.fallback && <div className="errorPanel">Fallback detail: {props.fallback}</div>}
      <p>{result.risk_warning}</p>
      <pre>{JSON.stringify(result.predictions, null, 2)}</pre>
    </article>
  );
}

function missingImports(status: KronosStatus) {
  return Object.entries(status.imports)
    .filter(([, installed]) => !installed)
    .map(([name]) => name);
}

function requireCsvPath(value: string) {
  const path = value.trim();
  if (!path) throw new Error("Enter a CSV path before running the CSV forecast.");
  return path;
}

function validateHorizon(value: number) {
  if (!Number.isInteger(value) || value < 1 || value > 512) {
    throw new Error("Horizon must be an integer between 1 and 512.");
  }
  return value;
}

function parsePayload(text: string) {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (exc) {
    throw new Error(`Payload must be valid JSON. ${exc instanceof Error ? exc.message : ""}`.trim());
  }

  if (!value || typeof value !== "object") throw new Error("Payload must be a JSON object.");
  const payload = value as { candles?: unknown; horizon?: unknown; use_kronos?: unknown };
  if (!Array.isArray(payload.candles) || payload.candles.length < 3) {
    throw new Error("Payload needs at least 3 candles.");
  }
  if (typeof payload.horizon !== "number" || !Number.isInteger(payload.horizon) || payload.horizon < 1 || payload.horizon > 512) {
    throw new Error("horizon must be an integer between 1 and 512.");
  }
  payload.candles.forEach((candle, index) => validateCandle(candle, index));
  return {
    candles: payload.candles as OhlcvCandle[],
    horizon: payload.horizon,
    use_kronos: Boolean(payload.use_kronos),
  };
}

function validateCandle(candle: unknown, index: number) {
  if (!candle || typeof candle !== "object") throw new Error(`Candle ${index} must be an object.`);
  const row = candle as Record<string, unknown>;
  for (const field of ["open", "high", "low", "close"] as const) {
    if (typeof row[field] !== "number" || !Number.isFinite(row[field])) {
      throw new Error(`Candle ${index} ${field} must be a finite number.`);
    }
  }
  if (row.volume !== undefined && (typeof row.volume !== "number" || row.volume < 0)) {
    throw new Error(`Candle ${index} volume must be a non-negative number.`);
  }
  const open = row.open as number;
  const high = row.high as number;
  const low = row.low as number;
  const close = row.close as number;
  if (high < Math.max(open, close) || low > Math.min(open, close)) {
    throw new Error(`Candle ${index} has inconsistent OHLC values.`);
  }
}
