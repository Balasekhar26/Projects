package com.ulttranslator.app

data class StartSessionRequest(
    val platform: String = "android",
    val sourceLanguage: String = "en",
    val targetLanguage: String = "te",
    val autoDetectSource: Boolean = true,
    val sessionKind: String = "android_runtime",
    val inputDeviceId: String = "",
    val outputDeviceId: String = "",
    val micInputDeviceId: String = "",
    val speakerOutputDeviceId: String = "",
    val micTargetLanguage: String = "te",
    val speakerTargetLanguage: String = "te",
    val routeProfileId: String = "android-runtime",
    val onlinePolicy: String = "offline-only",
    val voiceProfileId: String = "generic:offline-default",
    val preserveEmotion: Boolean = true,
)

data class SessionEvent(
    val type: String,
    val transcript: String = "",
    val translatedText: String = "",
    val backend: String = "",
    val message: String = "",
)

data class RouteProfile(
    val id: String,
    val label: String,
    val status: String,
)
