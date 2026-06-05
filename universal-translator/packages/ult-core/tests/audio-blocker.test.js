const test = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("events");

const { AudioBlocker } = require("../src/audio-blocking/blocker");

function createFakeChild({ stdout = "", stderr = "", code = 0, error = null }) {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  process.nextTick(() => {
    if (stdout) {
      child.stdout.emit("data", Buffer.from(stdout, "utf8"));
    }
    if (stderr) {
      child.stderr.emit("data", Buffer.from(stderr, "utf8"));
    }
    if (error) {
      child.emit("error", error);
      return;
    }
    child.emit("close", code);
  });
  return child;
}

test("AudioBlocker trusts script-confirmed interception even if Windows status still lags behind", async () => {
  const calls = [];
  const blocker = new AudioBlocker({
    spawnImpl: (_command, args) => {
      const action = args[args.length - 1];
      calls.push(action);
      if (action === "status") {
        return createFakeChild({ stdout: "Default playback: Speakers (Realtek)" });
      }
      if (action === "intercept") {
        return createFakeChild({ stdout: "Intercept ON. Original audio blocked." });
      }
      return createFakeChild({ stdout: "Default playback: Speakers (Realtek)" });
    },
  });
  blocker.on("error", () => {});

  const blocked = await blocker.blockAudio();
  const scriptConfirmedState = blocker.isBlocking;
  const status = await blocker.getStatus();

  assert.equal(blocked, true);
  assert.equal(scriptConfirmedState, true);
  assert.equal(status?.intercepted, false);
  assert.deepEqual(calls, ["status", "intercept", "status", "status"]);
});

test("AudioBlocker fails closed when the route script writes to stderr", async () => {
  const blocker = new AudioBlocker({
    spawnImpl: (_command, args) => {
      const action = args[args.length - 1];
      if (action === "status") {
        return createFakeChild({ stdout: "Default playback: Speakers (Realtek)" });
      }
      return createFakeChild({ stdout: "Intercept ON", stderr: "An unexpected error occurred", code: 0 });
    },
  });
  blocker.on("error", () => {});

  const blocked = await blocker.blockAudio();
  assert.equal(blocked, false);
  assert.equal(blocker.isBlocking, false);
});

test("AudioBlocker getStatus derives interception state from the current default playback device", async () => {
  const blocker = new AudioBlocker({
    spawnImpl: () => createFakeChild({ stdout: "Default playback: CABLE Input (VB-Audio Virtual Cable)" }),
  });

  const status = await blocker.getStatus();

  assert.deepEqual(status, {
    intercepted: true,
    defaultPlayback: "Default playback: CABLE Input (VB-Audio Virtual Cable)",
  });
  assert.equal(blocker.isBlocking, true);
});
