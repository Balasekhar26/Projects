/**
 * ClockSource abstraction layer
 *
 * STRICT MODE ENFORCEMENT:
 * - Live mode: Real wall-clock and high-res timers (observes nondeterminism)
 * - Deterministic mode: Pre-recorded timestamps (proves logic stability)
 *
 * NO MIXING ALLOWED. Mode must be explicitly specified.
 */

/**
 * Abstract clock interface
 * @typedef {Object} ClockSource
 * @property {() => number} getHighResTimeMs - Get monotonic elapsed time in milliseconds
 * @property {() => number} getNow - Get wall-clock time in milliseconds
 * @property {(previous: number) => number} enforceMonotonic - Ensure time doesn't go backward
 */

/**
 * Clock modes - explicit selection required
 * @typedef {"live" | "deterministic"} ClockMode
 */

/**
 * Live clock: Uses real system timers
 *
 * High-resolution: process.hrtime.bigint() for microsecond precision
 * Wall-clock: Date.now() for absolute timing
 */
class LiveClockSource {
  constructor() {
    this.startedAt = process.hrtime.bigint();
    this.lastMonotonicTime = 0;
  }

  /**
   * Get elapsed time since clock creation
   * @returns {number} Milliseconds elapsed
   */
  getHighResTimeMs() {
    const elapsedNs = process.hrtime.bigint() - this.startedAt;
    return Number(elapsedNs) / 1e6;
  }

  /**
   * Get current wall-clock time
   * @returns {number} Milliseconds since epoch
   */
  getNow() {
    return Date.now();
  }

  /**
   * Enforce monotonic time: never go backward
   * If new time < last time, return last + epsilon
   * @param {number} newTime - Proposed new time
   * @returns {number} Monotonically increasing time
   */
  enforceMonotonic(newTime) {
    const monotonic =
      newTime > this.lastMonotonicTime
        ? newTime
        : this.lastMonotonicTime + 0.001;
    this.lastMonotonicTime = monotonic;
    return monotonic;
  }
}

/**
 * Deterministic clock: Uses pre-recorded timestamps
 *
 * For replay/testing: timestamps are provided upfront
 * Enforces deterministic ordering even if inputs vary
 */
class DeterministicClockSource {
  constructor(config = {}) {
    this.timestamps = config.timestamps || [];
    this.highResTimestamps = config.highResTimestamps || [];
    this.timestampIndex = 0;
    this.highResIndex = 0;
    this.lastMonotonicTime = 0;
  }

  /**
   * Get next high-resolution timestamp
   * @returns {number} Next prerecorded milliseconds
   * @throws {Error} If no more timestamps available
   */
  getHighResTimeMs() {
    if (this.highResIndex >= this.highResTimestamps.length) {
      throw new Error(
        `DeterministicClockSource: Exhausted ${this.highResTimestamps.length} high-res timestamps at index ${this.highResIndex}`
      );
    }
    return this.highResTimestamps[this.highResIndex++];
  }

  /**
   * Get next wall-clock timestamp
   * @returns {number} Next prerecorded milliseconds since epoch
   * @throws {Error} If no more timestamps available
   */
  getNow() {
    if (this.timestampIndex >= this.timestamps.length) {
      throw new Error(
        `DeterministicClockSource: Exhausted ${this.timestamps.length} timestamps at index ${this.timestampIndex}`
      );
    }
    return this.timestamps[this.timestampIndex++];
  }

  /**
   * Enforce monotonic: deterministic source must already be monotonic
   * This is a safety check.
   * @param {number} newTime - Proposed time
   * @returns {number} Same time (assumes input is already monotonic)
   */
  enforceMonotonic(newTime) {
    const monotonic =
      newTime > this.lastMonotonicTime
        ? newTime
        : this.lastMonotonicTime + 0.001;
    this.lastMonotonicTime = monotonic;
    return monotonic;
  }

  /**
   * Record actual timestamps from a live session for later replay
   * @param {number[]} nowTimestamps - Wall-clock timestamps
   * @param {number[]} highResTimestamps - High-res timestamps
   * @returns {DeterministicClockSource} New clock configured with these timestamps
   */
  static fromRecorded(nowTimestamps, highResTimestamps) {
    return new DeterministicClockSource({
      timestamps: nowTimestamps,
      highResTimestamps: highResTimestamps,
    });
  }
}

/**
 * Factory to create appropriate clock source
 * STRICT: Mode must be explicitly specified - no defaults
 * @param {ClockMode} mode - "live" or "deterministic"
 * @param {Object} config - Configuration for deterministic mode
 * @returns {ClockSource}
 * @throws {Error} If mode is not explicitly specified
 */
function createClockSource(mode, config = {}) {
  if (mode === "live") {
    return new LiveClockSource();
  }

  if (mode === "deterministic") {
    return new DeterministicClockSource(config);
  }

  throw new Error(
    `ClockSource: Mode must be explicitly specified as "live" or "deterministic". Got: ${mode}`
  );
}

module.exports = {
  LiveClockSource,
  DeterministicClockSource,
  createClockSource,
};
