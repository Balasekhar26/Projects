package com.ulttranslator.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import androidx.annotation.RequiresApi
import androidx.lifecycle.LifecycleService
import kotlinx.coroutines.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.ByteArrayOutputStream
import java.util.concurrent.TimeUnit

/**
 * Foreground service that captures system playback audio via MediaProjection
 * (Android 10+ / API 29+) and uploads WAV chunks to the ULT session API.
 *
 * Start with:
 *   Intent(context, AudioProjectionService::class.java).also {
 *       it.putExtra(EXTRA_SESSION_ID, sessionId)
 *       it.putExtra(EXTRA_SERVER_URL, serverUrl)
 *       it.putExtra(EXTRA_TARGET_LANGUAGE, targetLanguage)
 *       it.putExtra(EXTRA_RESULT_CODE, resultCode)
 *       it.putExtra(EXTRA_RESULT_DATA, resultData)
 *       startForegroundService(it)
 *   }
 */
class AudioProjectionService : LifecycleService() {

    companion object {
        const val EXTRA_SESSION_ID = "session_id"
        const val EXTRA_SERVER_URL = "server_url"
        const val EXTRA_TARGET_LANGUAGE = "target_language"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"

        private const val CHANNEL_ID = "ult_capture"
        private const val NOTIF_ID = 1001
        private const val SAMPLE_RATE = 16_000
        private const val CHUNK_DURATION_MS = 1_000L
        private const val CHUNK_SAMPLES = (SAMPLE_RATE * CHUNK_DURATION_MS / 1000).toInt()
        private const val BYTES_PER_SAMPLE = 2
    }

    private var mediaProjection: MediaProjection? = null
    private var captureJob: Job? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    override fun onCreate() {
        super.onCreate()
        ensureNotificationChannel()
        startForeground(NOTIF_ID, buildNotification())
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)

        val sessionId = intent?.getStringExtra(EXTRA_SESSION_ID) ?: return START_NOT_STICKY
        val serverUrl = intent.getStringExtra(EXTRA_SERVER_URL) ?: return START_NOT_STICKY
        val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, -1)
        @Suppress("DEPRECATION")
        val resultData = intent.getParcelableExtra<Intent>(EXTRA_RESULT_DATA) ?: return START_NOT_STICKY

        val projectionManager = getSystemService(MediaProjectionManager::class.java)
        mediaProjection = projectionManager.getMediaProjection(resultCode, resultData)

        captureJob = scope.launch {
            runCatching { captureAndUpload(sessionId, serverUrl) }
        }

        return START_STICKY
    }

    override fun onBind(intent: Intent): IBinder? = super.onBind(intent)

    override fun onDestroy() {
        captureJob?.cancel()
        mediaProjection?.stop()
        mediaProjection = null
        scope.cancel()
        http.dispatcher.executorService.shutdown()
        super.onDestroy()
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    private suspend fun captureAndUpload(sessionId: String, serverUrl: String) {
        val projection = mediaProjection ?: return

        val captureConfig = AudioPlaybackCaptureConfiguration.Builder(projection)
            .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
            .addMatchingUsage(AudioAttributes.USAGE_GAME)
            .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
            .build()

        val audioFormat = AudioFormat.Builder()
            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
            .setSampleRate(SAMPLE_RATE)
            .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
            .build()

        val minBuffer = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        val bufferSize = maxOf(minBuffer, CHUNK_SAMPLES * BYTES_PER_SAMPLE * 4)

        val recorder = AudioRecord.Builder()
            .setAudioPlaybackCaptureConfig(captureConfig)
            .setAudioFormat(audioFormat)
            .setBufferSizeInBytes(bufferSize)
            .build()

        try {
            recorder.startRecording()
            val readBuffer = ByteArray(CHUNK_SAMPLES * BYTES_PER_SAMPLE)
            val accumulator = ByteArrayOutputStream()

            while (currentCoroutineContext().isActive) {
                val read = recorder.read(readBuffer, 0, readBuffer.size)
                if (read > 0) {
                    accumulator.write(readBuffer, 0, read)
                    if (accumulator.size() >= CHUNK_SAMPLES * BYTES_PER_SAMPLE) {
                        val pcm = accumulator.toByteArray()
                        accumulator.reset()
                        runCatching { uploadChunk(sessionId, serverUrl, buildWav(pcm)) }
                    }
                }
            }
        } finally {
            recorder.stop()
            recorder.release()
        }
    }

    private fun uploadChunk(sessionId: String, serverUrl: String, wav: ByteArray) {
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", "chunk.wav", wav.toRequestBody("audio/wav".toMediaType()))
            .build()

        http.newCall(
            Request.Builder()
                .url("$serverUrl/api/realtime/sessions/$sessionId/chunks")
                .post(body)
                .build()
        ).execute().close()
    }

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(CHANNEL_ID, "ULT Capture", NotificationManager.IMPORTANCE_LOW)
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("ULT — System audio capture active")
                .setContentText("Translating system playback audio in real time.")
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification()
        }
    }
}

// ── WAV builder (duplicated here so the service is self-contained) ────────────

private fun buildWav(pcm: ByteArray): ByteArray {
    val out = ByteArrayOutputStream()
    fun writeLE32(v: Int) = out.write(byteArrayOf(v.toByte(), (v shr 8).toByte(), (v shr 16).toByte(), (v shr 24).toByte()))
    fun writeLE16(v: Int) = out.write(byteArrayOf(v.toByte(), (v shr 8).toByte()))
    fun writeStr(s: String) = out.write(s.toByteArray(Charsets.US_ASCII))

    writeStr("RIFF"); writeLE32(36 + pcm.size)
    writeStr("WAVE")
    writeStr("fmt "); writeLE32(16)
    writeLE16(1); writeLE16(1)
    writeLE32(16_000); writeLE32(16_000 * 2)
    writeLE16(2); writeLE16(16)
    writeStr("data"); writeLE32(pcm.size)
    out.write(pcm)
    return out.toByteArray()
}
