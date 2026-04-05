package com.ulttranslator.app

import android.Manifest
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Bundle
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Locale
import java.util.concurrent.TimeUnit

// ── Constants ────────────────────────────────────────────────────────────────

private const val SAMPLE_RATE = 16_000
private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
private const val CHUNK_DURATION_MS = 1_000L
private const val CHUNK_SAMPLES = (SAMPLE_RATE * CHUNK_DURATION_MS / 1000).toInt()
private const val BYTES_PER_SAMPLE = 2

// ── ViewModel ────────────────────────────────────────────────────────────────

class TranslatorViewModel : ViewModel() {

    private val _status = MutableStateFlow("Idle")
    val status: StateFlow<String> = _status

    private val _events = MutableStateFlow<List<SessionEvent>>(emptyList())
    val events: StateFlow<List<SessionEvent>> = _events

    private val _isRunning = MutableStateFlow(false)
    val isRunning: StateFlow<Boolean> = _isRunning

    private val _serverUrl = MutableStateFlow(BuildConfig.ULT_SERVER_URL.ifBlank { "http://10.0.2.2:3000" })
    val serverUrl: StateFlow<String> = _serverUrl

    private val _sourceLanguage = MutableStateFlow("en")
    val sourceLanguage: StateFlow<String> = _sourceLanguage

    private val _targetLanguage = MutableStateFlow("te")
    val targetLanguage: StateFlow<String> = _targetLanguage

    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private var sessionId: String? = null
    private var recordJob: Job? = null
    private var sseJob: Job? = null
    var tts: TextToSpeech? = null

    fun setServerUrl(url: String) { _serverUrl.value = url.trim() }
    fun setSourceLanguage(lang: String) { _sourceLanguage.value = lang }
    fun setTargetLanguage(lang: String) { _targetLanguage.value = lang }

    fun start() {
        if (_isRunning.value) return
        _isRunning.value = true
        _status.value = "Creating session…"
        viewModelScope.launch {
            try {
                val id = createSession()
                sessionId = id
                _status.value = "Session ready — recording"
                sseJob = launch { listenEvents(id) }
                recordJob = launch(Dispatchers.IO) { recordAndUpload(id) }
            } catch (e: Exception) {
                _status.value = "Error: ${e.message}"
                _isRunning.value = false
            }
        }
    }

    fun stop() {
        recordJob?.cancel()
        sseJob?.cancel()
        recordJob = null
        sseJob = null
        val id = sessionId
        sessionId = null
        _isRunning.value = false
        _status.value = "Idle"
        if (id != null) {
            viewModelScope.launch(Dispatchers.IO) {
                runCatching {
                    http.newCall(
                        Request.Builder()
                            .url("${_serverUrl.value}/api/realtime/sessions/$id")
                            .delete()
                            .build()
                    ).execute().close()
                }
            }
        }
    }

    private suspend fun createSession(): String = withContext(Dispatchers.IO) {
        val body = JSONObject().apply {
            put("sourceLanguage", _sourceLanguage.value)
            put("targetLanguage", _targetLanguage.value)
            put("sessionKind", "microphone")
            put("onlinePolicy", "auto")
            put("voiceProfileId", "builtin:alloy")
            put("preserveEmotion", true)
        }.toString()

        val response = http.newCall(
            Request.Builder()
                .url("${_serverUrl.value}/api/realtime/sessions")
                .post(body.toRequestBody("application/json".toMediaType()))
                .build()
        ).execute()

        val json = JSONObject(response.body?.string() ?: "{}")
        response.close()
        if (!response.isSuccessful) throw Exception(json.optString("error", "Session creation failed"))
        json.getString("sessionId")
    }

    private suspend fun recordAndUpload(id: String) = withContext(Dispatchers.IO) {
        val minBuffer = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)
        val bufferSize = maxOf(minBuffer, CHUNK_SAMPLES * BYTES_PER_SAMPLE * 4)
        val recorder = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            SAMPLE_RATE,
            CHANNEL_CONFIG,
            AUDIO_FORMAT,
            bufferSize
        )

        try {
            recorder.startRecording()
            val readBuffer = ByteArray(CHUNK_SAMPLES * BYTES_PER_SAMPLE)
            val accumulator = ByteArrayOutputStream()

            while (isActive) {
                val read = recorder.read(readBuffer, 0, readBuffer.size)
                if (read > 0) {
                    accumulator.write(readBuffer, 0, read)
                    if (accumulator.size() >= CHUNK_SAMPLES * BYTES_PER_SAMPLE) {
                        val pcm = accumulator.toByteArray()
                        accumulator.reset()
                        val wav = buildWav(pcm)
                        runCatching { uploadChunk(id, wav) }
                    }
                }
            }
        } finally {
            recorder.stop()
            recorder.release()
        }
    }

    private fun uploadChunk(id: String, wav: ByteArray) {
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", "chunk.wav", wav.toRequestBody("audio/wav".toMediaType()))
            .build()

        http.newCall(
            Request.Builder()
                .url("${_serverUrl.value}/api/realtime/sessions/$id/chunks")
                .post(body)
                .build()
        ).execute().close()
    }

    private suspend fun listenEvents(id: String) = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("${_serverUrl.value}/api/realtime/sessions/$id/events")
            .build()

        try {
            http.newCall(request).execute().use { response ->
                val source = response.body?.source() ?: return@withContext
                while (isActive) {
                    val line = source.readUtf8Line() ?: break
                    if (line.startsWith("data:")) {
                        val json = runCatching { JSONObject(line.removePrefix("data:").trim()) }.getOrNull() ?: continue
                        handleEvent(json)
                    }
                }
            }
        } catch (_: Exception) {
            // SSE stream closed or cancelled — normal on stop()
        }
    }

    private fun handleEvent(json: JSONObject) {
        val type = json.optString("type")
        when (type) {
            "status" -> _status.value = json.optString("message", "Running")
            "error" -> _status.value = "Error: ${json.optString("message")}"
            "final_translation" -> {
                val translated = json.optString("translatedText")
                if (translated.isNotBlank()) {
                    val event = SessionEvent(
                        type = type,
                        transcript = json.optString("transcript"),
                        translatedText = translated,
                        backend = json.optString("backend"),
                    )
                    _events.value = (listOf(event) + _events.value).take(20)
                    tts?.speak(translated, TextToSpeech.QUEUE_ADD, null, null)
                }
            }
            "snapshot" -> {
                val arr = json.optJSONArray("events") ?: return
                for (i in 0 until arr.length()) {
                    handleEvent(arr.getJSONObject(i))
                }
            }
        }
    }

    override fun onCleared() {
        stop()
        http.dispatcher.executorService.shutdown()
        super.onCleared()
    }
}

