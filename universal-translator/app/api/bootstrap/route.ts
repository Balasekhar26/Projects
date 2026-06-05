import { NextResponse } from "next/server";
import { runBootstrapInspection } from "@/packages/ult-core/src/installer/bootstrap";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const report = await runBootstrapInspection();
    return NextResponse.json(report);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to inspect runtime bootstrap state.",
      },
      { status: 500 }
    );
  }
}
