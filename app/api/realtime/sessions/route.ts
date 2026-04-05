import { NextResponse } from "next/server";
import { createSession } from "@/src/server/session-store";
import { createStartSessionRequest } from "@/packages/ult-core/src/contracts";
import { prepareRuntimeForSession } from "@/packages/ult-core/src/installer/provisioning";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const payload = await request.json();
    const sessionRequest = createStartSessionRequest({
      sourceLanguage: typeof payload?.sourceLanguage === "string" ? payload.sourceLanguage : "en",
      targetLanguage: typeof payload?.targetLanguage === "string" ? payload.targetLanguage : "en",
      sessionKind: typeof payload?.sessionKind === "string" ? payload.sessionKind : "browser-debug",
      inputDeviceId: typeof payload?.inputDeviceId === "string" ? payload.inputDeviceId : "",
      outputDeviceId:
        typeof payload?.outputDeviceId === "string"
          ? payload.outputDeviceId
          : typeof payload?.ttsOutputDeviceName === "string"
            ? payload.ttsOutputDeviceName
            : "",
      routeProfileId: typeof payload?.routeProfileId === "string" ? payload.routeProfileId : "browser-debug",
      onlinePolicy: typeof payload?.onlinePolicy === "string" ? payload.onlinePolicy : "auto",
      voiceProfileId:
        typeof payload?.voiceProfileId === "string"
          ? payload.voiceProfileId
          : typeof payload?.ttsVoiceName === "string"
            ? `builtin:${payload.ttsVoiceName}`
            : "builtin:alloy",
      preserveEmotion: payload?.preserveEmotion !== false,
    });

    const preparation = await prepareRuntimeForSession({
      sourceLanguage: sessionRequest.sourceLanguage,
      targetLanguage: sessionRequest.targetLanguage,
      onlinePolicy: sessionRequest.onlinePolicy,
    });
    const session = await createSession(sessionRequest);

    return NextResponse.json({
      sessionId: session.id,
      createdAt: session.createdAt,
      preparation,
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to create translation session.",
      },
      { status: 500 }
    );
  }
}
