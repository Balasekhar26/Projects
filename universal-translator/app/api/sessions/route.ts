import { NextRequest, NextResponse } from "next/server";
import { db, sessionsTable, insertSessionSchema } from "@/lib/db";

export async function GET() {
  try {
    const sessions = await db.select().from(sessionsTable).orderBy(sessionsTable.createdAt);
    return NextResponse.json(sessions);
  } catch (error) {
    console.error("Failed to fetch sessions:", error);
    return NextResponse.json({ error: "Failed to fetch sessions" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const validatedData = insertSessionSchema.parse(body);

    const now = new Date().toISOString();
    const [session] = await db
      .insert(sessionsTable)
      .values({
        ...validatedData,
        createdAt: now,
        updatedAt: now,
      })
      .returning();

    return NextResponse.json(session, { status: 201 });
  } catch (error) {
    console.error("Failed to create session:", error);
    return NextResponse.json({ error: "Failed to create session" }, { status: 500 });
  }
}
