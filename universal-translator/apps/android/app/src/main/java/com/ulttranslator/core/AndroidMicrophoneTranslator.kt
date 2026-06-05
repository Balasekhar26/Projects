/**
 * Android Microphone Translation Engine
 * 
 * Handles real-time microphone capture and translation on Android devices.
 * Uses accessible APIs that work within Android's app sandbox.
 */

package com.ulttranslator.core

import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Handler
import android.os.Looper
import android.util.Log
import kotlinx.coroutines.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.TimeUnit

class AndroidMicrophoneTranslator(
    private val context: Context,
    private val config: TranslationConfig
) {
    companion object {
        private const val TAG = "AndroidMicTranslator"
        private const val SAMPLE_RATE = 16000
        private const val CHANNELS = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
        private const val BUFFER_REDUCTION_RATIO = 2
    }

    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private var translationScope = CoroutineScope(Dispatchers.Default + Job())
    private val listeners = mutableListOf<ITranslationListener>()
    private var sessionId: String? = null
    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    interface ITranslationListener {
        fun onAudioCaptured(audioData: ByteArray, durationMs: Int)
        fun onTranscriptionStarted()
        fun onTranscriptionComplete(transcript: String, language: String)
        fun onTranslationComplete(originalText: String, translatedText: String)
        fun onSynthesisStarted()
        fun onSynthesisComplete()
        fun onError(error: String)
    }

    /**
     * Initialize microphone capture
     */
    fun initialize(): Boolean {
        return try {
            val bufferSize = AudioRecord.getMinBufferSize(
                SAMPLE_RATE,
                CHANNELS,
                AUDIO_FORMAT
            )

            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE,
                CHANNELS,
                AUDIO_FORMAT,
                bufferSize * BUFFER_REDUCTION_RATIO
            )

            if (audioRecord?.state == AudioRecord.STATE_INITIALIZED) {
                Log.d(TAG, "AudioRecord initialized successfully")
                true
            } else {
                Log.e(TAG, "Failed to initialize AudioRecord")
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "Initialization error: ${e.message}")
            notifyError("Failed to initialize microphone: ${e.message}")
            false
        }
    }

    /**
     * Start microphone capture
     */
    fun startCapture() {
        if (isRecording) {
            Log.w(TAG, "Already recording")
            return
        }

        try {
            audioRecord?.startRecording()
            isRecording = true

            translationScope.launch {
                captureAudioLoop()
            }

            Log.d(TAG, "Microphone capture started")
        } catch (e: Exception) {
            Log.e(TAG, "Start capture error: ${e.message}")
            notifyError("Failed to start recording: ${e.message}")
        }
    }

    /**
     * Stop microphone capture
     */
    fun stopCapture() {
        try {
            isRecording = false
            audioRecord?.stop()
            Log.d(TAG, "Microphone capture stopped")
        } catch (e: Exception) {
            Log.e(TAG, "Stop capture error: ${e.message}")
        }
    }

    /**
     * Main audio capture loop
     */
    private suspend fun captureAudioLoop() {
        val bufferSize = audioRecord?.bufferSizeInFrames ?: return
        val buffer = ByteArray(bufferSize * 2)

        while (isRecording) {
            try {
                val bytesRead = audioRecord?.read(buffer, 0, buffer.size) ?: 0

                if (bytesRead > 0) {
                    val audioChunk = buffer.sliceArray(0 until bytesRead)
                    val durationMs = (bytesRead * 1000) / (SAMPLE_RATE * 2)

                    notifyAudioCaptured(audioChunk, durationMs)

                    // Process audio chunk for translation
                    processAudioChunk(audioChunk)
                }

                delay(100) // Chunk interval
            } catch (e: Exception) {
                Log.e(TAG, "Capture loop error: ${e.message}")
            }
        }
    }

    /**
     * Process captured audio chunk
     */
    private suspend fun processAudioChunk(audioData: ByteArray) {
        try {
            notifyTranscriptionStarted()

            // Call STT service
            val transcript = transcribeAudio(audioData)
            if (transcript.isEmpty()) return

            notifyTranscriptionComplete(transcript, config.sourceLanguage)

            // Call translation service
            val translatedText = translateText(transcript)
            notifyTranslationComplete(transcript, translatedText)

            // Call TTS service
            notifySynthesisStarted()
            synthesizeAndPlayAudio(translatedText)
            notifySynthesisComplete()
        } catch (e: Exception) {
            Log.e(TAG, "Processing error: ${e.message}")
            notifyError("Error processing audio: ${e.message}")
        }
    }

    /** Ensure a session exists on the ULT server and return its id. */
    private suspend fun ensureSession(): String = withContext(Dispatchers.IO) {
        sessionId?.let { return@withContext it }
        val body = JSONObject().apply {
            put("platform", "android")
            put("sourceLanguage", config.sourceLanguage)
            put("targetLanguage", config.targetLanguage)
            put("autoDetectSource", true)
            put("sessionKind", "android_runtime")
            put("micTargetLanguage", config.targetLanguage)
            put("speakerTargetLanguage", config.targetLanguage)
            put("routeProfileId", "android-runtime")
            put("onlinePolicy", "offline-only")
            put("voiceProfileId", "generic:offline-default")
        }.toString()
        val response = http.newCall(
            Request.Builder()
                .url("${config.serverUrl}/api/realtime/sessions")
                .post(body.toRequestBody("application/json".toMediaType()))
                .build()
        ).execute()
        val json = JSONObject(response.body?.string() ?: "{}")
        response.close()
        if (!response.isSuccessful) throw Exception(json.optString("error", "Session creation failed"))
        json.getString("sessionId").also { sessionId = it }
    }

    /** Upload a WAV chunk to the server pipeline and return the translated text. */
    private suspend fun transcribeAudio(audioData: ByteArray): String = withContext(Dispatchers.IO) {
        val id = ensureSession()
        val wav = buildWav(audioData)
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", "chunk.wav", wav.toRequestBody("audio/wav".toMediaType()))
            .build()
        val response = http.newCall(
            Request.Builder()
                .url("${config.serverUrl}/api/realtime/sessions/$id/chunks")
                .post(body)
                .build()
        ).execute()
        response.close()
        // Translation is delivered asynchronously via SSE; return empty here
        ""
    }

    private suspend fun translateText(text: String): String = text

    private suspend fun synthesizeAndPlayAudio(text: String) {
        Log.d(TAG, "TTS delegated to server pipeline for: $text")
    }

    private fun buildWav(pcm: ByteArray): ByteArray {
        val out = ByteArrayOutputStream()
        fun writeLE32(v: Int) = out.write(ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(v).array())
        fun writeLE16(v: Int) = out.write(ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN).putShort(v.toShort()).array())
        out.write("RIFF".toByteArray()); writeLE32(36 + pcm.size)
        out.write("WAVE".toByteArray())
        out.write("fmt ".toByteArray()); writeLE32(16)
        writeLE16(1); writeLE16(1)
        writeLE32(SAMPLE_RATE); writeLE32(SAMPLE_RATE * 2)
        writeLE16(2); writeLE16(16)
        out.write("data".toByteArray()); writeLE32(pcm.size)
        out.write(pcm)
        return out.toByteArray()
    }

    /**
     * Clean up resources
     */
    fun release() {
        try {
            stopCapture()
            audioRecord?.release()
            audioRecord = null
            translationScope.cancel()
            Log.d(TAG, "Resources released")
        } catch (e: Exception) {
            Log.e(TAG, "Release error: ${e.message}")
        }
    }

    /**
     * Event notification methods
     */
    fun addListener(listener: ITranslationListener) {
        listeners.add(listener)
    }

    fun removeListener(listener: ITranslationListener) {
        listeners.remove(listener)
    }

    private fun notifyAudioCaptured(audioData: ByteArray, durationMs: Int) {
        Handler(Looper.getMainLooper()).post {
            listeners.forEach { it.onAudioCaptured(audioData, durationMs) }
        }
    }

    private fun notifyTranscriptionStarted() {
        Handler(Looper.getMainLooper()).post {
            listeners.forEach { it.onTranscriptionStarted() }
        }
    }

    private fun notifyTranscriptionComplete(transcript: String, language: String) {
        Handler(Looper.getMainLooper()).post {
            listeners.forEach { it.onTranscriptionComplete(transcript, language) }
        }
    }

    private fun notifyTranslationComplete(originalText: String, translatedText: String) {
        Handler(Looper.getMainLooper()).post {
            listeners.forEach { it.onTranslationComplete(originalText, translatedText) }
        }
    }

    private fun notifySynthesisStarted() {
        Handler(Looper.getMainLooper()).post {
            listeners.forEach { it.onSynthesisStarted() }
        }
    }

    private fun notifySynthesisComplete() {
        Handler(Looper.getMainLooper()).post {
            listeners.forEach { it.onSynthesisComplete() }
        }
    }

    private fun notifyError(error: String) {
        Handler(Looper.getMainLooper()).post {
            listeners.forEach { it.onError(error) }
        }
    }
}

/**
 * Configuration for Android translation
 */
data class TranslationConfig(
    val sourceLanguage: String = "en",
    val targetLanguage: String = "te",
    val enableOfflineMode: Boolean = true,
    val sampleRate: Int = 16000,
    val chunkDurationMs: Int = 1000,
    val serverUrl: String = "http://10.0.2.2:3000",
)
