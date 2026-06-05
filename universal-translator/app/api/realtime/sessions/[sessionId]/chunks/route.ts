import { NextResponse } from "next/server";
import { getSession } from "@/src/server/session-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getFileExtension(name: string, mimeType: string) {
  const loweredName = name.toLowerCase();
  if (loweredName.endsWith(".webm")) return "webm";
  if (loweredName.endsWith(".mp3")) return "mp3";
  if (loweredName.endsWith(".wav")) return "wav";
  if (mimeType.includes("webm")) return "webm";
  if (mimeType.includes("mpeg")) return "mp3";
  return "wav";
}

export async function POST(
  request: Request,
  context: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await context.params;
  const session = getSession(sessionId);

  if (!session) {
    return NextResponse.json({ error: "Session not found." }, { status: 404 });
  }

  try {
    const formData = await request.formData();
    const audioFile = formData.get("file");

    if (!(audioFile instanceof Blob)) {
      return NextResponse.json({ error: "Missing audio chunk." }, { status: 400 });
    }

    const fileName = "name" in audioFile && typeof audioFile.name === "string" ? audioFile.name : "chunk.wav";
    const mimeType = audioFile.type || "";
    const chunk = await audioFile.arrayBuffer();
    const analysisValue = formData.get("analysis");
    let analysis = null;
    if (typeof analysisValue === "string" && analysisValue.trim()) {
      analysis = JSON.parse(analysisValue);
    }
    const result = await session.enqueueChunk({
      audioBuffer: Buffer.from(chunk),
      fileExtension: getFileExtension(fileName, mimeType),
      analysis,
    });

    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to process audio chunk.",
      },
      { status: 500 }
    );
  }
}
