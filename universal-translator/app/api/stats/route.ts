import { NextResponse } from "next/server";
import { db, sessionsTable, translationsTable } from "@/lib/db";
import { eq, sql } from "drizzle-orm";

export async function GET() {
  try {
    // Get active sessions count
    const activeSessionsResult = await db
      .select({ count: sql<number>`count(*)` })
      .from(sessionsTable)
      .where(eq(sessionsTable.status, "active"));

    const activeSessions = activeSessionsResult[0]?.count || 0;

    // Get total translations
    const totalTranslationsResult = await db
      .select({ count: sql<number>`count(*)` })
      .from(translationsTable);

    const totalTranslations = totalTranslationsResult[0]?.count || 0;

    // Get average latency
    const avgLatencyResult = await db
      .select({ avg: sql<number>`avg(latency_ms)` })
      .from(translationsTable)
      .where(sql`latency_ms IS NOT NULL`);

    const avgLatencyMs = avgLatencyResult[0]?.avg || 0;

    // Get total duration from all sessions
    const totalDurationResult = await db
      .select({ sum: sql<number>`sum(duration_seconds)` })
      .from(sessionsTable)
      .where(sql`duration_seconds IS NOT NULL`);

    const totalDuration = totalDurationResult[0]?.sum || 0;

    return NextResponse.json({
      activeSessions,
      totalTranslations,
      avgLatencyMs: Math.round(avgLatencyMs),
      totalDuration,
    });
  } catch (error) {
    console.error("Failed to fetch stats:", error);
    return NextResponse.json({ error: "Failed to fetch stats" }, { status: 500 });
  }
}