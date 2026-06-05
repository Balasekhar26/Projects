# Animal Meaning Mode

This module connects Universal Translator to the downloaded BirdNET-Analyzer reference project:

```text
C:\Users\balu\Projects\external-projects\BirdNET-Analyzer
```

It should be presented as **animal sound meaning estimation**, not literal animal-to-English translation.

Suggested local setup:

```cmd
cd C:\Users\balu\Projects\external-projects\BirdNET-Analyzer
python -m pip install -e .
```

Example analysis command produced by the adapter:

```cmd
python -m birdnet_analyzer.analyze C:\audio\sample.wav -o C:\audio\birdnet-output --min_conf 0.5
```

