# OneSetup Instrument Keyboard

Offline cross-platform instrument keyboard app.

## What It Does

- Runs on Android, iOS, Windows, macOS, Linux, ChromeOS, and other modern browser platforms.
- Works offline after the app files are available.
- Plays a note for every practical keyboard key: letters, numbers, symbols, arrows, function keys, modifiers, and numpad keys.
- Uses the selected instrument for every played note.
- Supports touch and mouse input from the on-screen keyboard.
- Uses the Web Audio API, so there are no downloaded samples or server calls.

## One Setup

Open:

```text
apps/instrument-keyboard/index.html
```

That is enough for normal offline use.

For installable PWA mode, serve this folder from any local static server or host it under HTTPS,
then open it in the browser and choose the browser's install option.

## Instrument Model

The app uses offline synthesized instruments:

- Piano
- Guitar
- Flute
- Organ
- Synth Lead
- Bass
- Bell

Every note is generated through the currently selected instrument model. To move to real recorded
instruments later, add note samples per instrument and replace `createVoice()` in `app.js` with a
sample player.

## Keyboard Notes

The mapping uses chromatic notes from the selected octave upward across the full keyboard layout.
Unknown keys still get a deterministic note by hashing the browser keyboard code.

Some OS-level shortcuts may not reach the browser, such as system-reserved function keys or global
window manager shortcuts. Any key event that the browser receives will play a note.
