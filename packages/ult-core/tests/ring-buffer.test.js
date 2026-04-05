const test = require("node:test");
const assert = require("node:assert/strict");

const { RollingPcmCommitter } = require("../src/audio-capture/ring-buffer");

test("rolling pcm committer emits a segment when it reaches the max window", () => {
  const committer = new RollingPcmCommitter({
    sampleRate: 1000,
    minCommitMs: 200,
    maxCommitMs: 400,
    overlapMs: 100,
  });

  const segmentA = new Int16Array(200).fill(500);
  const segmentB = new Int16Array(220).fill(500);

  const ready = [...committer.push(segmentA), ...committer.push(segmentB)];

  assert.equal(ready.length, 1);
  assert.equal(ready[0].reason, "window-max");
  assert.ok(ready[0].durationMs >= 400);
});
