import { NextResponse } from "next/server";
import fs from "fs/promises";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MARKER = path.join(process.cwd(), ".ult-setup-complete");

export async function GET() {
  // Check explicit marker first
  try {
    await fs.access(MARKER);
    return NextResponse.json({ isSetupComplete: true });
  } catch {
    // No marker — run bootstrap to auto-detect
  }

  try {
    const { runBootstrapInspection } = await import(
      "@/packages/ult-core/src/installer/bootstrap"
    );
    const report = await runBootstrapInspection();
    if (report.selfTest.ok) {
      // All components present — write marker and skip wizard
      await fs.writeFile(MARKER, new Date().toISOString(), "utf8").catch(() => {});
      return NextResponse.json({ isSetupComplete: true });
    }
    return NextResponse.json({ isSetupComplete: false });
  } catch {
    return NextResponse.json({ isSetupComplete: false });
  }
}

export async function POST() {
  await fs.writeFile(MARKER, new Date().toISOString(), "utf8");
  return NextResponse.json({ success: true });
}
