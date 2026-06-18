import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

def free_translate(text: str, target_lang: str = "hi") -> str:
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={urllib.parse.quote(text)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            return "".join(part[0] for part in data[0] if part[0])
    except Exception:
        return text

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No input file specified"}))
        return 1

    input_file = Path(sys.argv[1]).resolve()
    target_lang = sys.argv[2] if len(sys.argv) > 2 else "te"

    if not input_file.exists():
        print(json.dumps({"error": f"Input file not found: {input_file}"}))
        return 1

    try:
        # Import faster_whisper
        from faster_whisper import WhisperModel
        
        # Load model (using CPU for universal compatibility)
        model = WhisperModel('tiny', device='cpu', compute_type='int8')
        
        segments, info = model.transcribe(str(input_file), beam_size=5)
        
        results = []
        for segment in segments:
            translated = free_translate(segment.text, target_lang)
            results.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip(),
                "translated": translated.strip()
            })

        print(json.dumps({
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": round(info.duration, 2),
            "segments": results
        }, indent=2))
        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return 1

if __name__ == "__main__":
    sys.exit(main())
