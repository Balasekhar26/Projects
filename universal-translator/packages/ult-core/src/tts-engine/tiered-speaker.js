const { EventEmitter } = require("events");
const fs = require("fs/promises");
const fsSync = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { Pyttsx3Speaker } = require("./pyttsx3-speaker");
const { EdgeTtsSpeaker } = require("./edge-tts-speaker");
const { OpenAiWindowsSpeaker } = require("./openai-speaker");
const { ElevenLabsSpeaker } = require("./elevenlabs-speaker");
const { XttsVoiceCloneEngine } = require("../voice-clone/xtts");
const { isConsentedLocalVoiceProfile } = require("../voice-clone/registry");
const { resolveCoreConfig } = require("../config");
const { ProsodyEngine } = require("../prosody/engine");
const { writePcmAsWavFile } = require("../../../../src/utils/wav");

class TieredSpeechEngine extends EventEmitter {
  constructor(config = {}) {
    super();
    this.config = resolveCoreConfig(config);
    this.xtts = new XttsVoiceCloneEngine(this.config);
    this.edge = new EdgeTtsSpeaker(this.config);
    this.sapi = new Pyttsx3Speaker(this.config);
    this.openai = new OpenAiWindowsSpeaker(this.config);
    this.elevenlabs = new ElevenLabsSpeaker(this.config);
    this.prosodyEngine = new ProsodyEngine(this.config);
    this.voiceSamplePath = "";
    this.startupFadeInPending = true;
    this.lastContinuationPath = "";
    this.audioStreams = new Map();
    this.lastAudioWriteAt = 0;
    this.currentSpeechPlayback = null;
    this.presenceState = {
      active: false,
      timer: null,
      outputDeviceName: "",
      writeInFlight: false,
      chunkIndex: 0,
      chunks: [],
    };

    this.edge.on("debug", (message) => this.emit("debug", message));
    this.sapi.on("debug", (message) => this.emit("debug", message));
  }

  setVoiceSample(wavPath) {
    this.voiceSamplePath = typeof wavPath === "string" ? wavPath : "";
  }

  setProsody() {}

  speak(text, options = {}) {
    const trimmed = typeof text === "string" ? text.trim() : "";
    if (!trimmed) return Promise.resolve();
    this._speakBackground(trimmed, options).catch((error) => {
      this.emit("debug", `TTS bg error: ${error.message}`);
    });
    return Promise.resolve();
  }

