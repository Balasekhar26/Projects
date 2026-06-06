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
