#!/usr/bin/env python3
import subprocess
import json

result = subprocess.run(
    ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'tools/list-device-topology.ps1'],
    capture_output=True,
    text=True,
    cwd='.'
)

try:
    data = json.loads(result.stdout)
    print('INPUT DEVICES:')
    for d in data.get('inputDevices', []):
        print(f'  • {d["name"]}')
    
    print('\nOUTPUT DEVICES:')
    for d in data.get('outputDevices', []):
        print(f'  • {d["name"]}')
    
    print('\n--- ANALYSIS ---')
    input_names = [d["name"] for d in data.get('inputDevices', [])]
    cable_inputs = [n for n in input_names if 'cable' in n.lower() or 'voicemeeter' in n.lower()]
    print(f'VB-Cable/Voicemeeter inputs found: {cable_inputs if cable_inputs else "NONE"}')
    
except json.JSONDecodeError as e:
    print(f'JSON Error: {e}')
    print(f'Output: {result.stdout[:500]}')
except Exception as e:
    print(f'Error: {e}')
    if result.stderr:
        print(f'Stderr: {result.stderr}')
