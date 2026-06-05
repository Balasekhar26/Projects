import { NextResponse } from "next/server";

import { createVoiceConsent } from "@/src/openai/audio";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const name = formData.get("name");
    const language = formData.get("language");
    const recording = formData.get("recording");

    if (typeof name !== "string" || !name.trim()) {
      return NextResponse.json({ error: "Consent name is required." }, { status: 400 });
    }

    if (typeof language !== "string" || !language.trim()) {
      return NextResponse.json({ error: "Consent language is required." }, { status: 400 });
    }

    if (!(recording instanceof File)) {
      return NextResponse.json({ error: "Consent recording is required." }, { status: 400 });
    }

    const payload = await createVoiceConsent({
      name: name.trim(),
      language: language.trim(),
      file: recording,
    });

    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to create voice consent.",
      },
      { status: 500 }
    );
  }
}
