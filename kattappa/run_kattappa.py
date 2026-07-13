import sys
from backend.runtime.runtime_engine import RuntimeEngine

def main():
    query = "Book a meeting tomorrow at 3 PM with engineering and remind me one hour before."
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])

    engine = RuntimeEngine()
    result = engine.boot(query)

    print("\n--- RUNTIME CONSOLE OUTPUT ---")
    print(f"User Input:\n\"{query}\"\n")
    
    print("Runtime Trace:")
    for idx, trace_step in enumerate(result["trace"], 1):
        print(f"  {idx}. {trace_step}")

    print("\nFinal Response:")
    print(f"  \"{result['response']}\"")
    print("--------------------------------------------------------------------------------")

if __name__ == "__main__":
    main()
