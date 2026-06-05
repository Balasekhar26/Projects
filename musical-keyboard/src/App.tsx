import { useEffect, useRef, useState, useCallback } from 'react'

// Full keyboard mapping - maps almost every key to a musical note
const KEYBOARD_MAPPING: Record<string, number> = {
  // Numbers 1-0
  '1': 261.63, '2': 277.18, '3': 293.66, '4': 311.13, '5': 329.63,
  '6': 349.23, '7': 369.99, '8': 392.00, '9': 415.30, '0': 440.00,
  
  // Q-P row
  'q': 466.16, 'w': 493.88, 'e': 523.25, 'r': 554.37, 't': 587.33,
  'y': 622.25, 'u': 659.25, 'i': 698.46, 'o': 739.99, 'p': 783.99,
  
  // A-L row  
  'a': 830.61, 's': 880.00, 'd': 932.33, 'f': 987.77, 'g': 1046.50,
  'h': 1108.73, 'j': 1174.66, 'k': 1244.51, 'l': 1318.51,
  
  // Z-M row
  'z': 1396.91, 'x': 1479.98, 'c': 1567.98, 'v': 1661.22, 'b': 1760.00,
  'n': 1864.66, 'm': 1975.53,
  
  // Special keys
  ',': 2093.00, '.': 2217.46, '/': 2349.63,
  
  // Space and enter
  ' ': 2489.02, 'enter': 2637.02
}

// Instrument configurations with different sound characteristics
const INSTRUMENTS = {
  piano: {
    type: 'triangle' as OscillatorType,
    attack: 0.01,
    decay: 0.1,
    sustain: 0.3,
    release: 0.5,
    volume: 0.4
  },
  guitar: {
    type: 'sawtooth' as OscillatorType,
    attack: 0.02,
    decay: 0.3,
    sustain: 0.2,
    release: 0.8,
    volume: 0.3
  },
  flute: {
    type: 'sine' as OscillatorType,
    attack: 0.1,
    decay: 0.05,
    sustain: 0.7,
    release: 0.3,
    volume: 0.5
  },
  synth: {
    type: 'square' as OscillatorType,
    attack: 0.001,
    decay: 0.1,
    sustain: 0.1,
    release: 0.2,
    volume: 0.2
  },
  violin: {
    type: 'triangle' as OscillatorType,
    attack: 0.05,
    decay: 0.2,
    sustain: 0.5,
    release: 0.4,
    volume: 0.35
  }
}

type ActiveVoice = {
  oscillator: OscillatorNode
  gain: GainNode
  createdAt: number
}

const MAX_VOICES = 16

function normalizeKey(input: string): string {
  const key = input.toLowerCase()
  if (key === 'space' || key === ' ') return ' '
  if (key === 'enter') return 'enter'
  return key
}

