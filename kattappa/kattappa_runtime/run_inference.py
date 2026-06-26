import os
import sys
import argparse
import json

# Setup sys.path to resolve root imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from kattappa_runtime.loader import ModelLoader, Mode
from kattappa_runtime.prompt_builder import PromptBuilder
from kattappa_runtime.conversation import ConversationState
from kattappa_runtime.memory import DummyMemoryProvider
from kattappa_runtime.router import ToolRouter

# ANSI escape sequences for premium style aesthetics
C_BLUE = "\033[94m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_MAGENTA = "\033[95m"
C_RESET = "\033[0m"
C_BOLD = "\033[1m"

def print_splash():
    print(f"\n{C_BOLD}{C_CYAN}" + "="*70)
    print("  _  __    _   _____ _____  _   _____  _____    ___  ____  ".center(70))
    print(" | |/ /   / \\ |_   _|_   _|/ \\ |  _  \\|  _  \\  / _ \\/ ___| ".center(70))
    print(" | ' /   / _ \\  | |   | | / _ \\| |_') | |_') | | | | \\___ \\ ".center(70))
    print(" | . \\  / ___ \\ | |   | |/ ___ \\  __/|  __/  | |_| |___) |".center(70))
    print(" |_|\\_\\/_/   \\_\\|_|   |_/_/   \\_\\_|    |_|      \\___/|____/ ".center(70))
    print("="*70 + f"{C_RESET}")
    print(f"{C_BOLD}{C_BLUE} Kattappa-1B OS CLI Inference Console (KM-5) {C_RESET}".center(70))
    print(f" Type {C_GREEN}/help{C_RESET} for commands, or {C_GREEN}/exit{C_RESET} to close session.".center(70))
    print("="*70 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Kattappa Inference Runtime Console")
    parser.add_argument("--mode", type=str, default="mock", choices=["mock", "base", "lora"], help="Inference execution mode.")
    parser.add_argument("--model-id", type=str, default="Qwen/Qwen2.5-1.5B-Instruct", help="HuggingFace model ID.")
    parser.add_argument("--adapter-path", type=str, default="kattappa-lora-v1", help="Adapter path for LoRA weights.")
    args = parser.parse_args()

    print_splash()

    # 1. Initialize Loader
    loader = ModelLoader(mode=args.mode, model_id=args.model_id, adapter_path=args.adapter_path)
    loader.load_model()

    # 2. Initialize Infrastructure Layers
    prompt_builder = PromptBuilder()
    conv = ConversationState()
    memory_prov = DummyMemoryProvider()
    router = ToolRouter()

    print(f"\n{C_GREEN}Kattappa OS is ready.{C_RESET} Start your conversation:")
    
    while True:
        try:
            user_input = input(f"\n{C_BOLD}{C_GREEN}You:{C_RESET} ").strip()
            if not user_input:
                continue
                
            # Intercept CLI Commands
            if user_input.startswith("/"):
                cmd = user_input.split()[0].lower()
                if cmd == "/exit":
                    print(f"{C_CYAN}Goodbye Balu! Session closed.{C_RESET}")
                    break
                elif cmd == "/clear":
                    conv.clear()
                    print(f"{C_YELLOW}Conversation history cleared.{C_RESET}")
                    continue
                elif cmd == "/memory":
                    print(f"\n{C_BOLD}{C_MAGENTA}--- Persistent Memory Cache ---{C_RESET}")
                    for k, v in memory_prov.memory.items():
                        print(f"  {k}: {v}")
                    continue
                elif cmd == "/stats":
                    print(f"\n{C_BOLD}{C_CYAN}--- Session Statistics ---{C_RESET}")
                    print(f"  Session ID: {conv.session_id}")
                    print(f"  Total Turns: {len(conv.messages)}")
                    print(f"  Estimated Tokens: {conv.estimate_tokens()}")
                    continue
                elif cmd == "/tools":
                    print(f"\n{C_BOLD}{C_BLUE}--- Registered Tools ---{C_RESET}")
                    for t in router.tools.keys():
                        print(f"  - {t}")
                    continue
                elif cmd == "/help":
                    print(f"\n{C_BOLD}Available commands:{C_RESET}")
                    print("  /clear   - Resets context history")
                    print("  /memory  - Prints all facts in local memory file")
                    print("  /stats   - Shows active session tokens & turns")
                    print("  /tools   - Lists registered OS tool modules")
                    print("  /exit    - Closes inference console")
                    continue
                else:
                    print(f"Unknown command: {cmd}. Type /help for assistance.")
                    continue
            
            # Formulate prompt using history + memory context
            retrieved_facts = memory_prov.retrieve(user_input)
            prompt = prompt_builder.build_prompt(
                memory_context=retrieved_facts,
                conversation_history=conv.get_recent(),
                user_message=user_input
            )
            
            print(f"{C_YELLOW}Thinking...{C_RESET}")
            
            # Stream response generator
            response_chunks = []
            is_thinking = True
            
            for chunk in loader.generate_stream(prompt):
                # Format chunk print styles
                if is_thinking and "Answer:" in chunk:
                    # Split thinking block from final answer
                    is_thinking = False
                    print(f"\n{C_BOLD}{C_CYAN}Kattappa:{C_RESET} ", end="")
                    parts = chunk.split("Answer:")
                    # Print anything after Answer: in Cyan
                    ans_part = parts[-1].strip()
                    print(ans_part, end="", flush=True)
                    response_chunks.append(chunk)
                else:
                    if is_thinking:
                        # Print thinking stream in dim yellow
                        # Strip "Thinking:" keyword to look clean
                        clean_chunk = chunk.replace("Thinking:", "")
                        print(f"{C_YELLOW}{clean_chunk}{C_RESET}", end="", flush=True)
                    else:
                        print(f"{C_CYAN}{chunk}{C_RESET}", end="", flush=True)
                    response_chunks.append(chunk)
                    
            print() # end line
            
            full_response = "".join(response_chunks)
            
            # Execute tool routing check
            tool_result = router.parse_and_execute(full_response)
            if tool_result:
                print(f"{C_MAGENTA}[Tool Result] {tool_result['result']}{C_RESET}")
                
                # Check if it was a memory storage tool to dynamically update local provider
                # Standard format of tool output matching memory actions:
                # e.g., if we run search/clock or store facts
                if tool_result.get("tool") == "calculator":
                    ans_str = f"Result of equation is {tool_result['result'].get('result')}"
                    conv.add_message("user", user_input)
                    conv.add_message("assistant", f"{full_response}\n\nTool execution returned: {ans_str}")
                else:
                    conv.add_message("user", user_input)
                    conv.add_message("assistant", full_response)
            else:
                # Direct conversational reply
                # If memory updates, store them dynamically
                if "stored" in full_response.lower() or "store" in full_response.lower():
                    # Parse user input words to mock extract facts
                    words = user_input.split()
                    if len(words) > 2:
                        key = "user_detail"
                        val = user_input
                        memory_prov.store({key: val})
                        
                conv.add_message("user", user_input)
                conv.add_message("assistant", full_response)
                
            # History pruning check
            conv.prune_history()
            
        except KeyboardInterrupt:
            print(f"\n{C_CYAN}Session aborted. Goodbye!{C_RESET}")
            break
        except Exception as e:
            print(f"\n{C_BOLD}\033[91mError: {e}{C_RESET}")

if __name__ == "__main__":
    main()
