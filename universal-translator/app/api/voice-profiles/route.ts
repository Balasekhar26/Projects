import { NextResponse } from "next/server";
import { getCoreConfig } from "@/packages/ult-core/src/config";
import { listVoiceProfiles } from "@/packages/ult-core/src/voice-clone/registry";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const profiles = await listVoiceProfiles(getCoreConfig());
    return NextResponse.json({ profiles });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to list voice profiles.",
      },
      { status: 500 }
    );
  }
}
