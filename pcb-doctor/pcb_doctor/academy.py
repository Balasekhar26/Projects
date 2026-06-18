from __future__ import annotations

import sys
from typing import Any

class DiagnosticsAcademy:
    def __init__(self) -> None:
        self.lessons = [
            {
                "title": "Lesson 1: Multi-Meter Basics",
                "question": "What is the expected behavior when measuring a short circuit to ground on a power rail?",
                "options": [
                    "A) Resistance is close to 0 ohms",
                    "B) Voltage matches input voltage",
                    "C) Current drops to zero"
                ],
                "answer": "A",
                "explanation": "A short circuit offers path of least resistance, driving resistance to near 0 ohms."
            },
            {
                "title": "Lesson 2: SystemVerilog Logic Simulation",
                "question": "Which simulation command runs the Upstream Matrix multiplication in tiny-gpu?",
                "options": [
                    "A) run --matrix-multiply",
                    "B) make sim",
                    "C) python -m tiny_gpu_lab run-sim"
                ],
                "answer": "B",
                "explanation": "The standard Upstream Matrix Makefile executes simulation compilation using 'make sim'."
            },
            {
                "title": "Lesson 3: PCB Diagnostics & Trace Upstream",
                "question": "If you observe a voltage drop from 5.0V to 1.2V on the primary rail, what is the best first step?",
                "options": [
                    "A) Replace the main capacitor immediately",
                    "B) Trace upstream to verify regulator output capability",
                    "C) Short the rail to force system boot"
                ],
                "answer": "B",
                "explanation": "Always trace upstream from point of failure to isolate whether source supply is functioning correctly."
            }
        ]

    def launch_interactive_shell(self) -> None:
        print("==========================================================")
        print("          PCB DOCTOR - DIAGNOSTICS ACADEMY (MIMO)         ")
        print("==========================================================\n")
        print("Welcome! Complete the interactive electronics training lessons below.\n")

        score = 0
        for idx, lesson in enumerate(self.lessons):
            print(f"--- {lesson['title']} ---")
            print(lesson["question"])
            for opt in lesson["options"]:
                print(f"  {opt}")
            
            user_ans = input("\nYour answer (A/B/C): ").strip().upper()
            if user_ans == lesson["answer"]:
                print("✓ Correct! " + lesson["explanation"] + "\n")
                score += 1
            else:
                print(f"✗ Incorrect. The correct answer was {lesson['answer']}. " + lesson["explanation"] + "\n")

        print(f"Academy session complete. Score: {score}/{len(self.lessons)}")
