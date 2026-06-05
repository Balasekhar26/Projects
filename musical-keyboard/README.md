# Musical Keyboard

Offline-capable web/PWA musical keyboard with desktop Electron support and an older Flutter variant preserved in `flutter-version`.

## Run

```bat
setup.bat
run.exe
```

Or manually:

```bat
npm install
npm run dev
```

Open `http://localhost:5173`.

## Build

```bat
npm run build
```

The production web output is written to `dist`.

## Desktop Variant

The Electron desktop wrapper lives in `electron`.

```bat
run.exe
```

## Features

- Full keyboard support across number, letter, punctuation, space, and enter keys.
- Piano, guitar, flute, synth, and violin-style sounds.
- Touch controls for phones, tablets, and touch screens.
- Offline PWA build using a service worker.

## Structure

- `src` - React keyboard app.
- `public` - static web assets.
- `electron` - desktop wrapper.
- `flutter-version` - older Flutter version kept for reference.
