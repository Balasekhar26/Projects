import { NextRequest, NextResponse } from "next/server";
import { db, settingsTable } from "@/lib/db";

export async function GET() {
  try {
    const [settings] = await db
      .select()
      .from(settingsTable)
      .limit(1);

    if (!settings) {
      // Return default settings if none exist
      return NextResponse.json({
        sourceLang: "en",
        targetLang: "te",
        mode: "offline",
        voicePreservation: true,
        autoDetectLanguage: true,
        latencyTarget: 1500,
        theme: "dark",
      });
    }

    return NextResponse.json(settings);
  } catch (error) {
    console.error("Failed to fetch settings:", error);
    return NextResponse.json({ error: "Failed to fetch settings" }, { status: 500 });
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const body = await request.json();

    const updateData: Partial<Omit<typeof settingsTable.$inferSelect, "id">> = {
      updatedAt: new Date().toISOString(),
    };

    if (body.sourceLang) updateData.sourceLang = body.sourceLang;
    if (body.targetLang) updateData.targetLang = body.targetLang;
    if (body.mode) updateData.mode = body.mode;
    if (body.voicePreservation !== undefined) updateData.voicePreservation = body.voicePreservation;
    if (body.autoDetectLanguage !== undefined) updateData.autoDetectLanguage = body.autoDetectLanguage;
    if (body.latencyTarget !== undefined) updateData.latencyTarget = body.latencyTarget;
    if (body.theme) updateData.theme = body.theme;

    const [settings] = await db
      .update(settingsTable)
      .set(updateData)
      .returning();

    return NextResponse.json(settings);
  } catch (error) {
    console.error("Failed to update settings:", error);
    return NextResponse.json({ error: "Failed to update settings" }, { status: 500 });
  }
}