export default function App() {
  const [instrument, setInstrument] = useState<keyof typeof INSTRUMENTS>('piano')
  const [activeKeys, setActiveKeys] = useState<Set<string>>(new Set())
  const [isAudioSupported, setIsAudioSupported] = useState(true)
  const audioContextRef = useRef<AudioContext | null>(null)
  const activeVoicesRef = useRef<Map<string, ActiveVoice>>(new Map())

  const releaseVoice = useCallback((key: string, releaseSeconds = 0.08) => {
    const normalizedKey = normalizeKey(key)
    const voice = activeVoicesRef.current.get(normalizedKey)
    const ctx = audioContextRef.current
    if (!voice || !ctx) return

    try {
      const now = ctx.currentTime
      voice.gain.gain.cancelScheduledValues(now)
      voice.gain.gain.setValueAtTime(Math.max(voice.gain.gain.value, 0.001), now)
      voice.gain.gain.exponentialRampToValueAtTime(0.001, now + releaseSeconds)
      voice.oscillator.stop(now + releaseSeconds + 0.01)
    } catch (e) {
      // Ignore already-stopped voices.
    }
    activeVoicesRef.current.delete(normalizedKey)
  }, [])

  const stopAllNotes = useCallback(() => {
    for (const key of [...activeVoicesRef.current.keys()]) {
      releaseVoice(key, 0.03)
    }
    setActiveKeys(new Set())
  }, [releaseVoice])

  // Initialize audio context
  useEffect(() => {
    try {
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext
      if (!AudioContextClass) {
        setIsAudioSupported(false)
        return
      }
      
      audioContextRef.current = new AudioContextClass()
      
      // Resume audio context if suspended (for autoplay policies)
      if (audioContextRef.current.state === 'suspended') {
        audioContextRef.current.resume()
      }
    } catch (error) {
      console.error('Audio context initialization failed:', error)
      setIsAudioSupported(false)
    }

    return () => {
      // Cleanup on unmount
      stopAllNotes()
      
      if (audioContextRef.current) {
        audioContextRef.current.close()
      }
    }
  }, [stopAllNotes])

  // Play note function
  const playNote = useCallback((frequency: number, key: string) => {
    if (!audioContextRef.current || !isAudioSupported) return

    const ctx = audioContextRef.current
    if (ctx.state === 'suspended') {
      void ctx.resume()
    }
    const config = INSTRUMENTS[instrument]
    const normalizedKey = normalizeKey(key)

    if (activeVoicesRef.current.has(normalizedKey)) return

    if (activeVoicesRef.current.size >= MAX_VOICES) {
      let oldestKey = ''
      let oldestTime = Number.POSITIVE_INFINITY
      for (const [voiceKey, voice] of activeVoicesRef.current.entries()) {
        if (voice.createdAt < oldestTime) {
          oldestKey = voiceKey
          oldestTime = voice.createdAt
        }
      }
      if (oldestKey) {
        releaseVoice(oldestKey, 0.03)
      }
    }

    // Create new oscillator
    const oscillator = ctx.createOscillator()
    const gainNode = ctx.createGain()

    // Configure oscillator
    oscillator.type = config.type
    oscillator.frequency.value = frequency

    // Configure gain envelope
    const now = ctx.currentTime
    gainNode.gain.setValueAtTime(0, now)
    gainNode.gain.linearRampToValueAtTime(config.volume, now + config.attack)
    gainNode.gain.linearRampToValueAtTime(config.volume * config.sustain, now + config.attack + config.decay)

    // Connect nodes
    oscillator.connect(gainNode)
    gainNode.connect(ctx.destination)

    // Start oscillator
    oscillator.start(now)

    // Store reference
    activeVoicesRef.current.set(normalizedKey, { oscillator, gain: gainNode, createdAt: now })

    // Clean up after stop
    oscillator.onended = () => {
      const current = activeVoicesRef.current.get(normalizedKey)
      if (current?.oscillator === oscillator) {
        activeVoicesRef.current.delete(normalizedKey)
      }
      setActiveKeys(prev => {
        const newSet = new Set(prev)
        newSet.delete(normalizedKey)
        return newSet
      })
    }

    // Mark key as active
    setActiveKeys(prev => new Set(prev).add(normalizedKey))
  }, [instrument, isAudioSupported, releaseVoice])

  // Stop note function
  const stopNote = useCallback((key: string) => {
    const normalizedKey = normalizeKey(key)
    const voice = activeVoicesRef.current.get(normalizedKey)
    if (voice && audioContextRef.current) {
      releaseVoice(normalizedKey)
    }
    
    setActiveKeys(prev => {
      const newSet = new Set(prev)
      newSet.delete(normalizedKey)
      return newSet
    })
  }, [releaseVoice])

  // Keyboard event handlers
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Prevent repeating keys
      if (e.repeat) return
      
      const key = normalizeKey(e.key)
      if (KEYBOARD_MAPPING[key]) {
        e.preventDefault()
        if (activeVoicesRef.current.has(key)) return
        playNote(KEYBOARD_MAPPING[key], key)
      }
    }

    const handleKeyUp = (e: KeyboardEvent) => {
      const key = normalizeKey(e.key)
      if (KEYBOARD_MAPPING[key]) {
        e.preventDefault()
        stopNote(key)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('keyup', handleKeyUp)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('keyup', handleKeyUp)
    }
  }, [playNote, stopNote])

  useEffect(() => {
    const handleBlur = () => stopAllNotes()
    const handleVisibilityChange = () => {
      if (document.hidden) stopAllNotes()
    }

    window.addEventListener('blur', handleBlur)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      window.removeEventListener('blur', handleBlur)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [stopAllNotes])

  // Pointer handlers for on-screen keys
  const handlePointerDown = (key: string, frequency: number) => {
    const normalizedKey = normalizeKey(key)
    playNote(frequency, normalizedKey)
  }

  const handlePointerUp = (key: string) => {
    stopNote(normalizeKey(key))
  }

  // Organize keys for display
  const keyRows = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
    ['z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/'],
    ['Space', 'Enter']
  ]

  if (!isAudioSupported) {
    return (
      <div className="min-h-screen bg-red-50 flex items-center justify-center p-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-600 mb-4">Audio Not Supported</h1>
          <p className="text-red-700">Your browser doesn't support Web Audio API. Please use a modern browser.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-purple-50 p-4 md:p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl md:text-5xl font-bold text-gradient mb-4">
            Cross-Platform Instrument Keyboard
          </h1>
          <p className="text-gray-600 text-lg">
            Works offline • Full keyboard support • Touch enabled
          </p>
        </div>

        {/* Instrument Selector */}
        <div className="flex justify-center mb-8">
          <div className="bg-white rounded-2xl shadow-xl p-6">
            <label className="block text-sm font-semibold text-gray-700 mb-3">
              Select Instrument
            </label>
            <select
              value={instrument}
              onChange={(e) => setInstrument(e.target.value as keyof typeof INSTRUMENTS)}
              className="instrument-selector"
            >
              {Object.keys(INSTRUMENTS).map((name) => (
                <option key={name} value={name}>
                  {name.charAt(0).toUpperCase() + name.slice(1)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Keyboard Layout */}
        <div className="bg-white rounded-2xl shadow-xl p-6 md:p-8">
          <div className="space-y-3">
            {keyRows.map((row, rowIndex) => (
              <div key={rowIndex} className="flex justify-center gap-2">
                {row.map((key) => {
                  const normalizedKey = normalizeKey(key)
                  const displayKey = normalizedKey === ' ' ? 'Space' : normalizedKey === 'enter' ? 'Enter' : key.toUpperCase()
                  const frequency = KEYBOARD_MAPPING[normalizedKey]
                  const isActive = activeKeys.has(normalizedKey)
                  
                  return (
                    <button
                      key={key}
                      onPointerDown={(e) => {
                        e.preventDefault()
                        handlePointerDown(normalizedKey, frequency)
                      }}
                      onPointerUp={() => handlePointerUp(normalizedKey)}
                      onPointerCancel={() => handlePointerUp(normalizedKey)}
                      onPointerLeave={() => handlePointerUp(normalizedKey)}
                      className={`key-button ${isActive ? 'active' : ''} ${
                        normalizedKey === ' ' ? 'px-8' : normalizedKey === 'enter' ? 'px-6' : 'px-4'
                      } min-w-[3rem] md:min-w-[4rem]`}
                      disabled={!frequency}
                    >
                      {displayKey}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        </div>

        {/* Instructions */}
        <div className="mt-8 text-center">
          <div className="bg-white rounded-xl shadow-lg p-6 max-w-2xl mx-auto">
            <h2 className="text-lg font-semibold mb-3">How to Play</h2>
            <div className="text-gray-600 space-y-2">
              <p>🎹 <strong>Keyboard:</strong> Press any key from 1-0, Q-P, A-L, Z-M, Space, or Enter</p>
              <p>📱 <strong>Touch:</strong> Tap the on-screen keys</p>
              <p>🎵 <strong>Every key</strong> plays a different musical note</p>
              <p>🔄 <strong>Switch instruments</strong> to change the sound character</p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-sm text-gray-500">
          <p>Works offline as PWA • Cross-platform compatible</p>
          <p className="mt-1">Current instrument: <span className="font-semibold">{instrument}</span></p>
        </div>
      </div>
    </div>
  )
}
