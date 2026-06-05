import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const openaiKey = process.env.OPENAI_API_KEY;
  if (!openaiKey) {
    return NextResponse.json({ error: "OpenAI API key is not configured." }, { status: 500 });
  }

  try {
    const formData = await request.formData();
    const audioFile = formData.get("file");
    const language = formData.get("language")?.toString() || "en";

    if (!(audioFile instanceof Blob)) {
      return NextResponse.json({ error: "Missing audio file." }, { status: 400 });
    }

    const openaiForm = new FormData();
    openaiForm.append("file", audioFile, "speech.webm");
    openaiForm.append("model", "whisper-1");
    openaiForm.append("language", language);

    const response = await fetch("https://api.openai.com/v1/audio/transcriptions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${openaiKey}`,
      },
      body: openaiForm,
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json({ error: `Whisper transcription error: ${errorText}` }, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json({ text: data.text || "" });
  } catch {
    return NextResponse.json({ error: "Unable to transcribe audio." }, { status: 500 });
  }
}
