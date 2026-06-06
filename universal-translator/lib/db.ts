import fs from "fs";
import path from "path";
import Database from "better-sqlite3";
import { drizzle } from "drizzle-orm/better-sqlite3";
import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";
import { z } from "zod";

const runtimeDir = process.env.ULT_RUNTIME_DIR || path.join(process.cwd(), ".ult-runtime");
fs.mkdirSync(runtimeDir, { recursive: true });

export const databasePath = process.env.ULT_DB_PATH || path.join(runtimeDir, "universal-translator.db");
export const sqlite = new Database(databasePath);
sqlite.pragma("journal_mode = WAL");
sqlite.pragma("foreign_keys = ON");

export const sessionsTable = sqliteTable("sessions", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  sourceLang: text("source_lang").notNull().default("en"),
  targetLang: text("target_lang").notNull().default("te"),
  mode: text("mode").notNull().default("offline"),
  status: text("status").notNull().default("active"),
  translationCount: integer("translation_count").notNull().default(0),
  durationSeconds: integer("duration_seconds"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const translationsTable = sqliteTable("translations", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  sessionId: integer("session_id").references(() => sessionsTable.id, { onDelete: "set null" }),
  sourceText: text("source_text").notNull(),
  translatedText: text("translated_text").notNull(),
  sourceLang: text("source_lang").notNull().default("en"),
  targetLang: text("target_lang").notNull().default("te"),
  confidence: integer("confidence"),
  latencyMs: integer("latency_ms"),
  createdAt: text("created_at").notNull(),
});

export const settingsTable = sqliteTable("settings", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  sourceLang: text("source_lang").notNull().default("en"),
  targetLang: text("target_lang").notNull().default("te"),
  mode: text("mode").notNull().default("offline"),
  voicePreservation: integer("voice_preservation", { mode: "boolean" }).notNull().default(true),
  autoDetectLanguage: integer("auto_detect_language", { mode: "boolean" }).notNull().default(true),
  latencyTarget: integer("latency_target").notNull().default(1500),
  theme: text("theme").notNull().default("dark"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const db = drizzle(sqlite);

export const insertSessionSchema = z.object({
  sourceLang: z.string().min(2).default("en"),
  targetLang: z.string().min(2).default("te"),
  mode: z.string().default("offline"),
  status: z.string().default("active"),
  translationCount: z.number().int().nonnegative().optional(),
  durationSeconds: z.number().int().nonnegative().optional(),
});

export const insertTranslationSchema = z.object({
  sessionId: z.number().int().positive().optional(),
  sourceText: z.string().default(""),
  translatedText: z.string().default(""),
  sourceLang: z.string().min(2).default("en"),
  targetLang: z.string().min(2).default("te"),
  confidence: z.number().int().min(0).max(100).optional(),
  latencyMs: z.number().int().nonnegative().optional(),
});
