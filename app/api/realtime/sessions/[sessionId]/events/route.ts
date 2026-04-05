import { getSession } from "@/src/server/session-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await context.params;
  const session = getSession(sessionId);

  if (!session) {
    return Response.json({ error: "Session not found." }, { status: 404 });
  }

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      let closed = false;

      const writeEvent = (event: unknown) => {
        if (!closed) {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
        }
      };

      const heartbeat = setInterval(() => {
        if (!closed) {
          controller.enqueue(encoder.encode(":keepalive\n\n"));
        }
      }, 15000);

      const onEvent = (event: unknown) => {
        writeEvent(event);
      };

      const onAbort = () => {
        cleanup();
        if (!closed) {
          closed = true;
          controller.close();
        }
      };

      const cleanup = () => {
        clearInterval(heartbeat);
        session.off("event", onEvent);
        request.signal.removeEventListener("abort", onAbort);
      };

      session.on("event", onEvent);
      writeEvent({
        type: "snapshot",
        sessionId,
        events: session.getSnapshot().events,
      });

      request.signal.addEventListener("abort", onAbort);
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
