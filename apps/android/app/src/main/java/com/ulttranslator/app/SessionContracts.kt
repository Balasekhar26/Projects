package com.ulttranslator.app

data class StartSessionRequest(
    val sourceLanguage: String = "en",
    val targetLanguage: String = "te",
    val sessionKind: String = "microphone",
    val inputDeviceId: String = "",
    val outputDeviceId: String = "",
    val routeProfileId: String = "android-mic",
    val onlinePolicy: String = "auto",
    val voiceProfileId: String = "builtin:android-system",
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
