/**
 * Replay Manager
 * 
 * Enables recording timestamps from live sessions and replaying them
 * in deterministic mode to verify logic stability independent of timing.
 * 
 * Usage:
 * 1. Record live session:
 *    const manager = new ReplayManager();
 *    session.on('event', (event) => manager.recordTimestamps(session));
 * 
 * 2. Create deterministic clock for replay:
 *    const clock = manager.createReplayClock();
 *    const replaySession = new UniversalLiveSession(request, { clock });
 */

const { DeterministicClockSource } = require("./clock-source");

class ReplayManager {
  constructor() {
    this.nowTimestamps = [];
    this.highResTimestamps = [];
    this.eventSequence = 0;
  }

  /**
   * Record timing from a live session
   * Call this for each event during a live session
   * @param {UniversalLiveSession} session - Live session instance
   */
  recordTimestamps(session) {
    try {
      // Record high-res time from clock
      this.highResTimestamps.push(session.clock.getHighResTimeMs());

      // Record wall-clock time
      this.nowTimestamps.push(session.clock.getNow());

      this.eventSequence++;
    } catch (error) {
      console.warn(
        `ReplayManager: Could not record timestamp for event ${this.eventSequence}:`,
        error.message
      );
    }
  }

  /**
   * Create a deterministic clock for replay using recorded timestamps
   * @returns {DeterministicClockSource} Clock pre-configured with recorded timestamps
   * @throws {Error} If no timestamps have been recorded yet
   */
  createReplayClock() {
    if (this.nowTimestamps.length === 0) {
      throw new Error(
        "ReplayManager: No timestamps recorded. Record a live session first using recordTimestamps()."
      );
    }

    return DeterministicClockSource.fromRecorded(
      [...this.nowTimestamps],
      [...this.highResTimestamps]
    );
  }

  /**
   * Get a copy of recorded timestamps for manual inspection
   * @returns {Object} Object with nowTimestamps and highResTimestamps arrays
   */
  getRecordedTimestamps() {
    return {
      nowTimestamps: [...this.nowTimestamps],
      highResTimestamps: [...this.highResTimestamps],
      eventCount: this.eventSequence,
    };
  }

  /**
   * Save recorded timestamps to file for offline replay
   * @param {string} filepath - Where to write JSON file
   * @returns {Object} Information about saved file
   */
  async saveTimestampRecording(filepath) {
    const fs = require("fs/promises");

    const data = {
      timestamp: new Date().toISOString(),
      eventCount: this.eventSequence,
      nowTimestamps: this.nowTimestamps,
      highResTimestamps: this.highResTimestamps,
    };

    await fs.writeFile(filepath, JSON.stringify(data, null, 2));

    return {
      filepath,
      eventCount: this.eventSequence,
      size: (await fs.stat(filepath)).size,
    };
  }

  /**
   * Load timestamps from a previously saved recording
   * @param {string} filepath - Path to JSON file created by saveTimestampRecording()
   * @returns {Promise<Object>} Loaded timestamps
   */
  static async loadTimestampRecording(filepath) {
    const fs = require("fs/promises");
    const content = await fs.readFile(filepath, "utf8");
    const data = JSON.parse(content);

    return {
      timestamp: data.timestamp,
      eventCount: data.eventCount,
      nowTimestamps: data.nowTimestamps,
      highResTimestamps: data.highResTimestamps,
    };
  }

  /**
   * Create a ReplayManager from saved timestamps
   * @param {string} filepath - Path to JSON file
   * @returns {Promise<ReplayManager>} Configured replay manager
   */
  static async fromSavedRecording(filepath) {
    const data = await ReplayManager.loadTimestampRecording(filepath);
    const manager = new ReplayManager();
    manager.nowTimestamps = data.nowTimestamps;
    manager.highResTimestamps = data.highResTimestamps;
    manager.eventSequence = data.eventCount;
    return manager;
  }

  /**
   * Clear all recorded timestamps
   */
  reset() {
    this.nowTimestamps = [];
    this.highResTimestamps = [];
    this.eventSequence = 0;
  }

  /**
   * Get statistics about recorded timestamps
   * @returns {Object} Stats including timing ranges and deltas
   */
  getStatistics() {
    if (this.highResTimestamps.length === 0) {
      return { eventCount: 0, message: "No data recorded" };
    }

    const highRes = this.highResTimestamps;
    const deltas = [];
    for (let i = 1; i < highRes.length; i++) {
      deltas.push(highRes[i] - highRes[i - 1]);
    }

    return {
      eventCount: this.eventSequence,
      timelineStart: highRes[0],
      timelineEnd: highRes[highRes.length - 1],
      totalElapsed: highRes[highRes.length - 1] - highRes[0],
      deltaStats: {
        min: Math.min(...deltas),
        max: Math.max(...deltas),
        mean: deltas.reduce((a, b) => a + b, 0) / deltas.length,
        median: deltas.sort((a, b) => a - b)[Math.floor(deltas.length / 2)],
      },
    };
  }
}

module.exports = { ReplayManager };
