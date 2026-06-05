import { NextResponse } from "next/server";
import { db, sessionsTable } from "@/lib/db";
import { eq, desc } from "drizzle-orm";

export async function GET() {
  try {
    const [session] = await db
      .select()
      .from(sessionsTable)
      .where(eq(sessionsTable.status, "active"))
      .orderBy(desc(sessionsTable.createdAt))
      .limit(1);

    return NextResponse.json(session || null);
  } catch (error) {
    console.error("Failed to fetch current session:", error);
    return NextResponse.json({ error: "Failed to fetch current session" }, { status: 500 });
  }
}