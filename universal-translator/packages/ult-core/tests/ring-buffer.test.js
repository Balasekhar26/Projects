const test = require("node:test");
const assert = require("node:assert/strict");

const { PcmRingBuffer, RollingPcmCommitter, RollingWindowSegmenter } = require("../src/audio-capture/ring-buffer");

test("pcm ring buffer returns the latest sliding window across wrap-around writes", () => {
  const ring = new PcmRingBuffer({
    sampleRate: 1000,
    channels: 1,
    capacityMs: 1000,
  });

  ring.write(new Int16Array([1, 2, 3, 4]));
  ring.write(new Int16Array([5, 6, 7, 8, 9, 10]));

  assert.deepEqual(Array.from(ring.readLatest(5)), [6, 7, 8, 9, 10]);
});

test("rolling window segmenter emits overlapping windows on a fixed sample hop", () => {
  const segmenter = new RollingWindowSegmenter({
    sampleRate: 1000,
    channels: 1,
    windowMs: 8,
    hopMs: 3,
    capacityMs: 32,
  });

  const first = segmenter.push(new Int16Array([1, 2, 3, 4, 5, 6, 7, 8]));
  const second = segmenter.push(new Int16Array([9, 10, 11]));

  assert.equal(first.length, 1);
  assert.deepEqual(Array.from(first[0].pcm), [1, 2, 3, 4, 5, 6, 7, 8]);
  assert.equal(second.length, 1);
  assert.deepEqual(Array.from(second[0].pcm), [4, 5, 6, 7, 8, 9, 10, 11]);
  assert.equal(second[0].isPartial, true);
});

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
