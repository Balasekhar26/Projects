const { verifyNormalizationDebugRecord } = require("./debug-record");

class ObserverDebugApi {
  constructor({ readEvents, readReplayComparison } = {}) {
    this.readEvents = typeof readEvents === "function" ? readEvents : () => [];
    this.readReplayComparison =
      typeof readReplayComparison === "function"
        ? readReplayComparison
        : (eventId) => ({
            supported: false,
            eventId,
            message: "Replay comparison is not available.",
          });
  }

  getEvents({ limit = 50, cursor = undefined, filter = {} } = {}) {
    const safeLimit = Math.max(1, Math.min(100, Number(limit) || 50));
    const filtered = this._applyFilter(this._readVerifiedEvents(), filter);
    const sorted = [...filtered].sort((left, right) => {
      if (left.normalizedTime !== right.normalizedTime) {
        return left.normalizedTime - right.normalizedTime;
      }
      return left.sessionTime - right.sessionTime;
    });

    const startIndex = cursor ? sorted.findIndex((event) => event.id === cursor) + 1 : 0;
    const events = sorted.slice(Math.max(0, startIndex), Math.max(0, startIndex) + safeLimit);
    const nextCursor =
      startIndex + safeLimit < sorted.length ? sorted[startIndex + safeLimit - 1]?.id || null : null;

    return {
      events,
      nextCursor,
      total: sorted.length,
    };
  }

  getEventById(eventId) {
    return this._readVerifiedEvents().find((candidate) => candidate.id === eventId) || null;
  }

  getNormalizationTrace(eventId) {
    const event = this.getEventById(eventId);
    if (!event) {
      return null;
    }

    return {
      eventId,
      dominantDomain: event.dominantDomain,
      ignoredDomains: event.ignoredDomains,
      contributions: event.contributions,
      normalizationVersion: event.normalizationVersion,
      timing: event.timing,
    };
  }

  getReplayComparison(eventId) {
    return this.readReplayComparison(eventId);
  }

  _readVerifiedEvents() {
    return this.readEvents().map((record) => {
      verifyNormalizationDebugRecord(record);
      return record;
    });
  }

  _applyFilter(events, filter) {
    return events.filter((event) => {
      if (filter.type && event.type !== filter.type) {
        return false;
      }
      if (filter.sourceEventId && !event.causalityKey?.sourceEventIds?.includes(filter.sourceEventId)) {
        return false;
      }
      if (filter.lowCoherenceOnly && (event.timing?.coherenceScore || 1) >= 0.6) {
        return false;
      }
      if (filter.ignoredDomainsOnly && !(event.ignoredDomains?.length > 0)) {
        return false;
      }
      return true;
    });
  }
}

function getSessionRecords(sessionId, { getSession, mode } = {}) {
  const resolveSession =
    typeof getSession === "function"
      ? getSession
      : require("../server/session-store").getSession;
  const session = resolveSession(sessionId);

  if (!session) {
    throw new Error(`Session not found: ${sessionId}`);
  }

  const records = session.getDebugEvents(mode);
  if (!mode || mode === "compact") {
    return records;
  }

  if (mode === "full") {
    return records;
  }

  throw new Error(`Unsupported mode: ${mode}`);
}

module.exports = {
  ObserverDebugApi,
  getSessionRecords,
};
