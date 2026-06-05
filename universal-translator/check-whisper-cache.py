#!/usr/bin/env python3
from faster_whisper import WhisperModel
import os
import pathlib

print('Loading Whisper with CPU...')
try:
    model = WhisperModel('tiny', device='cpu')
    print('✓ Whisper model ready')
except Exception as e:
    print(f'✗ Error loading Whisper: {e}')

cache_dir = os.path.expanduser('~/.cache/faster_whisper')
print(f'\nCache location: {cache_dir}')
print('Cached files:')

if os.path.exists(cache_dir):
    items = sorted(list(pathlib.Path(cache_dir).rglob('*')))
    if not items:
        print('  (empty)')
    else:
        for p in items[:50]:  # Limit to first 50 items
            rel = p.relative_to(cache_dir)
            if p.is_file():
                try:
                    size = os.path.getsize(p)
                    print(f'  {rel} ({size} bytes)')
                except:
                    print(f'  {rel} (error reading size)')
            else:
                print(f'  {rel}/')
    
    # Check preprocessor config specifically
    preproc_config = pathlib.Path(cache_dir) / 'tiny.en' / 'preprocessor_config.json'
    if preproc_config.exists():
        print(f'\n✓ Preprocessor config found at: {preproc_config}')
        print(f'  Size: {os.path.getsize(preproc_config)} bytes')
        with open(preproc_config, 'r') as f:
            content = f.read()
            if content.strip():
                print(f'  Content: {content[:200]}...')
            else:
                print('  ✗ File is empty!')
    else:
        print(f'\n✗ Preprocessor config NOT found at expected location')
else:
    print('  (cache directory does not exist)')
