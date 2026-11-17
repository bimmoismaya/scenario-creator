"""Pengganti `claude`: perilaku dari env FAKE_MODE (ok|exit1|sleep|nospec)."""
import json
import os
import shutil
import sys
import time
from pathlib import Path

mode = os.environ.get("FAKE_MODE", "ok")
ex = Path(__file__).resolve().parent.parent / "assets/examples/example_spec.json"


def ev(o):
    print(json.dumps(o), flush=True)


ev({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {}}]}})
if mode == "exit1":
    print("not logged in: bob@example.com", file=sys.stderr)
    sys.exit(1)
if mode == "sleep":
    time.sleep(30)
if mode != "nospec":
    ev({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Write", "input": {}}]}})
    shutil.copyfile(ex, "spec.json")
ev({"type": "result", "is_error": False, "result": "ok"})
