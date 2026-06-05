import { NextRequest, NextResponse } from "next/server";
import { db, translationsTable, insertTranslationSchema } from "@/lib/db";

export async function GET() {
  try {
    const translations = await db
      .select()
      .from(translationsTable)
      .orderBy(translationsTable.createdAt)
      .limit(100); // Limit to recent translations

    return NextResponse.json(translations);
  } catch (error) {
    console.error("Failed to fetch translations:", error);
    return NextResponse.json({ error: "Failed to fetch translations" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const validatedData = insertTranslationSchema.parse(body);

    const [translation] = await db
      .insert(translationsTable)
      .values({
        ...validatedData,
        createdAt: new Date().toISOString(),
      })
      .returning();

    return NextResponse.json(translation, { status: 201 });
  } catch (error) {
    console.error("Failed to create translation:", error);
    return NextResponse.json({ error: "Failed to create translation" }, { status: 500 });
  }
}
