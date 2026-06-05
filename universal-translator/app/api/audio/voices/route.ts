import { NextResponse } from "next/server";

import { createCustomVoice, listAvailableTtsVoices } from "@/src/openai/audio";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const voices = await listAvailableTtsVoices();
    return NextResponse.json({ voices });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to list voices.",
      },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const name = formData.get("name");
    const consent = formData.get("consent");
    const audioSample = formData.get("audio_sample");

    if (typeof name !== "string" || !name.trim()) {
      return NextResponse.json({ error: "Voice name is required." }, { status: 400 });
    }

    if (typeof consent !== "string" || !consent.trim()) {
      return NextResponse.json({ error: "Consent ID is required." }, { status: 400 });
    }

    if (!(audioSample instanceof File)) {
      return NextResponse.json({ error: "Voice sample file is required." }, { status: 400 });
    }

    const payload = await createCustomVoice({
      name: name.trim(),
      consentId: consent.trim(),
      file: audioSample,
    });

    return NextResponse.json(payload);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to create custom voice.",
      },
      { status: 500 }
    );
  }
}
