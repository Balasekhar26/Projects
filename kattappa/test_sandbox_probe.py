import sys
import json
import time

args = json.loads(sys.argv[1])
action = args.get("action", "echo")

if action == "echo":
    print(json.dumps({"status": "processed", "echoed": args}))

elif action == "read_blocked_file":
    # This will trigger sandboxed_open rejection if outside allowed paths
    try:
        with open(args["path"], "r") as f:
            content = f.read()
        print(json.dumps({"status": "read_success", "content": content}))
    except PermissionError as e:
        print(json.dumps({"status": "blocked", "reason": str(e)}))

elif action == "connect_network":
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("8.8.8.8", 53))
        print(json.dumps({"status": "connected"}))
    except PermissionError as e:
        print(json.dumps({"status": "blocked", "reason": str(e)}))

elif action == "allocate_memory":
    # Allocate a large amount of memory to test memory limits
    target_mb = int(args.get("target_mb", 50))
    data = bytearray(target_mb * 1024 * 1024)
    time.sleep(2)
    print(json.dumps({"status": "allocated", "mb": target_mb}))
