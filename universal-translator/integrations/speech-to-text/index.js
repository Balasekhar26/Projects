/**
 * Speech-to-Text Integration for ULT Translator
 * Real-time voice input and translation capabilities
 */

const express = require('express');
const axios = require('axios');
const multer = require('multer');
const record = require('node-record-lpcm16');
const ffmpeg = require('fluent-ffmpeg');
const ffmpegPath = require('ffmpeg-static');
const winston = require('winston');
const cron = require('node-cron');
const { Server } = require('socket.io');
const http = require('http');
require('dotenv').config();

// Set FFmpeg path
ffmpeg.setFfmpegPath(ffmpegPath);

// Configure logging
const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.File({ filename: 'logs/speech-to-text.log' }),
    new winston.transports.Console()
  ]
});

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"]
  }
});

app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Configure multer for audio file uploads
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 50 * 1024 * 1024, // 50MB limit
  },
  fileFilter: (req, file, cb) => {
    const allowedTypes = [
      'audio/wav',
      'audio/mp3',
      'audio/mpeg',
      'audio/ogg',
      'audio/m4a',
      'audio/flac'
    ];
    
    if (allowedTypes.includes(file.mimetype)) {
      cb(null, true);
    } else {
      cb(new Error('Only audio files are allowed'), false);
    }
  }
});

// ULT Translator API configuration
const ULT_API_BASE = process.env.ULT_API_URL || 'http://localhost:3000/api';
const SPEECH_API_KEY = process.env.SPEECH_API_KEY || '';

/**
 * Speech-to-Text Processing Class
 */
class SpeechToTextProcessor {
  
  // Process audio file for speech recognition
  static async processAudio(audioBuffer, options = {}) {
    try {
      logger.info('Processing audio for speech recognition');
      
      // Convert audio to WAV format if needed
      const processedAudio = await this.convertToWav(audioBuffer, options.inputFormat);
      
      // Perform speech recognition
      const transcription = await this.performSpeechRecognition(processedAudio);
      
      return {
        text: transcription.text,
        confidence: transcription.confidence,
        duration: transcription.duration,
        language: options.language || 'auto'
      };
    } catch (error) {
      logger.error('Audio processing failed:', error);
      throw error;
    }
  }
  
  // Convert audio to WAV format
  static async convertToWav(audioBuffer, inputFormat = 'wav') {
    return new Promise((resolve, reject) => {
      if (inputFormat === 'wav') {
        resolve(audioBuffer);
        return;
      }
      
      // Create temporary file
      const tempInput = `temp_input.${inputFormat}`;
      const tempOutput = 'temp_output.wav';
      
      // Write input buffer to file
      require('fs').writeFileSync(tempInput, audioBuffer);
      
      // Convert using FFmpeg
      ffmpeg(tempInput)
        .toFormat('wav')
        .audioCodec('pcm_s16le')
        .audioFrequency(16000)
        .audioChannels(1)
        .on('end', () => {
          // Read converted file
          const convertedBuffer = require('fs').readFileSync(tempOutput);
          
          // Clean up temp files
          require('fs').unlinkSync(tempInput);
          require('fs').unlinkSync(tempOutput);
          
          resolve(convertedBuffer);
        })
        .on('error', (error) => {
          reject(error);
        })
        .save(tempOutput);
    });
  }
  
  // Perform speech recognition (simulated - would integrate with real service)
  static async performSpeechRecognition(audioBuffer) {
    try {
      // In a real implementation, this would call services like:
      // - Google Speech-to-Text API
      // - Azure Speech Services
      // - AWS Transcribe
      // - OpenAI Whisper API
      
      // For demonstration, we'll simulate the response
      logger.info('Performing speech recognition');
      
      // Simulate processing delay
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Simulated transcription result
      return {
        text: "Hello, this is a sample speech recognition result.",
        confidence: 0.92,
        duration: 3.5,
        words: [
          { word: "Hello", start: 0.0, end: 0.5, confidence: 0.95 },
          { word: "this", start: 0.6, end: 0.9, confidence: 0.90 },
          { word: "is", start: 1.0, end: 1.2, confidence: 0.93 },
          { word: "a", start: 1.3, end: 1.4, confidence: 0.88 },
          { word: "sample", start: 1.5, end: 2.0, confidence: 0.94 },
          { word: "speech", start: 2.1, end: 2.6, confidence: 0.91 },
          { word: "recognition", start: 2.7, end: 3.3, confidence: 0.89 },
          { word: "result", start: 3.4, end: 3.8, confidence: 0.92 }
        ]
      };
    } catch (error) {
      logger.error('Speech recognition failed:', error);
      throw error;
    }
  }
  