  createSpeechJob(options = {}) {
    const text = typeof options.text === "string" ? options.text.trim() : "";
    const lang = (options.language || this.config.targetLanguage || "en").toLowerCase();
    const device = options.outputDeviceName || this.config.ttsOutputDeviceName || "";
    const voiceProfile = options.voiceProfile || null;
    const voiceIdentityProfile = options.voiceIdentityProfile || null;
    const voiceSamplePath = isConsentedLocalVoiceProfile(voiceProfile) ? voiceProfile.samplePath : this.voiceSamplePath;
    const continuityProfile = this._resolveContinuityProfile({
      text,
      mode: options.mode,
      tempo: options.tempo,
      volumeBoost: options.volumeBoost,
      pitchCents: options.pitchCents,
      startupFadeMs: options.startupFadeMs,
      previousProsody: options.previousProsody,
      continuityScore: options.continuityScore,
      cadence: options.cadence,
      emotionalTilt: options.emotionalTilt,
    });
    const shapedProfile = this.applyVoiceIdentity(voiceIdentityProfile, {
      ...continuityProfile,
      mode: options.mode,
    });
    const playbackProfile = options.mode === "commit"
      ? {
          ...shapedProfile,
          volumeBoost: Math.max(1.1, shapedProfile.volumeBoost),
          tempo: Math.min(0.96, shapedProfile.tempo),
          pitchCents: Math.min(-10, shapedProfile.pitchCents),
          startupFadeMs: Math.min(20, shapedProfile.startupFadeMs),
        }
      : shapedProfile;
    const entryProfile = options.entryProfile && typeof options.entryProfile === "object"
      ? options.entryProfile
      : null;
    const effectivePlaybackProfile = this._applyEntryProfile(playbackProfile, entryProfile);
    const releasePath = path.join(
      this.config.tempDir,
      `tts-release-${Date.now()}-${Math.random().toString(16).slice(2, 8)}.wav`
    );
    let child = null;
    let aborted = false;
    let onStart = null;
    let onEnd = null;
    let activePlayback = null;
    const createdAt = Date.now();

    return {
      get onStart() {
        return onStart;
      },
      set onStart(handler) {
        onStart = handler;
      },
      get onEnd() {
        return onEnd;
      },
      set onEnd(handler) {
        onEnd = handler;
      },
      play: async () => {
        if (!text || aborted) {
          return;
        }

        await fs.mkdir(this.config.tempDir, { recursive: true });
        const segments = this._buildStreamingPlan(text);
        let nextRenderPromise = null;
        let currentRender = null;
        try {
          nextRenderPromise = this._renderStreamingSegment({
            text: segments[0].text,
            lang,
            voiceSamplePath,
            voiceIdentityProfile,
            playbackProfile: effectivePlaybackProfile,
            segmentIndex: 0,
            segmentMeta: segments[0],
            entryProfile,
          });

          for (let index = 0; index < segments.length; index += 1) {
            currentRender = nextRenderPromise;
            nextRenderPromise = index + 1 < segments.length
              ? this._renderStreamingSegment({
                  text: segments[index + 1].text,
                  lang,
                  voiceSamplePath,
                  voiceIdentityProfile,
                  playbackProfile: effectivePlaybackProfile,
                  segmentIndex: index + 1,
                  segmentMeta: segments[index + 1],
                  entryProfile,
                })
              : null;

            const rendered = await currentRender;
            if (!rendered || aborted) {
              break;
            }

            try {
              if (index === segments.length - 1) {
                try {
                  const releaseProfile = options.releaseProfile || {};
                  await this._renderReleaseClip(rendered.rawPath, releasePath, {
                    tailMs: releaseProfile.tailMs ?? 120,
                    fadeMs: releaseProfile.fadeMs ?? 90,
                    pitchCents: (releaseProfile.pitchCents ?? -50) + (playbackProfile.pitchCents * 0.35),
                    tempo: lerp(releaseProfile.tempo ?? 0.95, effectivePlaybackProfile.tempo, 0.2),
                    lowpassHz: releaseProfile.lowpassHz ?? 5200,
                    volume: clamp((releaseProfile.volume ?? 0.95) * lerp(1, effectivePlaybackProfile.volumeBoost, 0.2), 0.75, 1.2),
                  });
                  await this._cacheContinuationClip(releasePath, {
                    tailMs: 120,
                    fadeMs: 95,
                    pitchCents: -10 + (effectivePlaybackProfile.pitchCents * 0.2),
                    tempo: lerp(0.97, effectivePlaybackProfile.tempo, 0.2),
                    lowpassHz: 3000,
                    volume: clamp(lerp(0.85, effectivePlaybackProfile.volumeBoost, 0.2), 0.7, 1.05),
                  });
                } catch (error) {
                  this.emit("debug", `Release shaping failed (${error.message}), using hard fade`);
                }
              }

              activePlayback = this._playPreparedAsset(rendered.playbackAsset.path, device, {
                createdAt,
                onFirstWrite: () => onStart?.(),
              });
              this.currentSpeechPlayback = activePlayback;
              child = activePlayback.child;
              await activePlayback.completed;
              activePlayback = null;
              if (this.currentSpeechPlayback?.id === rendered.playbackAsset.path) {
                this.currentSpeechPlayback = null;
              }
            } finally {
              await rendered.cleanup();
            }
          }

          if (!aborted) {
            onEnd?.();
          }
        } finally {
          if (currentRender) {
            await currentRender.catch(() => {});
          }
          if (nextRenderPromise) {
            await nextRenderPromise.catch(() => {});
          }
          await fs.rm(releasePath, { force: true }).catch(() => {});
        }
      },
      abort: () => {
        aborted = true;
        if (activePlayback) {
          const interruptTriggeredAt = Date.now();
          activePlayback.abort().finally(() => {
            console.log(`[audio] interrupt delay=${Date.now() - interruptTriggeredAt}ms`);
          });
          this.currentSpeechPlayback = null;
          return;
        }
        if (child && !child.killed) {
          try {
            child.kill("SIGKILL");
          } catch {}
        }
      },
      fadeOut: async (ms) => {
        if (aborted) {
          return;
        }
        if (activePlayback?.fadeOut) {
          await activePlayback.fadeOut(ms);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, ms));
      },
      phraseId: options.phraseId,
      continuityScore: playbackProfile.continuityScore,
      tempo: effectivePlaybackProfile.tempo,
      volumeBoost: effectivePlaybackProfile.volumeBoost,
      pitchCents: effectivePlaybackProfile.pitchCents,
      cadence: effectivePlaybackProfile.cadence,
      emotionalTilt: effectivePlaybackProfile.emotionalTilt,
      mode: options.mode,
    };
  }

  preempt(options = {}) {
    const playback = this.currentSpeechPlayback;
    if (!playback?.fadeOut) {
      return;
    }

    const durationMs = Number.isFinite(options.durationMs) ? options.durationMs : 25;
    const aggressiveness = clamp(finiteOr(options.aggressiveness, 0.8), 0.4, 1);
    void playback.fadeOut(Math.max(12, Math.round(durationMs * (1.05 - (aggressiveness * 0.2)))));
  }

  createContinuationJob(options = {}) {
    const sourcePath = this.lastContinuationPath;
    const device = options.outputDeviceName || this.config.ttsOutputDeviceName || "";
    if (!sourcePath) {
      return null;
    }

    let child = null;
    let aborted = false;
    let onStart = null;
    let onEnd = null;
    let activePlayback = null;
    const createdAt = Date.now();

    return {
      get onStart() {
        return onStart;
      },
      set onStart(handler) {
        onStart = handler;
      },
      get onEnd() {
        return onEnd;
      },
      set onEnd(handler) {
        onEnd = handler;
      },
      play: async () => {
        if (aborted) {
          return;
        }

        try {
          await fs.access(sourcePath);
        } catch {
          return;
        }

        const playbackAsset = await this._preparePlaybackAsset(sourcePath, {
          skipStartupFade: true,
          volumeBoost: options.volumeBoost ?? 0.85,
          tempo: options.tempo ?? 0.97,
          pitchCents: options.pitchCents ?? 0,
          lowpassHz: options.kind === "stretch" ? 3600 : 3000,
          fadeOutMs: options.kind === "stretch" ? 60 : 90,
        });
        try {
          activePlayback = this._playPreparedAsset(playbackAsset.path, device, {
            createdAt,
            onFirstWrite: () => onStart?.(),
          });
          child = activePlayback.child;
          await activePlayback.completed;
          if (!aborted) {
            onEnd?.();
          }
        } finally {
          await playbackAsset.cleanup();
        }
      },
      abort: () => {
        aborted = true;
        if (activePlayback) {
          const interruptTriggeredAt = Date.now();
          activePlayback.abort().finally(() => {
            console.log(`[audio] interrupt delay=${Date.now() - interruptTriggeredAt}ms`);
            onEnd?.();
          });
          return;
        }
        if (child && !child.killed) {
          try {
            child.kill("SIGKILL");
          } catch {}
        }
        onEnd?.();
      },
    };
  }

  createPresenceJob(options = {}) {
    const sourcePath = this.lastContinuationPath;
    const device = options.outputDeviceName || this.config.ttsOutputDeviceName || "";
    if (!sourcePath) {
      return null;
    }

    let child = null;
    let aborted = false;
    let onStart = null;
    let onEnd = null;
    let activePlayback = null;
    const createdAt = Date.now();

    return {
      get onStart() {
        return onStart;
      },
      set onStart(handler) {
        onStart = handler;
      },
      get onEnd() {
        return onEnd;
      },
      set onEnd(handler) {
        onEnd = handler;
      },
      play: async () => {
        if (aborted) {
          return;
        }

        try {
          await fs.access(sourcePath);
        } catch {
          return;
        }

        const playbackAsset = await this._preparePlaybackAsset(sourcePath, {
          skipStartupFade: true,
          volumeBoost: options.volumeBoost ?? 0.028,
          tempo: clamp(0.985 + (((options.speechRate ?? 1.0) - 1.0) * 0.05), 0.97, 1.02),
          pitchCents: clamp(((Math.random() * 6) - 3), -3, 3),
          lowpassHz: 2400,
          fadeOutMs: 90,
          trimSeconds: 0.12,
        });
        try {
          activePlayback = this._playPreparedAsset(playbackAsset.path, device, {
            createdAt,
            onFirstWrite: () => onStart?.(),
          });
          child = activePlayback.child;
          await activePlayback.completed;
          if (!aborted) {
            onEnd?.();
          }
        } finally {
          await playbackAsset.cleanup();
        }
      },
      abort: () => {
        aborted = true;
        if (activePlayback) {
          const interruptTriggeredAt = Date.now();
          activePlayback.abort().finally(() => {
            console.log(`[audio] interrupt delay=${Date.now() - interruptTriggeredAt}ms`);
            onEnd?.();
          });
          return;
        }
        if (child && !child.killed) {
          try {
            child.kill("SIGKILL");
          } catch {}
        }
        onEnd?.();
      },
    };
  }

  playPresence(options = {}) {
    const outputDeviceName = options.outputDeviceName || this.config.ttsOutputDeviceName || "";
    if (this.presenceState.active) {
      return;
    }

    const chunkDurationMs = 40;
    const loopDurationMs = 240;
    const buffer = this._generatePresenceBuffer({
      energy: options.energy,
      tempo: options.tempo,
      tilt: options.tilt,
      chunkDurationMs: loopDurationMs,
    });
    const chunks = [];
    const bytesPerFrame = (Number.isFinite(this.config.channels) ? this.config.channels : 1) * 2;
    const samplesPerChunk = Math.max(
      1,
      Math.round(((Number.isFinite(this.config.sampleRate) ? this.config.sampleRate : 16000) * chunkDurationMs) / 1000)
    );
    const bytesPerChunk = samplesPerChunk * bytesPerFrame;

    for (let offset = 0; offset < buffer.length; offset += bytesPerChunk) {
      chunks.push(buffer.subarray(offset, Math.min(buffer.length, offset + bytesPerChunk)));
    }
    if (chunks.length === 0) {
      chunks.push(buffer);
    }

    this.presenceState = {
      active: true,
      timer: null,
      outputDeviceName,
      writeInFlight: false,
      chunkIndex: 0,
      chunks,
    };

    const tick = () => {
      if (!this.presenceState.active || this.presenceState.writeInFlight) {
        return;
      }
      const nextChunk = this.presenceState.chunks[this.presenceState.chunkIndex % this.presenceState.chunks.length];
      this.presenceState.chunkIndex += 1;
      this.presenceState.writeInFlight = true;
      void this._writePresenceChunk(nextChunk, outputDeviceName).finally(() => {
        if (this.presenceState.active) {
          this.presenceState.writeInFlight = false;
        }
      });
    };

    tick();
    const timer = setInterval(tick, chunkDurationMs);
    timer.unref?.();
    this.presenceState.timer = timer;
  }

  stopPresence() {
    if (!this.presenceState.active) {
      return;
    }

    if (this.presenceState.timer) {
      clearInterval(this.presenceState.timer);
    }
    this.presenceState = {
      active: false,
      timer: null,
      outputDeviceName: "",
      writeInFlight: false,
      chunkIndex: 0,
      chunks: [],
    };
  }

  playFile(audioPath, options = {}) {
    const device = options.outputDeviceName || this.config.ttsOutputDeviceName || "";
    return this._playWav(audioPath, device);
  }

  async warmup(options = {}) {
    const lang = (options.language || this.config.targetLanguage || "en").toLowerCase();
    const warmSpeechPath = path.join(this.config.tempDir, `tts-warm-${Date.now()}-${Math.random().toString(16).slice(2, 8)}.wav`);
    const warmSilencePath = path.join(this.config.tempDir, `tts-warm-silence-${Date.now()}-${Math.random().toString(16).slice(2, 8)}.wav`);
    const sampleRate = Number.isFinite(this.config.sampleRate) ? this.config.sampleRate : 16000;
    const silenceFrames = Math.max(1, Math.round(sampleRate * 0.12));

    await fs.mkdir(this.config.tempDir, { recursive: true });
    try {
      await this._renderSpeechToFile("hello", { lang, voiceSamplePath: "", outputPath: warmSpeechPath });
      await writePcmAsWavFile(warmSilencePath, Buffer.alloc(silenceFrames * 2), {
        sampleRate,
        channels: 1,
        bitsPerSample: 16,
      });
      await this._playWav(warmSilencePath, options.outputDeviceName || this.config.ttsOutputDeviceName || "", {
        skipStartupFade: true,
      });
    } finally {
      await Promise.all([
        fs.rm(warmSpeechPath, { force: true }).catch(() => {}),
        fs.rm(warmSilencePath, { force: true }).catch(() => {}),
      ]);
      this.startupFadeInPending = true;
    }
  }

  async _speakBackground(text, options) {
    const lang = (options.language || this.config.targetLanguage || "en").toLowerCase();
    const device = options.outputDeviceName || this.config.ttsOutputDeviceName || "";
    const voiceProfile = options.voiceProfile || null;
    const voiceSamplePath = isConsentedLocalVoiceProfile(voiceProfile) ? voiceProfile.samplePath : this.voiceSamplePath;

    if (options.backgroundAudioPath) {
      try {
        await this._renderAndPlayComposite(text, {
          lang,
          device,
          voiceSamplePath,
          backgroundAudioPath: options.backgroundAudioPath,
          prosody: options.prosody,
        });
        return;
      } catch (error) {
        this.emit("debug", `Composite playback failed (${error.message}), falling back to dry speech`);
      }
    }

    if (voiceSamplePath && this._xttsAvailable()) {
      try {
        await this._speakXtts(text, { lang, device, voiceSamplePath });
        this.emit("debug", `TTS OK [XTTS] lang=${lang}`);
        return;
      } catch (error) {
        this.emit("debug", `XTTS failed (${error.message}), using offline generic speaker`);
      }
    }

    try {
      if (this._prefersPremiumVoicePath(options) && this._shouldUseElevenLabs(options)) {
        await this._speakElevenLabs(text, { lang, device });
        this.emit("debug", `TTS OK [elevenlabs] lang=${lang}`);
        return;
      }
    } catch (error) {
      this.emit("debug", `ElevenLabs failed (${error.message}), falling back`);
    }

    try {
      if (this._shouldUseOpenAiTts(options)) {
        const instructions = options.instructions || this._buildSpeechInstructions(options.prosody, options);
        await this.openai.speak(text, {
          language: lang,
          outputDeviceName: device,
          voiceId: this.config.ttsVoiceName,
          instructions,
          speed: options.speed,
        });
        this.emit("debug", `TTS OK [openai] lang=${lang}`);
        return;
      }
    } catch (error) {
      this.emit("debug", `OpenAI TTS failed (${error.message}), falling back`);
    }

    try {
      if (!this._prefersPremiumVoicePath(options) && this._shouldUseElevenLabs(options)) {
        await this._speakElevenLabs(text, { lang, device });
        this.emit("debug", `TTS OK [elevenlabs] lang=${lang}`);
        return;
      }
    } catch (error) {
      this.emit("debug", `ElevenLabs failed (${error.message}), falling back`);
    }

    try {
      await this.edge.speak(text, { language: lang, outputDeviceName: device });
      return;
    } catch (error) {
      this.emit("debug", `edge-tts failed (${error.message}), using SAPI`);
    }

    if (lang === "en") {
      try {
        await this.sapi.speak(text, { outputDeviceName: device });
      } catch (error) {
        this.emit("debug", `SAPI failed: ${error.message}`);
      }
    }
  }

  async _renderAndPlayComposite(text, { lang, device, voiceSamplePath, backgroundAudioPath, prosody }) {
    await fs.mkdir(this.config.tempDir, { recursive: true });
    const rawSpeechPath = path.join(this.config.tempDir, `tts-raw-${Date.now()}.wav`);
    const styledSpeechPath = path.join(this.config.tempDir, `tts-styled-${Date.now()}.wav`);
    const mixedPath = path.join(this.config.tempDir, `tts-mix-${Date.now()}.wav`);

    try {
      await this._renderSpeechToFile(text, { lang, voiceSamplePath, outputPath: rawSpeechPath });
      const speechPath = await this._applyProsodyIfPossible({
        inputPath: rawSpeechPath,
        outputPath: styledSpeechPath,
        prosody,
      });
      await this._mixBackground(backgroundAudioPath, speechPath, mixedPath);
      await this._playWav(mixedPath, device);
    } finally {
      await Promise.all([
        fs.rm(rawSpeechPath, { force: true }).catch(() => {}),
        fs.rm(styledSpeechPath, { force: true }).catch(() => {}),
        fs.rm(mixedPath, { force: true }).catch(() => {}),
      ]);
    }
  }

  async _renderSpeechToFile(text, { lang, voiceSamplePath, outputPath, voiceIdentityProfile = null }) {
    if (voiceSamplePath && this._xttsAvailable()) {
      try {
        await this.xtts.synthesizeToWave({
          text,
          language: lang,
          samplePath: voiceSamplePath,
          outputPath,
        });
        return outputPath;
      } catch (error) {
        this.emit("debug", `XTTS file render failed (${error.message}), falling back to edge-tts`);
      }
    }

    try {
      if (this._prefersPremiumVoicePath({}) && this._shouldUseElevenLabs({ onlinePolicy: this.config.onlinePolicy })) {
        await this.elevenlabs.synthesizeToWave({
          text,
          voiceId: this.config.elevenlabsVoiceId,
          model: lang === "en" ? "eleven_turbo_v2_5" : "eleven_multilingual_v2",
          outputPath,
        });
        return outputPath;
      }
    } catch (error) {
      this.emit("debug", `ElevenLabs file render failed (${error.message}), falling back`);
    }

    try {
      if (this._shouldUseOpenAiTts({ onlinePolicy: this.config.onlinePolicy })) {
        await this.openai.synthesizeToFile(text, outputPath, {
          language: lang,
          voiceId: this.config.ttsVoiceName,
          instructions: this._buildSpeechInstructions({}, { language: lang, voiceIdentityProfile }),
        });
        return outputPath;
      }
    } catch (error) {
      this.emit("debug", `OpenAI file render failed (${error.message}), falling back`);
    }

    await this.edge.synthesizeToFile(text, { language: lang, outputPath });
    return outputPath;
  }

  async _renderStreamingSegment({
    text,
    lang,
    voiceSamplePath,
    voiceIdentityProfile,
    playbackProfile,
    segmentIndex,
    segmentMeta = {},
    entryProfile = null,
  }) {
    const rawPath = path.join(
      this.config.tempDir,
      `tts-job-${Date.now()}-${segmentIndex}-${Math.random().toString(16).slice(2, 8)}.wav`
    );
    let playbackAsset = null;
    try {
      await this._renderSpeechToFile(text, {
        lang,
        voiceSamplePath,
        outputPath: rawPath,
        voiceIdentityProfile,
      });
      const playbackOptions = {
        startupFadeMs: segmentIndex === 0
          ? (entryProfile?.attack === "fast" ? 5 : playbackProfile.startupFadeMs)
          : (segmentMeta.joinFadeMs ?? 5),
        skipStartupFade: false,
        volumeBoost: segmentIndex === 0 && Number.isFinite(entryProfile?.volumeBoost)
          ? entryProfile.volumeBoost
          : playbackProfile.volumeBoost,
        tempo: playbackProfile.tempo,
        pitchCents: playbackProfile.pitchCents,
        bassDb: playbackProfile.bassDb,
        trebleDb: playbackProfile.trebleDb,
        fadeOutMs: segmentMeta.isMicro ? (segmentMeta.joinFadeMs ?? 5) : 0,
        startOffsetMs: segmentIndex === 0 ? finiteOr(entryProfile?.startOffsetMs, 0) : 0,
      };
      playbackAsset = await this._preparePlaybackAsset(rawPath, playbackOptions);
      return {
        rawPath,
        playbackAsset,
        cleanup: async () => {
          await Promise.all([
            playbackAsset?.cleanup?.().catch(() => {}),
            fs.rm(rawPath, { force: true }).catch(() => {}),
          ]);
        },
      };
    } catch (error) {
      await Promise.all([
        playbackAsset?.cleanup?.().catch(() => {}),
        fs.rm(rawPath, { force: true }).catch(() => {}),
      ]);
      throw error;
    }
  }

  _splitTextForStreaming(text) {
    const normalized = typeof text === "string" ? text.replace(/\s+/g, " ").trim() : "";
    if (!normalized) {
      return [];
    }

    const maxChunkLength = 80;
    const clauses = normalized.match(/[^,.;:!?]+(?:[,.;:!?]+|$)/g) || [normalized];
    const segments = [];
    let carry = "";

    for (const clause of clauses) {
      const next = clause.trim();
      if (!next) {
        continue;
      }

      if (!carry) {
        carry = next;
        continue;
      }

      if ((carry.length + 1 + next.length) <= maxChunkLength) {
        carry = `${carry} ${next}`;
        continue;
      }

      segments.push(carry);
      carry = next;
    }

    if (carry) {
      segments.push(carry);
    }

    return segments.length > 0 ? segments : [normalized];
  }

  _splitClauseMicro(text) {
    const normalized = typeof text === "string" ? text.replace(/\s+/g, " ").trim() : "";
    if (!normalized) {
      return [];
    }

    const tokens = normalized.match(/\S+\s*/g) || [normalized];
    const microSegments = [];
    let chunk = "";

    for (let index = 0; index < tokens.length; index += 1) {
      chunk += tokens[index];
      const wordsInChunk = chunk.trim().split(/\s+/).filter(Boolean).length;
      const shouldBreak =
        wordsInChunk >= 3 ||
        /[,:;.!?]\s*$/.test(chunk) ||
        chunk.length >= 28;

      if (shouldBreak) {
        microSegments.push(chunk.trim());
        chunk = "";
      }
    }

    if (chunk.trim()) {
      microSegments.push(chunk.trim());
    }

    return microSegments.length > 0 ? microSegments : [normalized];
  }

  _buildStreamingPlan(text) {
    const clauses = this._splitTextForStreaming(text);
    const plan = [];

    for (let clauseIndex = 0; clauseIndex < clauses.length; clauseIndex += 1) {
      const microSegments = this._splitClauseMicro(clauses[clauseIndex]);
      for (let microIndex = 0; microIndex < microSegments.length; microIndex += 1) {
        plan.push({
          text: microSegments[microIndex],
          clauseIndex,
          microIndex,
          isMicro: microSegments.length > 1,
          joinFadeMs: microSegments.length > 1 ? 5 : 0,
        });
      }
    }

    return plan.length > 0
      ? plan
      : [{ text: typeof text === "string" ? text.trim() : "", clauseIndex: 0, microIndex: 0, isMicro: false, joinFadeMs: 0 }];
  }

  _applyEntryProfile(playbackProfile, entryProfile) {
    if (!entryProfile || typeof entryProfile !== "object") {
      return playbackProfile;
    }

    return {
      ...playbackProfile,
      volumeBoost: clamp(
        Math.max(
          finiteOr(playbackProfile.volumeBoost, 1.0),
          finiteOr(entryProfile.volumeBoost, playbackProfile.volumeBoost)
        ),
        0.86,
        1.24
      ),
      tempo: clamp(
        finiteOr(playbackProfile.tempo, 1.0) * finiteOr(entryProfile.tempoScale, 1.0),
        0.9,
        1.08
      ),
      pitchCents: clamp(
        finiteOr(playbackProfile.pitchCents, 0) + finiteOr(entryProfile.pitchLiftCents, 0),
        -80,
        80
      ),
      startupFadeMs: entryProfile.attack === "fast"
        ? Math.min(5, finiteOr(playbackProfile.startupFadeMs, 20))
        : playbackProfile.startupFadeMs,
    };
  }

  async _applyProsodyIfPossible({ inputPath, outputPath, prosody }) {
    if (!prosody || typeof prosody !== "object") {
      return inputPath;
    }

    try {
      await this.prosodyEngine.transferProsody({
        inputWav: inputPath,
        outputWav: outputPath,
        pitchMean: prosody.pitch_mean || prosody.pitchMean,
        pitchStd: prosody.pitch_std || prosody.pitchStd,
        energyMean: prosody.energy_mean || prosody.energyMean,
        speakingRate: prosody.speaking_rate || prosody.speakingRate,
      });
      return outputPath;
    } catch (error) {
      this.emit("debug", `Prosody transfer failed (${error.message}), using dry speech render`);
      return inputPath;
    }
  }

  _mixBackground(backgroundPath, speechPath, outputPath) {
    return new Promise((resolve, reject) => {
      const args = [
        "-m",
        "-v",
        "1.0",
        backgroundPath,
        "-v",
        "1.15",
        speechPath,
        outputPath,
      ];
      const child = spawn(this.config.soxPath, args, { stdio: ["ignore", "pipe", "pipe"] });
      let stderr = "";
      child.stderr.on("data", (chunk) => {
        stderr += chunk.toString();
      });
      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0) resolve(outputPath);
        else reject(new Error(stderr.trim() || `SoX mix failed (exit ${code})`));
      });
    });
  }

  async _speakXtts(text, { lang, device, voiceSamplePath }) {
    await fs.mkdir(this.config.tempDir, { recursive: true });
    const rawWav = path.join(this.config.tempDir, `xtts-${Date.now()}.wav`);
    try {
      await this.xtts.synthesizeToWave({
        text,
        language: lang,
        samplePath: voiceSamplePath,
        outputPath: rawWav,
      });
      await this._playWav(rawWav, device);
    } finally {
      await fs.rm(rawWav, { force: true }).catch(() => {});
    }
  }

  async _speakElevenLabs(text, { lang, device }) {
    await fs.mkdir(this.config.tempDir, { recursive: true });
    const outPath = path.join(this.config.tempDir, `elevenlabs-${Date.now()}.mp3`);
    try {
      await this.elevenlabs.synthesizeToWave({
        text,
        voiceId: this.config.elevenlabsVoiceId,
        model: lang === "en" ? "eleven_turbo_v2_5" : "eleven_multilingual_v2",
        outputPath: outPath,
      });
      await this._playWav(outPath, device);
    } finally {
      await fs.rm(outPath, { force: true }).catch(() => {});
    }
  }

  _playWav(wavPath, outputDeviceName, options = {}) {
    return new Promise((resolve, reject) => {
      void this._preparePlaybackAsset(wavPath, options)
        .then((playbackAsset) => {
          const playback = this._playPreparedAsset(playbackAsset.path, outputDeviceName, {
            createdAt: Date.now(),
          });
          playback.completed.then(() => {
            void playbackAsset.cleanup().finally(() => {
              if (!options.skipStartupFade) {
                this.startupFadeInPending = false;
              }
              resolve();
            });
          }).catch((error) => {
            void playbackAsset.cleanup().finally(() => reject(error));
          });
        })
        .catch(reject);
    });
  }

  async _writePresenceChunk(chunk, outputDeviceName) {
    const stream = this._getOrCreateAudioStream(outputDeviceName);
    await this._writeToAudioStream(stream, chunk, {
      auditGaps: false,
      countAsAudio: false,
    });
  }

  _playPreparedAsset(assetPath, outputDeviceName, options = {}) {
    const stream = this._getOrCreateAudioStream(outputDeviceName);
    const decoder = this._spawnPcmDecoder(assetPath);
    let finished = false;
    let firstWriteLogged = false;
    let fadeState = null;
    let resolvePromise = () => {};
    let rejectPromise = () => {};
    let currentWrite = Promise.resolve();
    const detachStreamError = stream.onError((error) => {
      finish(error);
    });
    const completed = new Promise((resolve, reject) => {
      resolvePromise = resolve;
      rejectPromise = reject;
    });

    const finish = (error = null) => {
      if (finished) {
        return;
      }
      finished = true;
      detachStreamError();
      if (error) {
        rejectPromise(error);
      } else {
        resolvePromise();
      }
    };

    const applyFade = (chunk) => {
      if (!fadeState) {
        return chunk;
      }
      const nextChunk = Buffer.from(chunk);
      const totalSamples = Math.floor(nextChunk.length / 2);
      if (totalSamples <= 0) {
        return nextChunk;
      }
      for (let index = 0; index < totalSamples; index += 1) {
        const now = Date.now();
        const elapsed = now - fadeState.startedAt;
        const scale = Math.max(0, 1 - (elapsed / Math.max(fadeState.durationMs, 1)));
        const sampleOffset = index * 2;
        const sample = nextChunk.readInt16LE(sampleOffset);
        nextChunk.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(sample * scale))), sampleOffset);
      }
      return nextChunk;
    };

    const writeChunk = async (chunk) => {
      if (finished) {
        return;
      }
      const payload = applyFade(chunk);
      await this._writeToAudioStream(stream, payload, {
        createdAt: options.createdAt,
        onFirstWrite: () => {
          if (firstWriteLogged) {
            return false;
          }
          firstWriteLogged = true;
          options.onFirstWrite?.();
          return true;
        },
      });
    };

    decoder.stdout.on("data", (chunk) => {
      decoder.stdout.pause();
      currentWrite = writeChunk(chunk)
        .then(() => {
          if (!finished) {
            decoder.stdout.resume();
          }
        })
        .catch((error) => {
          try {
            decoder.kill("SIGKILL");
          } catch {}
          finish(error);
        });
    });

    decoder.on("error", (error) => {
      finish(error);
    });

    decoder.on("close", (code) => {
      if (finished) {
        return;
      }
      void currentWrite.finally(() => {
        if (code === 0 || code === null) {
          finish();
        } else {
          finish(new Error(`SoX PCM decode failed (exit ${code})`));
        }
      });
    });

    return {
      id: assetPath,
      child: decoder,
      completed,
      fadeOut: async (durationMs) => {
        fadeState = {
          startedAt: Date.now(),
          durationMs: Math.max(1, durationMs),
        };
      },
      abort: async () => {
        if (finished) {
          return;
        }
        try {
          decoder.kill("SIGKILL");
        } catch {}
      },
    };
  }

  _getOrCreateAudioStream(outputDeviceName = "") {
    const deviceKey = outputDeviceName || "__default__";
    const existing = this.audioStreams.get(deviceKey);
    if (existing && !existing.closed) {
      return existing;
    }

    const sampleRate = Number.isFinite(this.config.sampleRate) ? this.config.sampleRate : 16000;
    const channels = Number.isFinite(this.config.channels) ? this.config.channels : 1;
    const bitsPerSample = 16;
    const args = [
      "-q",
      "-t",
      "raw",
      "-r",
      String(sampleRate),
      "-e",
      "signed-integer",
      "-b",
      String(bitsPerSample),
      "-c",
      String(channels),
      "-",
    ];
    if (outputDeviceName) {
      args.push("-t", "waveaudio", outputDeviceName);
    } else {
      args.push("-d");
    }

    const child = spawn(this.config.soxPath, args, { stdio: ["pipe", "ignore", "pipe"] });
    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    const listeners = new Set();
    const entry = {
      child,
      stdin: child.stdin,
      closed: false,
      onError: (handler) => {
        listeners.add(handler);
        return () => {
          listeners.delete(handler);
        };
      },
      close: () => {
        if (entry.closed) {
          return;
        }
        entry.closed = true;
        this.audioStreams.delete(deviceKey);
        try {
          child.stdin.end();
        } catch {}
        try {
          child.kill("SIGKILL");
        } catch {}
      },
    };

    const notify = (error) => {
      for (const listener of listeners) {
        try {
          listener(error);
        } catch {}
      }
    };

    child.on("error", (error) => {
      entry.closed = true;
      this.audioStreams.delete(deviceKey);
      notify(error);
    });
    child.on("close", (code) => {
      entry.closed = true;
      this.audioStreams.delete(deviceKey);
      if (code !== 0 && code !== null) {
        notify(new Error(stderr.trim() || `SoX output stream failed (exit ${code})`));
      }
    });

    this.audioStreams.set(deviceKey, entry);
    return entry;
  }

  async _writeToAudioStream(stream, payload, options = {}) {
    const now = Date.now();
    const auditGaps = options.auditGaps !== false;
    if (auditGaps && this.lastAudioWriteAt && now - this.lastAudioWriteAt > 100) {
      console.log(`[audio] GAP DETECTED: ${now - this.lastAudioWriteAt}ms`);
    }
    if (options.countAsAudio !== false) {
      this.lastAudioWriteAt = now;
    }
    if (typeof options.onFirstWrite === "function") {
      const shouldLogWrite = options.onFirstWrite() !== false;
      if (shouldLogWrite && Number.isFinite(options.createdAt)) {
        console.log(`[audio] write latency=${now - options.createdAt}ms`);
      }
    }
    if (!stream.stdin.write(payload)) {
      await new Promise((resolve) => {
        const onDrain = () => {
          stream.stdin.off("drain", onDrain);
          resolve();
        };
        stream.stdin.once("drain", onDrain);
      });
    }
  }

  _spawnPcmDecoder(inputPath) {
    const sampleRate = Number.isFinite(this.config.sampleRate) ? this.config.sampleRate : 16000;
    const channels = Number.isFinite(this.config.channels) ? this.config.channels : 1;
    const args = [
      "-q",
      inputPath,
      "-t",
      "raw",
      "-r",
      String(sampleRate),
      "-e",
      "signed-integer",
      "-b",
      "16",
      "-c",
      String(channels),
      "-",
    ];
    return spawn(this.config.soxPath, args, { stdio: ["ignore", "pipe", "pipe"] });
  }

  _generatePresenceBuffer({ energy, tempo, tilt, chunkDurationMs = 240 } = {}) {
    const sampleRate = Number.isFinite(this.config.sampleRate) ? this.config.sampleRate : 16000;
    const channels = Number.isFinite(this.config.channels) ? this.config.channels : 1;
    const sampleCount = Math.max(1, Math.round((sampleRate * chunkDurationMs) / 1000));
    const pcm = Buffer.alloc(sampleCount * channels * 2);
    const amplitude = clamp(0.0025 + (clamp(finiteOr(energy, 0.35), 0.2, 0.6) * 0.0045), 0.002, 0.006);
    const lfoHz = clamp(1.4 + ((finiteOr(tempo, 1.0) - 1.0) * 2) + (Math.abs(finiteOr(tilt, 0)) * 0.8), 0.8, 3.2);
    let low = 0;
    let band = 0;

    for (let index = 0; index < sampleCount; index += 1) {
      const t = index / sampleRate;
      const white = (Math.random() * 2) - 1;
      low = (low * 0.985) + (white * 0.015);
      band = (band * 0.92) + ((low - band) * 0.08);
      const lfo = 0.72 + (0.28 * Math.sin(2 * Math.PI * lfoHz * t));
      const breath = band * amplitude * lfo;
      const envelope = Math.min(1, index / (sampleRate * 0.02), (sampleCount - index) / (sampleRate * 0.03));
      const sampleValue = Math.round(clamp(breath * envelope, -0.012, 0.012) * 32767);

      for (let channel = 0; channel < channels; channel += 1) {
        pcm.writeInt16LE(sampleValue, ((index * channels) + channel) * 2);
      }
    }

    return pcm;
  }

  _spawnWavPlayer(wavPath, outputDeviceName, options = {}) {
    const volumeBoost = Number.isFinite(options.volumeBoost) ? options.volumeBoost : 1.0;
    const args = outputDeviceName
      ? ["-q", "-v", String(volumeBoost), wavPath, "-t", "waveaudio", outputDeviceName]
      : ["-q", "-v", String(volumeBoost), wavPath, "-d"];
    const startupFadeMs = Number.isFinite(options.startupFadeMs)
      ? options.startupFadeMs
      : (!options.skipStartupFade && this.startupFadeInPending ? 100 : 0);
    const tempo = Number.isFinite(options.tempo) ? options.tempo : 1.0;
    const pitchCents = Number.isFinite(options.pitchCents) ? options.pitchCents : 0;
    if (startupFadeMs > 0) {
      args.push("fade", "q", `${(startupFadeMs / 1000).toFixed(2)}`);
    }
    if (pitchCents !== 0) {
      args.push("pitch", `${Math.round(pitchCents)}`);
    }
    if (tempo !== 1.0) {
      args.push("tempo", "-s", tempo.toFixed(2));
    }
    if (Number.isFinite(options.bassDb) && Math.abs(options.bassDb) >= 0.2) {
      args.push("bass", options.bassDb.toFixed(1));
    }
    if (Number.isFinite(options.trebleDb) && Math.abs(options.trebleDb) >= 0.2) {
      args.push("treble", options.trebleDb.toFixed(1));
    }
    return spawn(this.config.soxPath, args, { stdio: ["ignore", "pipe", "pipe"] });
  }

  async _preparePlaybackAsset(inputPath, options = {}) {
    const shouldDump = process.env.ULT_DUMP_AUDIO === "1";
    const hasTransforms = this._hasPlaybackTransforms(options);

    if (!shouldDump && !hasTransforms) {
      return {
        path: inputPath,
        cleanup: async () => {},
      };
    }

    await fs.mkdir(this.config.tempDir, { recursive: true });
    const preparedPath = path.join(
      this.config.tempDir,
      `ult-playback-${Date.now()}-${Math.random().toString(16).slice(2, 8)}.wav`
    );

    await this._renderPlaybackAsset(inputPath, preparedPath, options);
    if (shouldDump) {
      const dumpPath = path.join(
        this.config.tempDir,
        `ult-listen-${Date.now()}-${Math.random().toString(16).slice(2, 8)}.wav`
      );
      await fs.copyFile(preparedPath, dumpPath);
      console.log("[ULT][dump]", dumpPath);
      this.emit("debug", `[ULT][dump] ${dumpPath}`);
    }

    return {
      path: preparedPath,
      cleanup: async () => {
        await fs.rm(preparedPath, { force: true }).catch(() => {});
      },
    };
  }

  async _renderPlaybackAsset(inputPath, outputPath, options = {}) {
    const volumeBoost = Number.isFinite(options.volumeBoost) ? options.volumeBoost : 1.0;
    const startupFadeMs = Number.isFinite(options.startupFadeMs)
      ? options.startupFadeMs
      : (!options.skipStartupFade && this.startupFadeInPending ? 100 : 0);
    const tempo = Number.isFinite(options.tempo) ? options.tempo : 1.0;
    const pitchCents = Number.isFinite(options.pitchCents) ? options.pitchCents : 0;
    const bassDb = Number.isFinite(options.bassDb) ? options.bassDb : 0;
    const trebleDb = Number.isFinite(options.trebleDb) ? options.trebleDb : 0;
    const lowpassHz = Number.isFinite(options.lowpassHz) ? options.lowpassHz : 0;
    const fadeOutMs = Number.isFinite(options.fadeOutMs) ? options.fadeOutMs : 0;
    const startOffsetMs = Number.isFinite(options.startOffsetMs) ? options.startOffsetMs : 0;
    const trimSeconds = Number.isFinite(options.trimSeconds) ? options.trimSeconds : 0;
    const args = ["-q"];

    if (volumeBoost !== 1.0) {
      args.push("-v", String(volumeBoost));
    }
    args.push(inputPath, outputPath);

    if (startOffsetMs > 0 || trimSeconds > 0) {
      const startSeconds = Math.max(0, startOffsetMs / 1000);
      args.push("trim", startSeconds.toFixed(3));
      if (trimSeconds > 0) {
        args.push(trimSeconds.toFixed(3));
      }
    }

    if (startupFadeMs > 0) {
      args.push("fade", "q", `${(startupFadeMs / 1000).toFixed(2)}`);
    }
    if (pitchCents !== 0) {
      args.push("pitch", `${Math.round(pitchCents)}`);
    }
    if (tempo !== 1.0) {
      args.push("tempo", "-s", tempo.toFixed(2));
    }
    if (Math.abs(bassDb) >= 0.2) {
      args.push("bass", bassDb.toFixed(1));
    }
    if (Math.abs(trebleDb) >= 0.2) {
      args.push("treble", trebleDb.toFixed(1));
    }
    if (lowpassHz > 0) {
      args.push("lowpass", String(Math.round(lowpassHz)));
    }
    if (fadeOutMs > 0) {
      const fadeSeconds = (fadeOutMs / 1000).toFixed(2);
      args.push("fade", "t", "0", "0", fadeSeconds);
    }

    await this._runSox(args, "SoX playback render failed");
  }

  _hasPlaybackTransforms(options = {}) {
    const startupFadeMs = Number.isFinite(options.startupFadeMs)
      ? options.startupFadeMs
      : (!options.skipStartupFade && this.startupFadeInPending ? 100 : 0);
    return (
      startupFadeMs > 0 ||
      (Number.isFinite(options.volumeBoost) && options.volumeBoost !== 1.0) ||
      (Number.isFinite(options.tempo) && options.tempo !== 1.0) ||
      (Number.isFinite(options.pitchCents) && options.pitchCents !== 0) ||
      (Number.isFinite(options.bassDb) && Math.abs(options.bassDb) >= 0.2) ||
      (Number.isFinite(options.trebleDb) && Math.abs(options.trebleDb) >= 0.2) ||
      (Number.isFinite(options.lowpassHz) && options.lowpassHz > 0) ||
      (Number.isFinite(options.fadeOutMs) && options.fadeOutMs > 0) ||
      (Number.isFinite(options.trimSeconds) && options.trimSeconds > 0)
    );
  }

  _runSox(args, fallbackMessage) {
    return new Promise((resolve, reject) => {
      const child = spawn(this.config.soxPath, args, { stdio: ["ignore", "pipe", "pipe"] });
      let stderr = "";
      child.stderr.on("data", (chunk) => {
        stderr += chunk.toString();
      });
      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0) {
          resolve();
        } else {
          reject(new Error(stderr.trim() || `${fallbackMessage} (exit ${code})`));
        }
      });
    });
  }

  applyVoiceIdentity(profile, options = {}) {
    const base = {
      ...options,
      bassDb: finiteOr(options.bassDb, 0),
      trebleDb: finiteOr(options.trebleDb, 0),
    };
    if (!profile || typeof profile !== "object") {
      return base;
    }

    const formants = Array.isArray(profile.formants) ? profile.formants : [];
    const lowFormant = finiteOr(formants[0], 500);
    const highFormant = finiteOr(formants[2], 2800);
    const targetTempo = clamp(finiteOr(profile.tempo, base.tempo), 0.92, 1.08);
    const targetVolume = clamp(0.9 + (finiteOr(profile.energy, 0.06) * 1.2), 0.88, 1.12);
    const pitchBias =
      ((clamp(finiteOr(profile.f0Mean, 165), 95, 250) - 165) * 0.18) +
      (clamp(finiteOr(profile.tilt, 0), -1, 1) * 6);
    const bassDb = clamp(((560 - lowFormant) / 180) - (finiteOr(profile.tilt, 0) * 1.4), -2.5, 2.5);
    const trebleDb = clamp(((highFormant - 3000) / 320) + (finiteOr(profile.tilt, 0) * 2.1), -2.5, 2.5);

    return {
      ...base,
      tempo: clamp(lerp(base.tempo, targetTempo, 0.35), 0.9, 1.12),
      volumeBoost: clamp(lerp(base.volumeBoost, targetVolume, 0.3), 0.86, 1.12),
      pitchCents: clamp(base.pitchCents + pitchBias, -80, 80),
      cadence: clamp(lerp(base.cadence, finiteOr(profile.cadence, base.cadence), 0.35), 0, 1),
      emotionalTilt: clamp(base.emotionalTilt + (finiteOr(profile.tilt, 0) * 0.25), -1, 1),
      startupFadeMs: clamp(Math.round(base.startupFadeMs - (Math.abs(finiteOr(profile.tilt, 0)) * 4)), 12, 100),
      bassDb,
      trebleDb,
    };
  }

  _resolveContinuityProfile(options = {}) {
    const previous = options.previousProsody || {};
    const continuityScore = clamp(options.continuityScore ?? 0, 0, 1);
    const baseTempo = finiteOr(options.tempo, 1.0);
    const baseVolumeBoost = finiteOr(options.volumeBoost, 1.0);
    const basePitchCents = finiteOr(options.pitchCents, 0);
    const cadenceAnchor = clamp(
      Number.isFinite(options.cadence)
        ? options.cadence
        : lerp(finiteOr(previous.cadence, 0.5), 0.45 + (continuityScore * 0.35), 0.35),
      0,
      1
    );
    const cadenceShift = ((Math.random() - 0.5) * 0.04) * (0.7 + ((1 - continuityScore) * 0.3));
    let tempo = lerp(finiteOr(previous.tempo, baseTempo), baseTempo, 0.35) + cadenceShift;
    tempo = lerp(tempo, finiteOr(previous.tempo, tempo), 0.6);

    let emotionalTilt = lerp(
      finiteOr(previous.emotionalTilt, 0),
      detectTilt(options.text || ""),
      0.3
    );
    let pitchCents = lerp(
      finiteOr(previous.pitchBias, basePitchCents),
      basePitchCents + (emotionalTilt * 24),
      0.35
    );
    let volumeBoost = lerp(finiteOr(previous.energy, baseVolumeBoost), baseVolumeBoost, 0.35);
    const startupFadeMs = clamp(
      Math.round((finiteOr(options.startupFadeMs, 40) || 40) - (continuityScore * 12)),
      15,
      100
    );

    if (options.mode === "commit") {
      tempo = lerp(tempo, 1.0, 0.2);
      pitchCents *= 0.7;
      emotionalTilt *= 0.85;
    }

    return {
      continuityScore,
      cadence: cadenceAnchor,
      emotionalTilt: clamp(emotionalTilt, -1, 1),
      tempo: clamp(tempo, 0.9, 1.08),
      volumeBoost: clamp(volumeBoost, 0.86, 1.1),
      pitchCents: clamp(pitchCents, -40, 40),
      startupFadeMs,
    };
  }

  async _renderReleaseClip(inputPath, outputPath, options = {}) {
    const tailMs = Number.isFinite(options.tailMs) ? options.tailMs : 120;
    const fadeMs = Number.isFinite(options.fadeMs) ? options.fadeMs : 90;
    const pitchCents = Number.isFinite(options.pitchCents) ? options.pitchCents : -50;
    const tempo = Number.isFinite(options.tempo) ? options.tempo : 0.95;
    const lowpassHz = Number.isFinite(options.lowpassHz) ? options.lowpassHz : 5200;
    const volume = Number.isFinite(options.volume) ? options.volume : 0.95;

    const duration = await this._getAudioDurationSeconds(inputPath);
    const tailSeconds = Math.max(tailMs / 1000, 0.02);
    const startSeconds = Math.max(0, duration - tailSeconds);
    const fadeSeconds = Math.min(fadeMs / 1000, tailSeconds);

    await new Promise((resolve, reject) => {
      const args = [
        "-q",
        "-v",
        String(volume),
        inputPath,
        outputPath,
        "trim",
        startSeconds.toFixed(3),
        tailSeconds.toFixed(3),
        "fade",
        "t",
        "0",
        tailSeconds.toFixed(3),
        fadeSeconds.toFixed(3),
        "pitch",
        String(pitchCents),
        "tempo",
        "-s",
        tempo.toFixed(2),
        "lowpass",
        String(lowpassHz),
      ];
      const child = spawn(this.config.soxPath, args, { stdio: ["ignore", "pipe", "pipe"] });
      let stderr = "";
      child.stderr.on("data", (chunk) => {
        stderr += chunk.toString();
      });
      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0) resolve();
        else reject(new Error(stderr.trim() || `SoX release shaping failed (exit ${code})`));
      });
    });
  }

  async _cacheContinuationClip(inputPath, options = {}) {
    await fs.mkdir(this.config.tempDir, { recursive: true });
    const nextPath = path.join(
      this.config.tempDir,
      `tts-continuation-${Date.now()}-${Math.random().toString(16).slice(2, 8)}.wav`
    );
    const previousPath = this.lastContinuationPath;

    await new Promise((resolve, reject) => {
      const args = [
        "-q",
        "-v",
        String(options.volume ?? 0.85),
        inputPath,
        nextPath,
        "trim",
        "0",
        `${Math.max((options.tailMs ?? 100) / 1000, 0.03).toFixed(3)}`,
        "tempo",
        "-s",
        `${Number.isFinite(options.tempo) ? options.tempo.toFixed(2) : "0.97"}`,
        "pitch",
        String(Number.isFinite(options.pitchCents) ? options.pitchCents : -10),
        "lowpass",
        String(Number.isFinite(options.lowpassHz) ? options.lowpassHz : 3000),
        "fade",
        "t",
        "0",
        `${Math.max((options.tailMs ?? 100) / 1000, 0.03).toFixed(3)}`,
        `${Math.max(Math.min((options.fadeMs ?? 80) / 1000, (options.tailMs ?? 100) / 1000), 0.02).toFixed(3)}`,
      ];
      const child = spawn(this.config.soxPath, args, { stdio: ["ignore", "pipe", "pipe"] });
      let stderr = "";
      child.stderr.on("data", (chunk) => {
        stderr += chunk.toString();
      });
      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0) {
          resolve();
        } else {
          reject(new Error(stderr.trim() || `SoX continuation render failed (exit ${code})`));
        }
      });
    });

    this.lastContinuationPath = nextPath;
    if (previousPath && previousPath !== nextPath) {
      await fs.rm(previousPath, { force: true }).catch(() => {});
    }
  }

  _getAudioDurationSeconds(inputPath) {
    return new Promise((resolve, reject) => {
      const child = spawn(this.config.soxPath, ["--i", "-D", inputPath], { stdio: ["ignore", "pipe", "pipe"] });
      let stdout = "";
      let stderr = "";
      child.stdout.on("data", (chunk) => {
        stdout += chunk.toString();
      });
      child.stderr.on("data", (chunk) => {
        stderr += chunk.toString();
      });
      child.on("error", reject);
      child.on("close", (code) => {
        if (code !== 0) {
          reject(new Error(stderr.trim() || `SoX duration probe failed (exit ${code})`));
          return;
        }
        const value = Number.parseFloat(stdout.trim());
        if (!Number.isFinite(value)) {
          reject(new Error(`SoX duration probe returned "${stdout.trim()}"`));
          return;
        }
        resolve(value);
      });
    });
  }

  _xttsAvailable() {
    return fsSync.existsSync(this.config.xttsWorkerPath);
  }

  _shouldUseOpenAiTts(options = {}) {
    if (this.config.freeOnlyProviders) {
      return false;
    }

    if (!this.config.openAiApiKey) {
      return false;
    }

    const policy = (options.onlinePolicy || this.config.onlinePolicy || "").toLowerCase();
    return policy === "auto" || policy === "online-only";
  }

  _shouldUseElevenLabs(options = {}) {
    if (this.config.freeOnlyProviders) {
      return false;
    }

    if (!this.config.elevenlabsApiKey || !this.config.elevenlabsVoiceId) {
      return false;
    }

    const policy = (options.onlinePolicy || this.config.onlinePolicy || "").toLowerCase();
    return policy === "auto" || policy === "online-only";
  }

  _prefersPremiumVoicePath(options = {}) {
    const tier = String(options.runtimeTier || this.config.runtimeTier || "").toLowerCase();
    return tier === "paid";
  }

  _buildSpeechInstructions(prosody = {}, options = {}) {
    if (options.preserveEmotion === false && (!prosody || typeof prosody !== "object")) {
      return "";
    }

    const hints = [];
    const rate = Number.isFinite(prosody?.speaking_rate)
      ? prosody.speaking_rate
      : Number.isFinite(prosody?.speakingRate)
        ? prosody.speakingRate
        : null;
    const pitchMean = Number.isFinite(prosody?.pitch_mean)
      ? prosody.pitch_mean
      : Number.isFinite(prosody?.pitchMean)
        ? prosody.pitchMean
        : null;
    const energyMean = Number.isFinite(prosody?.energy_mean)
      ? prosody.energy_mean
      : Number.isFinite(prosody?.energyMean)
        ? prosody.energyMean
        : null;
    const voiceIdentityProfile = options?.voiceIdentityProfile && typeof options.voiceIdentityProfile === "object"
      ? options.voiceIdentityProfile
      : null;

    if (rate !== null) {
      if (rate > 1.1) hints.push("speak briskly");
      else if (rate < 0.9) hints.push("speak more calmly and slightly slower");
      else hints.push("keep a natural conversational pace");
    }

    if (pitchMean !== null) {
      if (pitchMean > 190) hints.push("keep a brighter higher-pitch tone");
      else if (pitchMean < 120) hints.push("keep a deeper lower-pitch tone");
    }

    if (energyMean !== null) {
      if (energyMean > 0.12) hints.push("maintain energetic emphasis");
      else if (energyMean < 0.05) hints.push("maintain a softer controlled delivery");
    }

    if (voiceIdentityProfile) {
      const f0Mean = Number.isFinite(voiceIdentityProfile.f0Mean) ? voiceIdentityProfile.f0Mean : null;
      const tilt = Number.isFinite(voiceIdentityProfile.tilt) ? voiceIdentityProfile.tilt : null;
      if (f0Mean !== null) {
        if (f0Mean > 185) hints.push("keep the speaker's naturally lighter pitch center");
        else if (f0Mean < 130) hints.push("keep the speaker's naturally deeper pitch center");
      }
      if (tilt !== null) {
        if (tilt > 0.2) hints.push("keep a brighter forward resonance");
        else if (tilt < -0.2) hints.push("keep a warmer darker resonance");
      }
    }

    if (!hints.length) {
      return "Speak naturally and preserve the source speaker tone and emotion as closely as possible.";
    }

    return `Speak naturally and preserve the source speaker tone and emotion. ${hints.join(". ")}.`;
  }

  stop() {
    this.edge.stop();
    this.sapi.stop();
    this.prosodyEngine.stop();
    this.stopPresence();
    for (const stream of this.audioStreams.values()) {
      stream.close();
    }
    this.audioStreams.clear();
    const continuationPath = this.lastContinuationPath;
    this.lastContinuationPath = "";
    if (continuationPath) {
      void fs.rm(continuationPath, { force: true }).catch(() => {});
    }
  }

  getStatistics() {
    return {};
  }
}

module.exports = { TieredSpeechEngine };

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function finiteOr(value, fallback) {
  return Number.isFinite(value) ? value : fallback;
}

function lerp(a, b, t) {
  return a + ((b - a) * t);
}

function detectTilt(text) {
  if (typeof text !== "string") {
    return 0;
  }
  const normalized = text.trim();
  if (!normalized) {
    return 0;
  }
  if (normalized.includes("!")) {
    return 0.4;
  }
  if (normalized.includes("?")) {
    return 0.2;
  }
  if (normalized.length < 5) {
    return -0.2;
  }
  return 0;
}
