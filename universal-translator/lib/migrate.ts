import { sqlite } from "@/lib/db";

export function initializeDatabase() {
  sqlite.exec(`
    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_lang TEXT NOT NULL DEFAULT 'en',
      target_lang TEXT NOT NULL DEFAULT 'te',
      mode TEXT NOT NULL DEFAULT 'offline',
      status TEXT NOT NULL DEFAULT 'active',
      translation_count INTEGER NOT NULL DEFAULT 0,
      duration_seconds INTEGER,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS translations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
      source_text TEXT NOT NULL,
      translated_text TEXT NOT NULL,
      source_lang TEXT NOT NULL DEFAULT 'en',
      target_lang TEXT NOT NULL DEFAULT 'te',
      confidence INTEGER,
      latency_ms INTEGER,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS settings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_lang TEXT NOT NULL DEFAULT 'en',
      target_lang TEXT NOT NULL DEFAULT 'te',
      mode TEXT NOT NULL DEFAULT 'offline',
      voice_preservation INTEGER NOT NULL DEFAULT 1,
      auto_detect_language INTEGER NOT NULL DEFAULT 1,
      latency_target INTEGER NOT NULL DEFAULT 1500,
      theme TEXT NOT NULL DEFAULT 'dark',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
    CREATE INDEX IF NOT EXISTS idx_translations_created_at ON translations(created_at);
    CREATE INDEX IF NOT EXISTS idx_translations_session_id ON translations(session_id);

    -- NeuroSeed consent-first memory reinforcement tables
    CREATE TABLE IF NOT EXISTS neuroseed_seeds (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      text TEXT NOT NULL,
      keywords TEXT NOT NULL,
      cue TEXT NOT NULL,
      approved INTEGER NOT NULL DEFAULT 0,
      consent_status TEXT NOT NULL DEFAULT 'pending',
      consent_model TEXT NOT NULL,
      approved_at TEXT,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS neuroseed_sessions (
      id TEXT PRIMARY KEY,
      started_at TEXT NOT NULL,
      ended_at TEXT,
      status TEXT NOT NULL DEFAULT 'running',
      approved_seed_ids TEXT NOT NULL,
      cue_events TEXT NOT NULL,
      uncued_seed_ids TEXT NOT NULL,
      settings TEXT NOT NULL,
      safety_boundary TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS neuroseed_consent_logs (
      id TEXT PRIMARY KEY,
      seed_id TEXT NOT NULL,
      action TEXT NOT NULL,
      consent_status TEXT NOT NULL,
      model_version TEXT NOT NULL,
      timestamp TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS neuroseed_recall_results (
      id TEXT PRIMARY KEY,
      seed_id TEXT NOT NULL,
      session_id TEXT NOT NULL,
      seed_title TEXT NOT NULL,
      condition TEXT NOT NULL,
      score INTEGER NOT NULL,
      answer TEXT NOT NULL,
      checked_at TEXT NOT NULL,
      consent_model TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_neuroseed_seeds_created ON neuroseed_seeds(created_at);
    CREATE INDEX IF NOT EXISTS idx_neuroseed_sessions_started ON neuroseed_sessions(started_at);
    CREATE INDEX IF NOT EXISTS idx_neuroseed_recall_session ON neuroseed_recall_results(session_id);
  `);

  const now = new Date().toISOString();
  sqlite.prepare(`
    INSERT INTO settings (
      id, source_lang, target_lang, mode, voice_preservation,
      auto_detect_language, latency_target, theme, created_at, updated_at
    )
    SELECT 1, 'en', 'te', 'offline', 1, 1, 1500, 'dark', ?, ?
    WHERE NOT EXISTS (SELECT 1 FROM settings WHERE id = 1)
  `).run(now, now);

  return { ok: true };
}
