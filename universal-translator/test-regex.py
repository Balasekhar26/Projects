#!/usr/bin/env python3
import re

# Test device names
devices = [
    "CABLE Output (VB-Audio Virtual",
    "CABLE Output (VB-Audio Virtual Cable)",
    "Voicemeeter Out B2 (VB-Audio Vo",
    "Microphone (2- High Definition",
    "Line 1 (Virtual Audio Cable)",
]

# Regex from pickDefaultInputDevice
pattern_system = r'cable output|voicemeeter output'
pattern_mic = r'cable|voicemeeter'

print("Testing SYSTEM mode (should match CABLE Output / Voicemeeter Out):")
print(f"Pattern: /{pattern_system}/i\n")
for device in devices:
    match = re.search(pattern_system, device, re.IGNORECASE)
    status = "✓ MATCH" if match else "✗ no match"
    print(f"  {status}: {device}")

print("\n\nTesting MICROPHONE mode (should exclude cable/voicemeeter):")
print(f"Pattern: !/{pattern_mic}/i\n")
for device in devices:
    match = re.search(pattern_mic, device, re.IGNORECASE)
    exclude = "✓ EXCLUDE" if match else "✗ INCLUDE"
    print(f"  {exclude}: {device}")
