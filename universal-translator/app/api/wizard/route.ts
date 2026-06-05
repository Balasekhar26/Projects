import { NextRequest, NextResponse } from "next/server";
import fs from "fs/promises";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MARKER = path.join(process.cwd(), ".ult-setup-complete");

export async function GET() {
  try {
    const { runBootstrapInspection } = await import("@/packages/ult-core/src/installer/bootstrap");
    const report = await runBootstrapInspection();

    const allOk = report.selfTest.ok;
    const steps = report.selfTest.checks.map((c: { label: string; ok: boolean }) => ({
      id: c.label,
      title: c.label,
      description: c.ok ? "Ready" : "Missing",
      status: c.ok ? "completed" : "error",
      logs: [c.ok ? `✅ ${c.label} found` : `❌ ${c.label} missing`],
    }));

    return NextResponse.json({
      isRunning: false,
      isComplete: allOk,
      currentStep: steps.filter((s: { status: string }) => s.status === "completed").length,
      totalSteps: steps.length,
      steps,
      hardware: report.hardware,
      error: allOk ? null : "Some components are missing. Run setup.bat to fix.",
    });
  } catch (error) {
    return NextResponse.json({
      isRunning: false,
      isComplete: false,
      currentStep: 0,
      totalSteps: 1,
      steps: [],
      error: error instanceof Error ? error.message : "Bootstrap inspection failed.",
    });
  }
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const action = body?.action;

  if (action === "start") {
    try {
      const { runBootstrapInspection } = await import("@/packages/ult-core/src/installer/bootstrap");
      const report = await runBootstrapInspection();
      if (report.selfTest.ok) {
        await fs.writeFile(MARKER, new Date().toISOString(), "utf8");
        return NextResponse.json({ success: true, allOk: true });
      }
      return NextResponse.json({
        success: false,
        allOk: false,
        missing: report.selfTest.checks.filter((c: { ok: boolean }) => !c.ok).map((c: { label: string }) => c.label),
      });
    } catch (error) {
      return NextResponse.json(
        { error: error instanceof Error ? error.message : "Wizard start failed." },
        { status: 500 }
      );
    }
  }

  if (action === "stop") {
    return NextResponse.json({ success: true });
  }

  if (action === "complete") {
    await fs.writeFile(MARKER, new Date().toISOString(), "utf8").catch(() => {});
    return NextResponse.json({ success: true });
  }

  return NextResponse.json({ error: "Invalid action" }, { status: 400 });
}
