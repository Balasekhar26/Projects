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
      platform: typeof payload?.platform === "string" ? payload.platform : process.platform,
      sourceLanguage: typeof payload?.sourceLanguage === "string" ? payload.sourceLanguage : "en",
      targetLanguage: typeof payload?.targetLanguage === "string" ? payload.targetLanguage : "en",
      autoDetectSource: payload?.autoDetectSource !== false,
      sessionKind: typeof payload?.sessionKind === "string" ? payload.sessionKind : "browser_debug",
      inputDeviceId: typeof payload?.inputDeviceId === "string" ? payload.inputDeviceId : "",
      outputDeviceId: typeof payload?.outputDeviceId === "string" ? payload.outputDeviceId : "",
      micInputDeviceId:
        typeof payload?.micInputDeviceId === "string"
          ? payload.micInputDeviceId
          : typeof payload?.inputDeviceId === "string"
            ? payload.inputDeviceId
            : "",
      speakerOutputDeviceId:
        typeof payload?.speakerOutputDeviceId === "string"
          ? payload.speakerOutputDeviceId
          : typeof payload?.outputDeviceId === "string"
            ? payload.outputDeviceId
            : typeof payload?.ttsOutputDeviceName === "string"
              ? payload.ttsOutputDeviceName
              : "",
      micTargetLanguage:
        typeof payload?.micTargetLanguage === "string"
          ? payload.micTargetLanguage
          : typeof payload?.targetLanguage === "string"
            ? payload.targetLanguage
            : "en",
      speakerTargetLanguage:
        typeof payload?.speakerTargetLanguage === "string"
          ? payload.speakerTargetLanguage
          : typeof payload?.targetLanguage === "string"
            ? payload.targetLanguage
            : "en",
      routeProfileId: typeof payload?.routeProfileId === "string" ? payload.routeProfileId : "browser-debug",
      onlinePolicy: typeof payload?.onlinePolicy === "string" ? payload.onlinePolicy : "offline-only",
      voiceProfileId:
        typeof payload?.voiceProfileId === "string"
          ? payload.voiceProfileId
          : typeof payload?.ttsVoiceName === "string"
            ? `builtin:${payload.ttsVoiceName}`
            : "generic:offline-default",
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
