import { NextResponse } from "next/server";
import { translateInput } from "@/src/translation/service";

export async function POST(request: Request) {
  try {
    const { text, source, target, onlinePolicy } = await request.json();

    if (!text || !source || !target) {
      return NextResponse.json({ error: "Missing required fields." }, { status: 400 });
    }

    const result = await translateInput({
      transcript: text,
      whisperTranslation: "",
      detectedLanguage: source,
      sourceLanguage: source,
      targetLanguage: target,
      onlinePolicy,
    });

    return NextResponse.json({
      translatedText: result.translatedText || "",
      backend: result.backend,
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Translation request failed.",
      },
      { status: 500 }
    );
  }
}
