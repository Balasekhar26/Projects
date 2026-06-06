const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const { spawn } = require("child_process");

const { resolveCoreConfig } = require("../src/config");

test("edge_tts_worker resamples decoded PCM to the requested runtime sample rate before writing wav output", async (t) => {
  const config = resolveCoreConfig();
  const dependencyCheck = await runPython(config.pythonPath, [
    "import importlib.util, sys",
    "missing = [name for name in ('numpy', 'scipy', 'soundfile') if importlib.util.find_spec(name) is None]",
    "print(','.join(missing))",
    "sys.exit(1 if missing else 0)",
  ].join("; "));
  if (dependencyCheck.code !== 0) {
    t.skip(`Python audio test dependencies missing: ${dependencyCheck.stdout || dependencyCheck.stderr || "unknown"}`);
    return;
  }

  const workerPath = config.edgeTtsWorkerPath;
  if (!fs.existsSync(workerPath)) {
    t.skip(`Optional Edge TTS worker missing: ${workerPath}`);
    return;
  }
  const pythonScript = [
    "import importlib.util, json, math, os, soundfile as sf, tempfile, numpy as np",
    `worker_path = r'''${workerPath}'''`,
    "spec = importlib.util.spec_from_file_location('edge_tts_worker', worker_path)",
    "mod = importlib.util.module_from_spec(spec)",
    "spec.loader.exec_module(mod)",
    "source_rate = 24000",
    "target_rate = 16000",
    "duration_seconds = 0.25",
    "t = np.arange(int(source_rate * duration_seconds), dtype=np.float32) / source_rate",
    "pcm = np.sin(2 * math.pi * 440 * t).astype(np.float32)",
    "resampled, output_rate = mod.resample_pcm_to_target(pcm, source_rate, target_rate)",
    "final_pcm = mod.finalize_pcm(resampled, output_rate, fade_in_ms=15, fade_out_ms=30, tail_ms=800)",
    "fd, wav_path = tempfile.mkstemp(suffix='.wav')",
    "os.close(fd)",
    "sf.write(wav_path, final_pcm, output_rate, subtype='PCM_16')",
    "info = sf.info(wav_path)",
    "expected_frames = int(round(duration_seconds * target_rate)) + int(round(0.8 * target_rate))",
    "print(json.dumps({'samplerate': info.samplerate, 'frames': info.frames, 'expected_frames': expected_frames}))",
    "os.remove(wav_path)",
  ].join("; ");

  const processResult = await runPython(config.pythonPath, pythonScript);
  if (processResult.code !== 0) {
    throw new Error(processResult.stderr.trim() || `python exited with code ${processResult.code}`);
  }
  const result = JSON.parse(processResult.stdout.trim());

  assert.equal(result.samplerate, 16000);
  assert.ok(Math.abs(result.frames - result.expected_frames) <= 2);
});

function runPython(pythonPath, pythonScript) {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonPath, ["-c", pythonScript], { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      resolve({ code, stdout: stdout.trim(), stderr: stderr.trim() });
    });
  });
}
