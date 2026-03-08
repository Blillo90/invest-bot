from flask import Flask, request, jsonify
import subprocess
import shutil
import os

app = Flask(__name__)

BASE_CMD = """
cd /home/ubuntu/quant-bot/worker && \
source .venv/bin/activate && \
set -a && source /home/ubuntu/quant-bot/config/bot.env && set +a && \
MODE={mode} python src/run_intraday.py
"""

@app.route("/run", methods=["POST"])
def run_bot():
    mode = request.json.get("mode", "close")
    cmd = f"bash -lc '{BASE_CMD.format(mode=mode)}'"

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    # Copiar reporte a carpeta permitida por n8n
    try:
        src = "/home/ubuntu/quant-bot/reports/latest.md"
        dst = "/home/ubuntu/n8n-files/reports/latest.md"
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(src, dst)
    except Exception:
        pass

    return jsonify({
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
