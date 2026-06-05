# Musical Keyboard App

A cross-platform musical keyboard app that turns your computer keyboard into a musical instrument.

## Features

- 🎹 **Multi-Instrument Support**: Piano, Guitar, Violin, Flute, Synth
- ⌨️ **Full Keyboard Mapping**: Every key produces a musical note
- 🎵 **Octave Control**: Switch between different octaves
- 🔄 **Sustain Mode**: Hold notes sustain
- 📱 **Cross-Platform**: Windows, macOS, Linux, Android, iOS
- 🎨 **Beautiful UI**: Modern Material Design interface
- 🎯 **Visual Feedback**: See which keys are being pressed

## Key Mapping

### Primary Row (White Keys)
```
A → C     S → D     D → E     F → F     G → G
H → A     J → B     K → C     L → D     ; → E     ' → F
```

### Upper Row (Black Keys)
```
W → C#    E → D#    T → F#    Y → G#    U → A#
O → C#5   P → D#5
```

### Lower Row (Lower Octave)
```
Z → C3    X → D3    C → E3    V → F3    B → G3
N → A3    M → B3    , → C4    . → D4    / → E4
```

## How to Run

### Prerequisites
- Flutter SDK installed
- Android Studio (for mobile development)
- Xcode (for iOS development, macOS only)

### Setup and Run

```bash
# Navigate to the music keyboard directory
cd apps/music_keyboard

# Get dependencies
flutter pub get

# Run on web
flutter run -d web-server --web-port 3000

# Run on desktop (Windows/macOS/Linux)
flutter run -d windows    # or macos, linux

# Run on mobile
flutter run -d android     # or ios
```

### Build for Release

```bash
# Web build
flutter build web

# Windows build
flutter build windows

# Android build
flutter build apk
flutter build appbundle

# macOS build
flutter build macos

# Linux build
flutter build linux
```

## Project Structure

```
music_keyboard/
├── lib/
│   └── main.dart              # Main application
├── assets/
│   └── sounds/               # Audio samples
│       ├── piano/            # Piano sound samples
│       ├── guitar/           # Guitar sound samples
│       ├── violin/           # Violin sound samples
│       ├── flute/            # Flute sound samples
│       └── synth/            # Synth sound samples
├── pubspec.yaml              # Dependencies
└── README.md                # This file
```

## Instruments

### 🎹 Piano
- Classic piano sounds
- Full 88-key range mapping
- Realistic piano samples

### 🎸 Guitar
- Acoustic guitar tones
- Strum simulation
- Natural decay

### 🎻 Violin
- Classical violin sounds
- Bow articulation
- Expressive dynamics

### 🎺 Flute
- Clear flute tones
- Breath control simulation
- Pure harmonic sounds

### 🎛️ Synth
- Electronic synthesizer
- Multiple waveforms
- Modern electronic sounds

## Controls

- **Instrument Selector**: Choose between 5 instruments
- **Octave Control**: Switch octaves (1-7)
- **Sustain Toggle**: Enable/disable sustain pedal
- **Visual Keyboard**: See active keys highlighted

## Technical Details

### Audio Engine
- Uses `audioplayers` package for cross-platform audio
- Low-latency playback
- Sample-based audio generation

### Input Handling
- Raw keyboard event capture
- Multi-key support (chords)
- Key press/release tracking

### Performance
- Optimized for real-time audio
- Minimal latency (<50ms)
- Memory-efficient sample loading

## Development Notes

### Adding New Instruments
1. Add sound samples to `assets/sounds/[instrument]/`
2. Update `_instruments` list in `main.dart`
3. Ensure samples follow naming convention (C.mp3, D.mp3, etc.)

### Customizing Key Mapping
- Modify `_keyToNote` map in `main.dart`
- Add new key-note pairs as needed
- Test with actual keyboard input

### Audio Sample Requirements
- Format: MP3 or WAV
- Naming: Note name (e.g., C.mp3, D#.mp3)
- Quality: 44.1kHz, 16-bit recommended
- Duration: 2-3 seconds per note

## Troubleshooting

### Audio Not Playing
- Check if audio samples exist in assets folder
- Verify audio permissions on mobile devices
- Try running with `flutter run -v` for detailed logs

### Keys Not Responding
- Ensure app has focus (click on app window)
- Check if keyboard shortcuts are interfering
- Test with different keyboard layouts

### Performance Issues
- Reduce audio sample quality if needed
- Close other audio applications
- Check system resources

## Future Enhancements

- [ ] Recording functionality
- [ ] MIDI support
- [ ] Custom instrument loading
- [ ] Effects (reverb, delay, etc.)
- [ ] Chord detection and display
- [ ] Learning mode with tutorials
- [ ] Metronome integration

## License

This project is part of the ULT Translator ecosystem.

---

**Made with ❤️ using Flutter**
