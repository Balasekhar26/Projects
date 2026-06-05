import { NextResponse } from "next/server";
import { getSession } from "@/src/server/session-store";
import { ObserverDebugApi } from "@/src/ai-observer/debug-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type DebugApi = {
  getReplayComparison(eventId: string): unknown;
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

  return NextResponse.json((api as unknown as DebugApi).getReplayComparison(eventId));
}
