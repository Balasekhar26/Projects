import sys
import json

args = json.loads(sys.argv[1])
result = {"echoed_args": args, "status": "processed_in_sandbox"}
print(json.dumps(result))
