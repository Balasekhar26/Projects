const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("http");
const { EventEmitter } = require("events");

const { WhisperHttpClient } = require("../../../src/stt/whisper-http-client");

function createIdleChild() {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = () => {
    process.nextTick(() => child.emit("close", null));
  };
  return child;
}

test("WhisperHttpClient becomes ready from /health polling instead of relying on server log wording", async () => {
  const server = http.createServer((req, res) => {
    if (req.url === "/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "ok", model_loaded: true }));
      return;
    }
    res.writeHead(404);
    res.end();
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();

  const child = createIdleChild();
  const client = new WhisperHttpClient({
    pythonPath: "python.exe",
    scriptsDir: ".",
    whisperModelPath: ".",
    whisperHttpPort: port,
    whisperStartupTimeoutMs: 3000,
    whisperHealthPollIntervalMs: 50,
    spawnImpl: () => child,
  });

  const debugLogs = [];
  client.on("debug", (message) => debugLogs.push(message));

  await client._start();

  assert.equal(client.ready, true);
  assert.ok(debugLogs.some((message) => message.includes("Whisper HTTP server ready")));

  client.stop();
  await new Promise((resolve) => server.close(resolve));
});

test("WhisperHttpClient includes captured startup logs in timeout errors", async () => {
  const child = createIdleChild();
  const client = new WhisperHttpClient({
    pythonPath: "python.exe",
    scriptsDir: ".",
    whisperModelPath: ".",
    whisperHttpPort: 6553,
    whisperStartupTimeoutMs: 200,
    whisperHealthPollIntervalMs: 50,
    spawnImpl: () => {
      process.nextTick(() => {
        child.stderr.emit("data", Buffer.from("Loading Whisper model from fake-path\n", "utf8"));
      });
      return child;
    },
  });

  await assert.rejects(
    client._start(),
    (error) => {
      assert.match(error.message, /startup timeout/i);
      assert.match(error.message, /Loading Whisper model from fake-path/);
      return true;
    }
  );
});
