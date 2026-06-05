const { UniversalLiveSession } = require("./live-session");
const { ReplayManager } = require("./replay-manager");

const sessionStore = globalThis.__ultUniversalSessions || new Map();
globalThis.__ultUniversalSessions = sessionStore;

async function createSession(request, options = {}) {
  const session = new UniversalLiveSession(request, options);
  sessionStore.set(session.id, session);
  await session.start();
  return session;
}

function getSession(sessionId) {
  return sessionStore.get(sessionId) || null;
}

async function stopSession(sessionId) {
  const session = getSession(sessionId);
  if (!session) {
    return false;
  }

  await session.stop();
  sessionStore.delete(sessionId);
  return true;
}

function listSessions() {
  return Array.from(sessionStore.values()).map((session) => session.getSnapshot());
}

/**
 * Get debug events for a session
 * @param {string} sessionId - Session ID
 * @param {string} mode - "full" or "compact"
 * @param {number} limit - Max events to return
 * @returns {Array|null} Debug events or null if session not found
 */
function getSessionDebugEvents(sessionId, mode, limit) {
  const session = getSession(sessionId);
  if (!session) return null;
  return session.getDebugEvents(mode).slice(-limit || undefined);
}

/**
 * Get a complete session dump
 * @param {string} sessionId - Session ID
 * @param {Object} options - Dump options (mode, limit)
 * @returns {Object|null} Session dump or null if session not found
 */
function getSessionDebugDump(sessionId, options = {}) {
  const session = getSession(sessionId);
  if (!session) return null;
  return session.getDebugSessionDump(options);
}

/**
 * Persist a session's debug dump to disk
 * @param {string} sessionId - Session ID
 * @param {string} dumpDir - Directory to persist to
 * @param {Object} options - Dump options
 * @returns {Object|null} Persistence result or null if session not found
 */
async function persistSessionDebugDump(sessionId, dumpDir, options = {}) {
  const session = getSession(sessionId);
  if (!session) return null;
  return session.persistDebugSessionDump(dumpDir, options);
}

module.exports = {
  createSession,
  getSession,
  listSessions,
  stopSession,
  getSessionDebugEvents,
  getSessionDebugDump,
  persistSessionDebugDump,
  ReplayManager, // Export for replay testing
};
