const { UniversalLiveSession } = require("./live-session");

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

module.exports = {
  createSession,
  getSession,
  listSessions,
  stopSession,
};
