# ULT Translator - User Manual

## Universal Language Translator (ULT)
**Real-time Audio Interception & Translation Engine**

---

## 📖 Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Main Interface](#main-interface)
4. [Audio Configuration](#audio-configuration)
5. [Translation Features](#translation-features)
6. [Voice & TTS Settings](#voice--tts-settings)
7. [Session Management](#session-management)
8. [Advanced Features](#advanced-features)
9. [Troubleshooting](#troubleshooting)
10. [Keyboard Shortcuts](#keyboard-shortcuts)
11. [Technical Specifications](#technical-specifications)
12. [FAQ](#faq)

---

## 🎯 Introduction

ULT Translator is a professional-grade real-time audio translation system that intercepts audio streams, transcribes speech, translates between languages, and synthesizes voice output while preserving the original speaker's characteristics and emotions.

### Key Features
- **Real-time Processing**: Sub-second latency audio translation
- **Voice Preservation**: Maintains speaker identity and emotional tone
- **40+ Languages**: Support for major world languages
- **Multiple Modes**: Offline, online, and hybrid operation
- **Professional Audio**: WASAPI integration with virtual audio routing
- **Cross-platform**: Windows desktop, Android mobile, Web interface

### Use Cases
- **Business Meetings**: Real-time translation for international conferences
- **Education**: Language learning and accessibility support
- **Media Production**: Live subtitling and voice-over translation
- **Personal Communication**: Breaking language barriers in daily interactions

---

## 🚀 Getting Started

### First Launch
1. **Complete Setup**: Run the first-run setup wizard
2. **Configure Languages**: Select source and target languages
3. **Start ULT**: ULT will automatically run in the background.

### Quick Start Guide
1. **Launch ULT**: Double-click desktop shortcut
2. **Background Operation**: ULT automatically intercepts all audio from your mic and system, blocking original playback and routing translated audio instantly.

---

## 🖥️ Main Interface

### Dashboard Overview
```
┌─────────────────────────────────────────────────────────┐
│ ULT TRANSLATOR v1.0.0               [Settings] [Help]   │
├─────────────────────────────────────────────────────────┤
│ ┌─ System Status ───┐ ┌─ Audio Status ─┐ ┌─ Statistics ─┐ │
│ │ 🟢 ALWAYS ON      │ │ Input: Active  │ │ Latency: 280ms│ │
│ │ 🛡️ Intercepting   │ │ Output: Active │ │ CPU: 35%      │ │
│ │ 🎙️ Mic: Active    │ │ Virtual Cable: │ │ RAM: 2.1GB    │ │
│ │ 🔊 Spk: Active    │ │ ✓ Connected    │ │              │ │
│ └───────────────────┘ └────────────────┘ └───────────────┘ │
├─────────────────────────────────────────────────────────┤
│ ┌─ Live Transcription ──────────────────────────────┐ │
│ │ Source: Hello, how are you today?                │ │
│ │ Target: Hola, ¿cómo estás hoy?                    │ │
│ │ Confidence: 98%  Latency: 280ms                   │ │
│ └───────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────┤
│ ┌─ Voice Activity ─┐ ┌─ Language Display ─┐ ┌─ Controls ─┐ │
│ │ 🎤 Speaking      │ │ EN → ES           │ │ 🔇 Mute     │ │
│ │ 📊 Waveform      │ │ Neural Translation│ │ 🔄 Switch   │ │
│ │ 🎵 Audio Levels  │ │ Voice Preservation│ │ ⚙️ Settings │ │
│ └──────────────────┘ └───────────────────┘ └─────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Interface Elements

#### System Status Panel
- **Always ON**: ULT operates automatically in the background as a system-level interceptor. There are no manual start/stop buttons.
- **Dual Path Operation**: Intercepts microphone and speaker simultaneously.

#### Audio Status Panel
- **Input Status**: Microphone/system audio activity
- **Output Status**: Speaker/synthesis device status
- **Virtual Cable**: VB-Audio connection status
- **Buffer Levels**: Audio processing queue status

#### Statistics Panel
- **Performance Metrics**: Latency, CPU, memory usage
- **Session Data**: Translation count, duration, accuracy
- **System Health**: Resource utilization indicators

#### Live Display Area
- **Source Text**: Real-time transcription
- **Target Text**: Live translation output
- **Quality Indicators**: Confidence scores and processing time
- **Voice Visualization**: Audio waveform and activity

---

## 🎵 Audio Configuration

### Input Sources

#### Microphone Mode
- **Direct Capture**: Real-time microphone input
- **Speech Extraction**: Separate voice from noise/music automatically
- **AGC (Auto Gain Control)**: Automatic volume leveling

#### Speaker/System Audio Mode
- **Virtual Audio Driver**: VB-Cable integration required
- **System-wide Capture**: All system audio interception
- **Multi-channel Support**: Stereo and surround sound
- **Original Audio Blocking**: No leakage of original sound

#### File Input Mode
- **Supported Formats**: WAV, MP3, M4A, FLAC
- **Batch Processing**: Multiple files in queue
- **Real-time Preview**: Live processing simulation
- **Export Options**: Save translated audio

### Output Configuration

#### Audio Routing
- **Primary Output**: Main speaker device
- **Secondary Output**: Additional monitoring device
- **Virtual Channels**: Separate source/target audio streams
- **Latency Matching**: Synchronize audio/video output

#### Voice Synthesis
- **TTS Engine**: Coqui TTS / RVC integration
- **Voice Cloning**: Reconstructs exact speaker identity automatically
- **Emotion Transfer**: Maintain emotional tone and emphasis
- **Prosody Transfer**: Matches pitch, tone, and accent feel

---

## 🌐 Translation Features

### Language Support

#### Supported Languages
- **Speech-to-Text**: 40+ languages via Whisper AI
- **Translation**: 40+ language pairs via Argos Translate
- **Real-time Switching**: Change languages mid-session
- **Dialect Support**: Regional language variations

#### Language Pairs
```
English ↔ Spanish, French, German, Italian, Portuguese
English ↔ Chinese, Japanese, Korean, Arabic, Hindi
English ↔ Russian, Dutch, Polish, Turkish, Swedish
And many more combinations...
```

### Translation Modes
ULT operates strictly via **Local Offline AI Models** to ensure zero latency constraints and absolute privacy. 

### Quality Settings

#### Accuracy vs Speed
- **High Accuracy**: Whisper Small/Medium models (slower)
- **Balanced**: Whisper Base model (recommended)
- **Fast**: Whisper Tiny model (lower accuracy)

#### Audio Processing
- **Processing Pipeline**: TensorRT/ONNX optimized C++ audio daemon
- **Latency Target**: Sub-300ms execution

---

## 🎤 Voice & TTS Settings

### TTS Engine Options

#### XTTS v2 (Recommended)
- **Neural Voice Cloning**: Preserves speaker identity
- **Emotion Transfer**: Maintains emotional expression
- **Multi-language**: 17 languages supported
- **High Quality**: Professional-grade synthesis

#### ElevenLabs
- **Premium Voices**: 1000+ professional voice actors
- **API Integration**: Requires API key
- **Advanced Features**: Voice design and customization
- **Cloud Processing**: Server-based synthesis

#### PyTTSx3 (Fallback)
- **Local TTS**: No internet required
- **System Voices**: Uses Windows TTS engines
- **Basic Quality**: Functional but less natural
- **Always Available**: No external dependencies

### Voice Preservation

#### Speaker Characteristics
- **Gender Recognition**: Maintains male/female voice qualities
- **Age Estimation**: Preserves apparent age characteristics
- **Accent Transfer**: Retains regional speech patterns
- **Speaking Style**: Maintains pace and rhythm

#### Emotional Analysis
- **Emotion Detection**: Identifies happiness, anger, sadness, etc.
- **Intensity Mapping**: Preserves emotional strength
- **Context Awareness**: Adjusts translation based on emotional context
- **Cultural Adaptation**: Appropriate emotional expression in target language

---

## 📊 Session Management

### Session Types

#### Real-time Sessions
- **Live Translation**: Continuous audio processing
- **Interactive Mode**: Speaker change detection
- **Quality Monitoring**: Real-time performance metrics
- **Recording Options**: Save session audio/text

#### Batch Processing
- **File Translation**: Process pre-recorded audio
- **Queue Management**: Multiple files in sequence
- **Progress Tracking**: Visual processing status
- **Export Formats**: Multiple output options

#### Meeting Mode
- **Multi-speaker**: Automatic speaker identification
- **Meeting Summary**: Generate session transcripts
- **Participant Tracking**: Speaker attribution
- **Time Stamping**: Precise timing for all utterances

### Session Controls

#### Recording & Playback
- **Session Recording**: Save all audio and translations
- **Playback Control**: Review previous sessions
- **Export Options**: Save as text, audio, or video
- **Sharing**: Export session data for collaboration

#### Quality Monitoring
- **Latency Tracking**: Real-time delay measurements
- **Accuracy Metrics**: Translation confidence scores
- **Audio Quality**: Signal-to-noise ratio monitoring
- **Performance Logs**: Detailed session analytics

---

## ⚡ Advanced Features

### Audio Routing & Processing

#### Virtual Audio Cables
- **VB-Audio Integration**: Professional audio routing
- **Multi-channel Support**: Separate input/output streams
- **Application-specific**: Route individual app audio
- **System Integration**: Windows audio session management

#### WASAPI Integration
- **Low-latency Processing**: Direct hardware access
- **Exclusive Mode**: Bypass Windows audio mixing
- **High-fidelity**: Uncompressed audio processing
- **Professional Quality**: Studio-grade audio handling

### AI Model Management

#### Model Selection
- **Dynamic Loading**: Switch models based on needs
- **Memory Management**: Efficient GPU/CPU utilization
- **Model Updates**: Automatic model version checking
- **Custom Models**: Support for fine-tuned models

#### Performance Optimization
- **GPU Acceleration**: CUDA support for faster processing
- **CPU Optimization**: Multi-threaded processing
- **Memory Pooling**: Efficient resource utilization
- **Caching**: Model and data caching for speed

### Network & API Features

#### API Integration
- **RESTful API**: Programmatic access to all features
- **WebSocket Support**: Real-time streaming
- **Authentication**: Secure API key management
- **Rate Limiting**: Configurable usage limits

#### Cloud Services
- **OpenAI Integration**: GPT models for enhanced translation
- **ElevenLabs TTS**: Premium voice synthesis
- **Model Hosting**: Cloud-based model serving
- **Backup Processing**: Failover to cloud services

---

## 🔧 Troubleshooting

### Audio Issues

#### No Audio Input
- **Check**: Microphone permissions in Windows
- **Verify**: Audio device is not muted
- **Test**: Audio settings in Windows Sound control panel
- **Update**: Audio drivers to latest version

#### Poor Audio Quality
- **Adjust**: Microphone sensitivity settings
- **Check**: Background noise levels
- **Configure**: Audio enhancement options
- **Test**: Different audio devices

#### Virtual Cable Problems
- **Install**: VB-Audio Virtual Cable correctly
- **Configure**: Windows audio routing
- **Restart**: ULT Translator after cable setup
- **Verify**: Cable shows in audio devices list

### Translation Issues

#### Low Accuracy
- **Switch**: To more accurate STT model
- **Check**: Audio quality and clarity
- **Adjust**: Language detection settings
- **Verify**: Correct language selection

#### High Latency
- **Reduce**: Audio chunk size
- **Switch**: To faster model (Tiny/Base)
- **Check**: System resource usage
- **Optimize**: GPU/CPU utilization

#### Language Detection
- **Manual**: Override automatic language detection
- **Check**: Clear speech pronunciation
- **Adjust**: Detection sensitivity
- **Verify**: Supported language pair

### Performance Issues

#### High CPU Usage
- **Switch**: To CPU-optimized models
- **Reduce**: Processing quality settings
- **Close**: Other resource-intensive applications
- **Update**: System drivers and firmware

#### Memory Problems
- **Reduce**: Model size (Tiny/Base)
- **Close**: Other memory-intensive apps
- **Increase**: Virtual memory/page file
- **Monitor**: Memory usage in Task Manager

#### GPU Issues
- **Update**: GPU drivers to latest version
- **Check**: CUDA compatibility
- **Switch**: To CPU processing if needed
- **Monitor**: GPU temperature and usage

---

## ⌨️ Keyboard Shortcuts

### Global Shortcuts
- **F1**: Show help/documentation
- **F5**: Refresh audio devices
- **F10**: Open settings panel
- **F11**: Toggle fullscreen mode
- **F12**: Emergency stop all processing

### Session Control
- **Space**: Start/stop translation session
- **M**: Toggle microphone mode
- **S**: Toggle speaker mode
- **R**: Start/stop recording
- **P**: Pause/resume processing

### Audio Control
- **↑/↓**: Volume up/down
- **←/→**: Previous/next audio device
- **Mute**: Toggle audio mute
- **Ctrl+M**: Toggle microphone mute
- **Ctrl+S**: Toggle speaker mute

### Language Control
- **L**: Cycle through source languages
- **Shift+L**: Cycle through target languages
- **Ctrl+L**: Open language selection dialog
- **Alt+L**: Toggle language auto-detection

### Advanced Controls
- **Ctrl+R**: Restart audio processing
- **Ctrl+T**: Test audio devices
- **Ctrl+D**: Show debug information
- **Ctrl+E**: Export current session
- **Ctrl+Q**: Quick settings menu

---

## 📋 Technical Specifications

### System Requirements
- **OS**: Windows 10/11 (64-bit)
- **CPU**: 4+ cores, AVX2 support
- **RAM**: 8GB minimum, 16GB recommended
- **GPU**: NVIDIA GTX 1060 or equivalent (optional)
- **Storage**: 20GB SSD space
- **Audio**: WASAPI-compatible device

### Performance Metrics
- **Latency**: 200-2000ms (configurable)
- **Accuracy**: 90-98% (model dependent)
- **CPU Usage**: 20-80% (model dependent)
- **Memory Usage**: 1-4GB active processing
- **GPU Memory**: 2-8GB for CUDA acceleration

### Audio Specifications
- **Sample Rates**: 16kHz, 44.1kHz, 48kHz
- **Bit Depth**: 16-bit, 24-bit
- **Channels**: Mono, Stereo
- **Formats**: WAV, MP3, M4A, FLAC
- **Latency**: <50ms audio processing

### AI Models
- **Whisper**: tiny, base, small, medium, large
- **Argos Translate**: 1000+ language pairs
- **XTTS v2**: 17 languages, voice cloning
- **ElevenLabs**: 1000+ voices, 29 languages

---

## ❓ FAQ

### General Questions

**Q: Is ULT Translator free?**
A: ULT Translator is open-source software released under MIT license. Basic features are free, premium cloud features may require API keys.

**Q: Does it work offline?**
A: Yes, ULT operates completely offline by default. Online features are optional and require explicit configuration.

**Q: What languages are supported?**
A: 40+ languages for speech recognition and translation, with neural voice synthesis in 17+ languages.

**Q: How accurate is the translation?**
A: Accuracy ranges from 90-98% depending on audio quality, language pair, and model selection.

### Technical Questions

**Q: Can I use it on multiple computers?**
A: Yes, ULT can be installed on multiple Windows computers. Each installation is independent.

**Q: Does it support virtual machines?**
A: Yes, but audio passthrough must be configured properly. Physical audio devices are recommended for best performance.

**Q: Can I integrate ULT into other applications?**
A: Yes, ULT provides REST API and WebSocket interfaces for integration with other software.

**Q: How do I backup my settings?**
A: Settings are stored in `config/user-config.json`. Voice profiles are in `models/voice-profiles/`.

### Audio Questions

**Q: Why do I need VB-Audio Virtual Cable?**
A: VB-Cable enables system-wide audio interception, allowing ULT to translate audio from any application.

**Q: Can I use multiple microphones?**
A: Yes, ULT supports multiple audio input devices. Configure routing in the audio settings panel.

**Q: Does it work with Bluetooth headsets?**
A: Yes, Bluetooth audio devices are supported, though wired headsets provide lower latency.

**Q: Can I translate video call audio?**
A: Yes, by routing video call application audio through VB-Cable virtual device.

### Performance Questions

**Q: Why is translation slow on my computer?**
A: Try using smaller AI models (Tiny/Base), ensure sufficient RAM, or switch to CPU-only processing.

**Q: Can I use ULT on older computers?**
A: Minimum 8GB RAM required. Use Tiny model and disable voice preservation for older systems.

**Q: Does it support GPU acceleration?**
A: Yes, NVIDIA GPUs with CUDA support provide significant performance improvements.

**Q: How much bandwidth does online mode use?**
A: Online mode uses minimal bandwidth (text-only for most features). Audio upload is optional.

### Privacy Questions

**Q: Is my audio data sent to servers?**
A: No, by default. Online features require explicit opt-in and API key configuration.

**Q: How is voice data protected?**
A: Voice profiles are encrypted locally. No audio data leaves your computer without explicit permission.

**Q: Can I delete all stored data?**
A: Yes, run the uninstaller or manually delete the database and configuration files.

**Q: Does ULT collect usage data?**
A: Anonymous usage analytics are optional and can be disabled in privacy settings.

---

## 📞 Support & Resources

### Getting Help
- **Documentation**: This user manual and SETUP.md
- **GitHub Issues**: Bug reports and feature requests
- **Community**: Discussion forums and user groups
- **Email**: Direct support for enterprise users

### System Information
For support requests, include:
- ULT version and installation date
- Windows version and hardware specs
- Audio device configuration
- Error messages and log files

### Updates & Maintenance
- **Automatic Updates**: Check for updates in settings
- **Manual Downloads**: GitHub releases page
- **Changelog**: Release notes for each version
- **Backup**: Important data before major updates

---

*ULT Translator - Making global communication seamless and natural*

---

## 📄 License & Acknowledgments

**License**: MIT License - See LICENSE file for full terms.

**Credits**:
- OpenAI Whisper for speech recognition
- Argos Translate for neural machine translation
- Coqui.ai XTTS v2 for voice synthesis
- VB-Audio for virtual audio routing
- Electron for cross-platform desktop framework

**Privacy**: ULT respects user privacy with local processing by default and optional cloud features.