  // Real-time speech recognition stream
  static async startRealTimeRecognition(socketId) {
    try {
      logger.info(`Starting real-time speech recognition for socket: ${socketId}`);
      
      // Start recording from microphone
      const recording = record.record({
        sampleRateHertz: 16000,
        threshold: 0,
        verbose: false,
        recordProgram: 'sox',
        silence: '1.0',
        channels: 1
      });
      
      let audioChunks = [];
      
      recording.stream().on('data', (chunk) => {
        audioChunks.push(chunk);
        
        // Process chunks in real-time
        if (audioChunks.length >= 10) {
          const audioBuffer = Buffer.concat(audioChunks);
          audioChunks = [];
          
          this.processRealTimeChunk(audioBuffer, socketId);
        }
      });
      
      recording.stream().on('error', (error) => {
        logger.error(`Recording error for socket ${socketId}:`, error);
        io.to(socketId).emit('speech-error', { error: error.message });
      });
      
      return recording;
    } catch (error) {
      logger.error('Real-time recognition setup failed:', error);
      throw error;
    }
  }
  
  // Process real-time audio chunk
  static async processRealTimeChunk(audioChunk, socketId) {
    try {
      // Process chunk for speech recognition
      const result = await this.performSpeechRecognition(audioChunk);
      
      // Send result to client
      io.to(socketId).emit('speech-result', {
        text: result.text,
        confidence: result.confidence,
        isFinal: false,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      logger.error(`Real-time processing failed for socket ${socketId}:`, error);
    }
  }
  
  // Stop real-time recognition
  static stopRealTimeRecognition(recording) {
    try {
      if (recording) {
        recording.stop();
      }
    } catch (error) {
      logger.error('Failed to stop real-time recognition:', error);
    }
  }
}

/**
 * Voice Translation Workflow
 */
class VoiceTranslationWorkflow {
  
  // Process voice input and translate
  static async processVoiceTranslation(audioBuffer, sourceLang, targetLang, options = {}) {
    try {
      logger.info(`Processing voice translation: ${sourceLang} -> ${targetLang}`);
      
      // Step 1: Speech-to-text
      const speechResult = await SpeechToTextProcessor.processAudio(audioBuffer, {
        language: sourceLang,
        inputFormat: options.inputFormat
      });
      
      // Step 2: Translate text
      const translationResponse = await axios.post(`${ULT_API_BASE}/translate`, {
        text: speechResult.text,
        sourceLanguage: sourceLang,
        targetLanguage: targetLang,
        provider: options.translationProvider || 'nvidia'
      });
      
      const translation = translationResponse.data;
      
      // Step 3: Text-to-speech (if requested)
      let audioTranslation = null;
      if (options.generateAudio) {
        audioTranslation = await this.generateSpeechFromText(
          translation.translatedText,
          targetLang
        );
      }
      
      // Store translation in ULT system
      await axios.post(`${ULT_API_BASE}/translations/store`, {
        originalText: speechResult.text,
        translatedText: translation.translatedText,
        sourceLanguage: sourceLang,
        targetLanguage: targetLang,
        audioOriginal: audioBuffer,
        audioTranslated: audioTranslation,
        confidence: speechResult.confidence,
        translationConfidence: translation.confidence,
        type: 'voice_translation'
      });
      
      return {
        originalText: speechResult.text,
        translatedText: translation.translatedText,
        originalAudio: audioBuffer,
        translatedAudio: audioTranslation,
        confidence: speechResult.confidence,
        translationConfidence: translation.confidence,
        sourceLanguage: sourceLang,
        targetLanguage: targetLang
      };
    } catch (error) {
      logger.error('Voice translation workflow failed:', error);
      throw error;
    }
  }
  
  // Generate speech from text (text-to-speech)
  static async generateSpeechFromText(text, language) {
    try {
      logger.info(`Generating speech for text in ${language}`);
      
      // In a real implementation, this would call TTS services like:
      // - Google Text-to-Speech API
      // - Azure Speech Services
      // - AWS Polly
      // - ElevenLabs API
      
      // For demonstration, return a placeholder
      return Buffer.from('simulated-audio-data');
    } catch (error) {
      logger.error('Text-to-speech generation failed:', error);
      throw error;
    }
  }
  
  // Batch voice translation
  static async processBatchVoiceTranslation(audioFiles, sourceLang, targetLang) {
    try {
      logger.info(`Processing batch voice translation: ${audioFiles.length} files`);
      
      const results = [];
      
      for (const audioFile of audioFiles) {
        try {
          const result = await this.processVoiceTranslation(
            audioFile.buffer,
            sourceLang,
            targetLang,
            {
              inputFormat: audioFile.mimetype.replace('audio/', ''),
              generateAudio: true
            }
          );
          
          results.push({
            filename: audioFile.originalname,
            result: result
          });
        } catch (error) {
          results.push({
            filename: audioFile.originalname,
            error: error.message
          });
        }
      }
      
      return results;
    } catch (error) {
      logger.error('Batch voice translation failed:', error);
      throw error;
    }
  }
}

/**
 * API Routes
 */

// Upload and translate audio file
app.post('/translate-voice', upload.single('audio'), async (req, res) => {
  const { sourceLang, targetLang, options } = req.body;
  
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No audio file provided' });
    }
    
    const result = await VoiceTranslationWorkflow.processVoiceTranslation(
      req.file.buffer,
      sourceLang,
      targetLang,
      options || {}
    );
    
    res.json({
      translation: result,
      audioInfo: {
        name: req.file.originalname,
        size: req.file.size,
        type: req.file.mimetype
      }
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Batch voice translation
app.post('/batch-translate-voice', upload.array('audios', 10), async (req, res) => {
  const { sourceLang, targetLang } = req.body;
  
  try {
    if (!req.files || req.files.length === 0) {
      return res.status(400).json({ error: 'No audio files provided' });
    }
    
    const results = await VoiceTranslationWorkflow.processBatchVoiceTranslation(
      req.files,
      sourceLang,
      targetLang
    );
    
    res.json({ results: results });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Real-time speech recognition and translation
app.post('/real-time-translate', async (req, res) => {
  const { sourceLang, targetLang } = req.body;
  
  try {
    // This would set up WebSocket connection for real-time processing
    res.json({
      message: 'Real-time translation endpoint ready',
      instructions: 'Connect to WebSocket endpoint for real-time processing',
      websocketUrl: '/socket.io',
      sourceLang: sourceLang,
      targetLang: targetLang
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get supported languages
app.get('/supported-languages', async (req, res) => {
  try {
    const response = await axios.get(`${ULT_API_BASE}/languages/supported`);
    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

/**
 * WebSocket Handlers
 */
io.on('connection', (socket) => {
  logger.info(`Client connected: ${socket.id}`);
  
  // Start real-time speech recognition
  socket.on('start-speech', async (data) => {
    try {
      const { sourceLang, targetLang } = data;
      
      // Start recording
      const recording = await SpeechToTextProcessor.startRealTimeRecognition(socket.id);
      
      socket.recording = recording;
      socket.sourceLang = sourceLang;
      socket.targetLang = targetLang;
      
      socket.emit('speech-started', {
        message: 'Speech recognition started',
        sourceLang: sourceLang,
        targetLang: targetLang
      });
    } catch (error) {
      socket.emit('speech-error', { error: error.message });
    }
  });
  
  // Stop real-time speech recognition
  socket.on('stop-speech', async () => {
    try {
      if (socket.recording) {
        SpeechToTextProcessor.stopRealTimeRecognition(socket.recording);
        socket.recording = null;
      }
      
      socket.emit('speech-stopped', {
        message: 'Speech recognition stopped'
      });
    } catch (error) {
      socket.emit('speech-error', { error: error.message });
    }
  });
  
  // Handle disconnection
  socket.on('disconnect', () => {
    logger.info(`Client disconnected: ${socket.id}`);
    
    if (socket.recording) {
      SpeechToTextProcessor.stopRealTimeRecognition(socket.recording);
    }
  });
});

/**
 * Scheduled Tasks
 */

// Daily voice translation cleanup (at 2 AM)
cron.schedule('0 2 * * *', async () => {
  try {
    logger.info('Starting daily voice translation cleanup');
    
    // Clean up old temporary audio files
    // Archive old voice translations
    // Update usage statistics
    
    logger.info('Daily voice translation cleanup completed');
  } catch (error) {
    logger.error('Daily voice translation cleanup failed:', error);
  }
});

/**
 * Health Check
 */
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'ULT Translator Speech-to-Text Integration',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    connectedClients: io.engine.clientsCount
  });
});

/**
 * Start Server
 */
const PORT = process.env.PORT || 3014;
server.listen(PORT, () => {
  logger.info(`ULT Translator Speech-to-Text Integration running on port ${PORT}`);
  logger.info('Available endpoints:');
  logger.info('- POST /translate-voice - Translate audio file');
  logger.info('- POST /batch-translate-voice - Batch voice translation');
  logger.info('- POST /real-time-translate - Real-time translation setup');
  logger.info('- GET /supported-languages - Get supported languages');
  logger.info('- WebSocket /socket.io - Real-time speech recognition');
  logger.info('- GET /health - Health check');
});

module.exports = {
  SpeechToTextProcessor,
  VoiceTranslationWorkflow,
  app,
  io
};
