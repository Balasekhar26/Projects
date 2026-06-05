import { NextResponse } from "next/server";
import { getSession } from "@/src/server/session-store";
import { ObserverDebugApi } from "@/src/ai-observer/debug-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type DebugApi = {
  getEvents(input: {
    limit: number;
    cursor?: string;
    filter: {
      type?: string;
      lineageId?: string;
      lowCoherenceOnly: boolean;
      ignoredDomainsOnly: boolean;
    };
  }): unknown;
};

export async function GET(
  request: Request,
  context: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await context.params;
  const session = getSession(sessionId);

  if (!session) {
    return NextResponse.json({ error: "Session not found." }, { status: 404 });
  }

  const url = new URL(request.url);
  const cursor = url.searchParams.get("cursor") || undefined;
  const api = new ObserverDebugApi({
    readEvents: () => session.getDebugEvents(),
    readReplayComparison: (eventId: string) => session.getReplayComparison(eventId),
  });

  return NextResponse.json(
    (api as unknown as DebugApi).getEvents({
      limit: Number(url.searchParams.get("limit") || 50),
      cursor,
      filter: {
        type: url.searchParams.get("type") || undefined,
        lineageId: url.searchParams.get("lineageId") || undefined,
        lowCoherenceOnly: url.searchParams.get("lowCoherenceOnly") === "true",
        ignoredDomainsOnly: url.searchParams.get("ignoredDomainsOnly") === "true",
      },
    })
  );
}
