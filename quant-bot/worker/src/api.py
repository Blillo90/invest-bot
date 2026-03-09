from flask import Flask, request, jsonify
import subprocess
import shutil
import os
import json
import re
from datetime import datetime, timezone

app = Flask(__name__)

BASE_CMD = """
cd /home/ubuntu/quant-bot/worker && \
source .venv/bin/activate && \
set -a && source /home/ubuntu/quant-bot/config/bot.env && set +a && \
MODE={mode} python src/run_intraday.py
"""

HISTORY_PATH = "/home/ubuntu/n8n-history/history.json"
REPORT_PATH = "/home/ubuntu/quant-bot/reports/latest.md"


def _num(s):
    if s is None:
        return None
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None


def _append_snapshot(mode: str):
    try:
        with open(REPORT_PATH, "r") as f:
            raw = f.read()
    except Exception:
        return

    pick = lambda pattern: (m.group(1) if (m := re.search(pattern, raw)) else None)

    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "slot": mode.upper(),
        "equityPre": _num(pick(r"Equity \(pre\): \*\*([0-9.]+)\*\*")),
        "equityPost": _num(pick(r"Equity \(post\): \*\*([0-9.]+)\*\*")),
        "cash": _num(pick(r"Cash: \*\*([0-9.]+)\*\*")),
        "exposurePct": _num(pick(r"Exposición: \*\*([-0-9.]+)%\*\*")),
        "drawdownPct": _num(pick(r"Drawdown \(vs pico\): \*\*([-0-9.]+)%\*\*")),
        "targetPerPos": _num(pick(r"Target por posición .*?: \*\*([0-9.]+)\*\*")),
    }

    try:
        with open(HISTORY_PATH, "r") as f:
            history = json.load(f)
        if not isinstance(history, list):
            history = []
    except Exception:
        history = []

    history.append(snapshot)

    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


@app.route("/run", methods=["POST"])
def run_bot():
    mode = request.json.get("mode", "close")
    cmd = f"bash -lc '{BASE_CMD.format(mode=mode)}'"

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        try:
            _append_snapshot(mode)
        except Exception:
            pass

    return jsonify({
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
