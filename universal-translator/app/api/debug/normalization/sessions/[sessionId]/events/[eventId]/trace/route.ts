import { NextResponse } from "next/server";
import { getSession } from "@/src/server/session-store";
import { ObserverDebugApi } from "@/src/ai-observer/debug-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type DebugApi = {
  getNormalizationTrace(eventId: string): unknown;
};

export async function GET(
  _request: Request,
  context: { params: Promise<{ sessionId: string; eventId: string }> }
) {
  const { sessionId, eventId } = await context.params;
  const session = getSession(sessionId);

  if (!session) {
    return NextResponse.json({ error: "Session not found." }, { status: 404 });
  }

  const api = new ObserverDebugApi({
    readEvents: () => session.getDebugEvents(),
    readReplayComparison: (id: string) => session.getReplayComparison(id),
  });
  const trace = (api as unknown as DebugApi).getNormalizationTrace(eventId);

  if (!trace) {
    return NextResponse.json({ error: "Event not found." }, { status: 404 });
  }

  return NextResponse.json(trace);
}
