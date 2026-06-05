import { NextResponse } from "next/server";
import { listAudioRoutingOptions } from "@/src/server/realtime-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const options = await listAudioRoutingOptions();
    return NextResponse.json(options);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to list audio routing options.",
      },
      { status: 500 }
    );
  }
}
