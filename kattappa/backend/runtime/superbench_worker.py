"""Isolated RuntimeEngine worker used by Superbench."""

from __future__ import annotations

import contextlib
import io
import json
import sys


def main() -> int:
    request = json.load(sys.stdin)
    prompt = str(request["prompt"])
    diagnostic_output = io.StringIO()
    with contextlib.redirect_stdout(diagnostic_output):
        from backend.runtime.runtime_engine import RuntimeEngine

        result = RuntimeEngine().boot(prompt)
    if diagnostic_output.getvalue():
        print(diagnostic_output.getvalue(), file=sys.stderr, end="")
    json.dump(result, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
