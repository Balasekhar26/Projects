import { NextResponse } from "next/server";
import { listDeviceTopology } from "@/packages/ult-core/src/device-control/topology";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const topology = await listDeviceTopology();
    return NextResponse.json(topology);
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to inspect device topology.",
      },
      { status: 500 }
    );
  }
}