// ── WAV builder ──────────────────────────────────────────────────────────────

private fun buildWav(pcm: ByteArray): ByteArray {
    val out = ByteArrayOutputStream()
    val dos = DataOutputStream(out)
    val dataSize = pcm.size
    val totalSize = 36 + dataSize

    fun writeLE32(v: Int) {
        val buf = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(v).array()
        dos.write(buf)
    }
    fun writeLE16(v: Int) {
        val buf = ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN).putShort(v.toShort()).array()
        dos.write(buf)
    }

    dos.writeBytes("RIFF"); writeLE32(totalSize)
    dos.writeBytes("WAVE")
    dos.writeBytes("fmt "); writeLE32(16)
    writeLE16(1); writeLE16(1)
    writeLE32(SAMPLE_RATE); writeLE32(SAMPLE_RATE * BYTES_PER_SAMPLE)
    writeLE16(BYTES_PER_SAMPLE); writeLE16(16)
    dos.writeBytes("data"); writeLE32(dataSize)
    dos.write(pcm)
    dos.flush()
    return out.toByteArray()
}

// ── Activity ─────────────────────────────────────────────────────────────────

class MainActivity : ComponentActivity() {

    private var tts: TextToSpeech? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            val vm: TranslatorViewModel = viewModel()
            LaunchedEffect(Unit) {
                tts = TextToSpeech(this@MainActivity) { status ->
                    if (status == TextToSpeech.SUCCESS) {
                        tts?.language = Locale.getDefault()
                        vm.tts = tts
                    }
                }
            }
            UltAndroidApp(vm)
        }
    }

    override fun onDestroy() {
        tts?.shutdown()
        super.onDestroy()
    }
}

// ── Compose UI ───────────────────────────────────────────────────────────────

@Composable
private fun UltAndroidApp(vm: TranslatorViewModel) {
    val status by vm.status.collectAsState()
    val events by vm.events.collectAsState()
    val isRunning by vm.isRunning.collectAsState()
    val serverUrl by vm.serverUrl.collectAsState()
    val sourceLang by vm.sourceLanguage.collectAsState()
    val targetLang by vm.targetLanguage.collectAsState()

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) vm.start()
    }

    MaterialTheme {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(Brush.verticalGradient(listOf(Color(0xFF07111D), Color(0xFF0C1828))))
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("ULT Android", style = MaterialTheme.typography.headlineMedium, color = Color.White, fontWeight = FontWeight.SemiBold)

            OutlinedTextField(
                value = serverUrl,
                onValueChange = vm::setServerUrl,
                label = { Text("Server URL", color = Color(0xFF94A3B8)) },
                singleLine = true,
                enabled = !isRunning,
                modifier = Modifier.fillMaxWidth(),
            )

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = sourceLang,
                    onValueChange = vm::setSourceLanguage,
                    label = { Text("Source", color = Color(0xFF94A3B8)) },
                    singleLine = true,
                    enabled = !isRunning,
                    modifier = Modifier.weight(1f),
                )
                OutlinedTextField(
                    value = targetLang,
                    onValueChange = vm::setTargetLanguage,
                    label = { Text("Target", color = Color(0xFF94A3B8)) },
                    singleLine = true,
                    enabled = !isRunning,
                    modifier = Modifier.weight(1f),
                )
            }

            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(
                    onClick = {
                        if (isRunning) vm.stop()
                        else permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isRunning) Color(0xFFEF4444) else Color(0xFF67E8F9)
                    ),
                ) {
                    Text(if (isRunning) "Stop" else "Start Mic", color = if (isRunning) Color.White else Color(0xFF0F172A))
                }
            }

            Card {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("Status", fontWeight = FontWeight.Bold, color = Color(0xFF94A3B8))
                    Text(status, color = Color.White)
                }
            }

            LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(events) { event ->
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(event.backend.uppercase().ifBlank { event.type.uppercase() }, fontWeight = FontWeight.Bold, color = Color(0xFF67E8F9))
                            if (event.transcript.isNotBlank()) {
                                Text("Source: ${event.transcript}", color = Color(0xFF94A3B8))
                            }
                            Text(event.translatedText.ifBlank { event.message.ifBlank { "—" } }, color = Color.White)
                        }
                    }
                }
            }
        }
    }
}
