clear
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
exit
clear
docker --version
docker compose version
sudo apt install tree
clear
mkdir -p ~/quant-bot/{n8n,worker/src,data,reports,logs,config}
tree
cd quant-bot/
cd n8n/
sudo nano docker-compose.yml
cd ~/quant-bot/n8n
docker compose up -d
docker ps
exit
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
python3 -m venv ~/quant-bot/worker/.venv
source ~/quant-bot/worker/.venv/bin/activate
pip install -U pip
pip install yfinance pandas numpy duckdb pyarrow python-dateutil
cat > ~/quant-bot/config/bot.env << 'EOF'
# Rutas
TICKERS_FILE=/home/ubuntu/quant-bot/data/tickers.txt
DB_PATH=/home/ubuntu/quant-bot/data/market.duckdb
REPORTS_DIR=/home/ubuntu/quant-bot/reports

# Simulación
START_CASH=100000
MAX_POSITIONS=20
MAX_EXPOSURE_PCT=0.95
MIN_POSITION_USD=1000

# Fricción (aprox)
FEE_BPS=10
SLIPPAGE_BPS=10

# Señales
BUY_TOP_PCT=0.10
SELL_OUT_PCT=0.30
MAX_REPLACEMENTS_PER_DAY=5

# Histórico inicial (para la primera carga)
HISTORY_YEARS=3
EOF

chmod 600 ~/quant-bot/config/bot.env
cat > ~/quant-bot/data/tickers.txt << 'EOF'
AAPL
MSFT
NVDA
AMZN
META
GOOGL
TSLA
JPM
UNH
XOM
CVX
BRK-B
LLY
V
MA
HD
PG
KO
PEP
COST
WMT
AMD
INTC
NFLX
CRM
ADBE
CSCO
ORCL
BAC
DIS
EOF

cd quant-bot/
cd worker/
cd src/
sudo nano run_daily.py
ls
nano run_daily.py
chmod +x ~/quant-bot/worker/src/run_daily.py
cd ~/quant-bot/worker
source .venv/bin/activate
set -a
source /home/ubuntu/quant-bot/config/bot.env
set +a
python src/run_daily.py
cat /home/ubuntu/quant-bot/reports/latest.md | head -n 40
cd ~/quant-bot/worker/src
nano run_intraday.py
chmod +x ~/quant-bot/worker/src/run_intraday.py
exit
clear
cd ~/quant-bot/n8n
nano docker-compose.yml
sudo nano docker-compose.yml
docker compose down
docker compose up -d
cd ~/quant-bot/worker
source .venv/bin/activate
pip install flask
cd ~/quant-bot/worker/src
nano api.py
cd ~/quant-bot/worker
source .venv/bin/activate
python src/api.py
exit
python src/api.py
exit
sudo systemctl status quantbot --no-pager
sudo journalctl -u quantbot -n 200 --no-pager
sudo systemctl status quantbot --no-pager
clear
curl -X POST http://127.0.0.1:5000/run -H "Content-Type: application/json" -d '{"mode":"open"}'
sudo nano /etc/systemd/system/quantbot.service
sudo systemctl daemon-reload
sudo systemctl enable quantbot
sudo systemctl start quantbot
sudo systemctl status quantbot --no-pager
sudo journalctl -u quantbot -n 200 --no-pager
sudo ss -ltnp | grep :5000 || true
sudo systemctl stop quantbot
sudo kill 6698
sudo ss -ltnp | grep :5000 || true
sudo systemctl start quantbot
sudo systemctl status quantbot --no-pager
curl -X POST http://127.0.0.1:5000/run -H "Content-Type: application/json" -d '{"mode":"open"}'
docker ps
nano /home/ubuntu/quant-bot/worker/src/api.py
sudo ufw allow from 127.0.0.1 to any port 5000
sudo ufw deny 5000
sudo systemctl restart quantbot
sudo systemctl status quantbot --no-pager
sudo ss -ltnp | grep :5000
ip addr show docker0 | grep "inet "
ls -l /home/ubuntu/quant-bot/reports/latest.md
docker ps
docker exec -it 04365122da36 ls -l /home/node/quant-bot/reports/latest.md
mkdir -p /home/ubuntu/n8n-files
nano ~/quant-bot/n8n/docker-compose.yml
sudo nano ~/quant-bot/n8n/docker-compose.yml
cd ~/quant-bot/n8n
docker compose down
docker compose up -d
nano /home/ubuntu/quant-bot/worker/src/api.py
sudo systemctl restart quantbot
curl -X POST http://127.0.0.1:5000/run -H "Content-Type: application/json" -d '{"mode":"open"}'
nano /home/ubuntu/quant-bot/worker/src/api.py
sudo systemctl restart quantbot
sudo nano /home/ubuntu/quant-bot/worker/src/api.py
nano /home/ubuntu/quant-bot/worker/src/api.py
/home/ubuntu/quant-bot/worker/.venv/bin/python -m py_compile /home/ubuntu/quant-bot/worker/src/api.py
sudo systemctl restart quantbot
sudo systemctl status quantbot --no-pager
curl -X POST http://127.0.0.1:5000/run -H "Content-Type: application/json" -d '{"mode":"open"}'
ls -l /home/ubuntu/n8n-files/latest.md
ssh -i ./invest-bot-aws-key.pem -L 5678:127.0.0.1:5678 ubuntu@51.21.196.41
exit
ls -la /home/ubuntu/n8n-files
docker exec -it n8n ls -la /home/node/.n8n-files
clear
sudo nano /etc/systemd/system/quantbot.service
sudo systemctl status quantbot
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker logs -n 50 n8n-n8n-1
docker volume ls | grep n8n
docker inspect n8n_data | head
docker inspect n8n-n8n-1 --format '{{json .Mounts}}'
docker logs -n 200 n8n-n8n-1 | tail -n 80
docker logs -n 200 n8n-n8n-1 | grep -i cron
openssl rand -hex 32
cd n8n-files/
ls
cd ..
cd quant-bot/
ls
cd n8n/
ls
sudo nano docker-compose.yml 
docker compose down
docker compose up -d
docker exec -it n8n date
docker logs -n 200 n8n | grep -i cron
clear
docker compose down
docker volume rm n8n_n8n_data
docker compose up -d
docker exec -it n8n sh
docker logs -n 200 n8n | grep -i cron
sudo nano docker-compose.yml 
docker compose down
docker compose up -d
docker logs -n 100 n8n | grep -i encryption
docker ps
docker logs -n 200 n8n | grep -i cron
docker logs -f n8n
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
cat /home/ubuntu/n8n-files/history.json | head
ls -la /home/ubuntu/n8n-files
cat /home/ubuntu/n8n-files/history.json | head
echo "[]" > /home/ubuntu/n8n-files/history.json
cat /home/ubuntu/n8n-files/history.json
head -n 5 /home/ubuntu/n8n-files/history.json
head -n 10 /home/ubuntu/n8n-files/history.json
clear
cd /home/ubuntu/dashboard/invest-dashboard
pwd
ls
ls -la src/app/api/history
ls -la src/app/api/history/route.ts
ls -la src/app
curl -i http://127.0.0.1:3000/api/history
clear
cd /home/ubuntu/dashboard/invest-dashboard
ls -la src/app/api/history
curl -i http://127.0.0.1:3000/api/history
clear
mkdir -p app/api/history
nano route.ts
rm -rf src/app/api/history
curl -s http://127.0.0.1:3000/api/history | head
clear
curl -s http://127.0.0.1:3000/api/history | head
clear
ls -la app/api/history
ls -la src/app/api/history
curl -s http://127.0.0.1:3000/api/history | head
clear
cd /home/ubuntu/dashboard/invest-dashboard
pwd
ls
ls -la app/api/history
mkdir -p app/api/history
ls
cd app/api
ls
cd history/
ls
nano route.ts
ls
cd /home/ubuntu/dashboard/invest-dashboard
npm i recharts
cd app
cd lib
mkdir lib
nano api.ts
mkdir -p app/lib
cat > app/lib/api.ts <<'EOF'
export type HistoryItem = {
  ts: string;
  slot: "OPEN" | "MID" | "CLOSE" | string;
  equityPre?: number | null;
  equityPost?: number | null;
  cash?: number | null;
  exposurePct?: number | null;
  drawdownPct?: number | null;
  targetPerPos?: number | null;
  rawLen?: number | null;
};

export async function getHistory(): Promise<HistoryItem[]> {
  const res = await fetch("http://127.0.0.1:3000/api/history", {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`API /api/history failed: ${res.status}`);
  }

  const json = await res.json();
  return json.data || [];
}
EOF

mkdir -p app/components
cat > app/components/EquityChart.tsx <<'EOF'
"use client";

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

type Point = {
  ts: string;
  equity: number;
  slot: string;
};

export default function EquityChart({ data }: { data: Point[] }) {
  return (
    <div style={{ width: "100%", height: 280 }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="ts"
            tickFormatter={(v) => new Date(v).toLocaleTimeString()}
            minTickGap={25}
          />
          <YAxis tickFormatter={(v) => `${v}`} width={80} />
          <Tooltip
            labelFormatter={(v) => new Date(String(v)).toLocaleString()}
            formatter={(value: any, name: any, props: any) => {
              return [value, "Equity"];
            }}
          />
          <Line type="monotone" dataKey="equity" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
EOF

cat > app/page.tsx <<'EOF'
import EquityChart from "./components/EquityChart";
import { getHistory, HistoryItem } from "./lib/api";

function fmt(n: number | null | undefined, decimals = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: decimals, minimumFractionDigits: decimals }).format(n);
}

function pct(n: number | null | undefined) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${fmt(n, 2)}%`;
}

export default async function Home() {
  const history = await getHistory();

  // orden por fecha
  const sorted = [...history].sort((a, b) => +new Date(a.ts) - +new Date(b.ts));

  // puntos para la gráfica (usa equityPost si existe, si no equityPre)
  const chartData = sorted
    .map((x) => ({
      ts: x.ts,
      slot: x.slot,
      equity: (x.equityPost ?? x.equityPre) as number,
    }))
    .filter((x) => typeof x.equity === "number");

  const last = sorted[sorted.length - 1];
  const first = sorted[0];

  const lastEquity = (last?.equityPost ?? last?.equityPre) ?? null;
  const firstEquity = (first?.equityPost ?? first?.equityPre) ?? null;

  const growthAbs =
    typeof lastEquity === "number" && typeof firstEquity === "number" ? lastEquity - firstEquity : null;

  const growthPct =
    typeof lastEquity === "number" && typeof firstEquity === "number" && firstEquity !== 0
      ? (growthAbs! / firstEquity) * 100
      : null;

  return (
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 16px", fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Arial" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 28 }}>Invest Dashboard</h1>
          <div style={{ color: "#6b7280", marginTop: 6 }}>
            Fuente: <code>/api/history</code> · {sorted.length} snapshots
          </div>
        </div>
        <div style={{ color: "#6b7280" }}>
          Último update: {last?.ts ? new Date(last.ts).toLocaleString() : "—"}
        </div>
      </header>

      {/* KPI cards */}
      <section style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12, marginTop: 18 }}>
        <div style={{ border: "1px solid #e5e7eb", borderRadius: 14, padding: 14, background: "white" }}>
          <div style={{ color: "#6b7280", fontSize: 12 }}>Equity (último)</div>
          <div style={{ fontSize: 22, fontWeight: 700, marginTop: 6 }}>{fmt(lastEquity, 2)}</div>
          <div style={{ color: "#6b7280", fontSize: 12, marginTop: 6 }}>slot: {last?.slot ?? "—"}</div>
        </div>

        <div style={{ border: "1px solid #e5e7eb", borderRadius: 14, padding: 14, background: "white" }}>
          <div style={{ color: "#6b7280", fontSize: 12 }}>Cash (último)</div>
          <div style={{ fontSize: 22, fontWeight: 700, marginTop: 6 }}>{fmt(last?.cash ?? null, 2)}</div>
          <div style={{ color: "#6b7280", fontSize: 12, marginTop: 6 }}>Exposición: {pct(last?.exposurePct ?? null)}</div>
        </div>

        <div style={{ border: "1px solid #e5e7eb", borderRadius: 14, padding: 14, background: "white" }}>
          <div style={{ color: "#6b7280", fontSize: 12 }}>Crecimiento (abs)</div>
          <div style={{ fontSize: 22, fontWeight: 700, marginTop: 6 }}>{growthAbs === null ? "—" : fmt(growthAbs, 2)}</div>
          <div style={{ color: "#6b7280", fontSize: 12, marginTop: 6 }}>vs primer snapshot</div>
        </div>

        <div style={{ border: "1px solid #e5e7eb", borderRadius: 14, padding: 14, background: "white" }}>
          <div style={{ color: "#6b7280", fontSize: 12 }}>Crecimiento (%)</div>
          <div style={{ fontSize: 22, fontWeight: 700, marginTop: 6 }}>{growthPct === null ? "—" : pct(growthPct)}</div>
          <div style={{ color: "#6b7280", fontSize: 12, marginTop: 6 }}>drawdown: {pct(last?.drawdownPct ?? null)}</div>
        </div>
      </section>

      {/* Chart + Table */}
      <section style={{ display: "grid", gridTemplateColumns: "1.2fr 0.8fr", gap: 12, marginTop: 12 }}>
        <div style={{ border: "1px solid #e5e7eb", borderRadius: 14, padding: 14, background: "white" }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Equity over time</div>
          <EquityChart data={chartData} />
        </div>

        <div style={{ border: "1px solid #e5e7eb", borderRadius: 14, padding: 14, background: "white" }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Últimos snapshots</div>
          <div style={{ overflow: "auto", maxHeight: 320 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", color: "#6b7280" }}>
                  <th style={{ padding: "8px 6px", borderBottom: "1px solid #e5e7eb" }}>Slot</th>
                  <th style={{ padding: "8px 6px", borderBottom: "1px solid #e5e7eb" }}>Hora</th>
                  <th style={{ padding: "8px 6px", borderBottom: "1px solid #e5e7eb" }}>Equity</th>
                </tr>
              </thead>
              <tbody>
                {[...sorted].slice(-12).reverse().map((x: HistoryItem) => {
                  const eq = x.equityPost ?? x.equityPre ?? null;
                  return (
                    <tr key={x.ts}>
                      <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6", fontWeight: 600 }}>{x.slot}</td>
                      <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{new Date(x.ts).toLocaleTimeString()}</td>
                      <td style={{ padding: "8px 6px", borderBottom: "1px solid #f3f4f6" }}>{fmt(eq, 2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section style={{ border: "1px solid #e5e7eb", borderRadius: 14, padding: 14, background: "white", marginTop: 12 }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Tabla completa</div>
        <div style={{ overflow: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "#6b7280" }}>
                <th style={{ padding: "10px 8px", borderBottom: "1px solid #e5e7eb" }}>ts</th>
                <th style={{ padding: "10px 8px", borderBottom: "1px solid #e5e7eb" }}>slot</th>
                <th style={{ padding: "10px 8px", borderBottom: "1px solid #e5e7eb" }}>equityPre</th>
                <th style={{ padding: "10px 8px", borderBottom: "1px solid #e5e7eb" }}>equityPost</th>
                <th style={{ padding: "10px 8px", borderBottom: "1px solid #e5e7eb" }}>cash</th>
                <th style={{ padding: "10px 8px", borderBottom: "1px solid #e5e7eb" }}>exposure</th>
                <th style={{ padding: "10px 8px", borderBottom: "1px solid #e5e7eb" }}>drawdown</th>
                <th style={{ padding: "10px 8px", borderBottom: "1px solid #e5e7eb" }}>target/pos</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((x) => (
                <tr key={x.ts}>
                  <td style={{ padding: "10px 8px", borderBottom: "1px solid #f3f4f6" }}>{new Date(x.ts).toLocaleString()}</td>
                  <td style={{ padding: "10px 8px", borderBottom: "1px solid #f3f4f6", fontWeight: 600 }}>{x.slot}</td>
                  <td style={{ padding: "10px 8px", borderBottom: "1px solid #f3f4f6" }}>{fmt(x.equityPre ?? null, 2)}</td>
                  <td style={{ padding: "10px 8px", borderBottom: "1px solid #f3f4f6" }}>{fmt(x.equityPost ?? null, 2)}</td>
                  <td style={{ padding: "10px 8px", borderBottom: "1px solid #f3f4f6" }}>{fmt(x.cash ?? null, 2)}</td>
                  <td style={{ padding: "10px 8px", borderBottom: "1px solid #f3f4f6" }}>{pct(x.exposurePct ?? null)}</td>
                  <td style={{ padding: "10px 8px", borderBottom: "1px solid #f3f4f6" }}>{pct(x.drawdownPct ?? null)}</td>
                  <td style={{ padding: "10px 8px", borderBottom: "1px solid #f3f4f6" }}>{fmt(x.targetPerPos ?? null, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
EOF

cd /home/ubuntu/dashboard/invest-dashboard
pwd
ls -la app/page.tsx
sed -n '1,40p' app/page.tsx
cat > app/page.tsx <<'EOF'
export default function Home() {
  return (
    <main style={{padding:40,fontFamily:"system-ui"}}>
      <h1>INVEST DASHBOARD FUNCIONANDO 🚀</h1>
      <p>Si ves esto, ya está usando tu page.tsx</p>
    </main>
  );
}
EOF

cat > app/page.tsx <<'EOF'
import EquityChart from "./components/EquityChart";
import { getHistory } from "./lib/api";

export default async function Home() {
  const history = await getHistory();

  const sorted = [...history].sort(
    (a, b) => +new Date(a.ts) - +new Date(b.ts)
  );

  const last = sorted[sorted.length - 1];

  const chartData = sorted.map((x) => ({
    ts: x.ts,
    equity: x.equityPost ?? x.equityPre ?? 0,
  }));

  return (
    <main style={{ maxWidth: 1100, margin: "40px auto", fontFamily: "system-ui" }}>
      <h1 style={{ marginBottom: 20 }}>Invest Dashboard</h1>

      <div style={{ marginBottom: 20 }}>
        <strong>Último slot:</strong> {last?.slot}
        <br />
        <strong>Equity:</strong> {last?.equityPost ?? last?.equityPre}
        <br />
        <strong>Cash:</strong> {last?.cash}
        <br />
        <strong>Exposure:</strong> {last?.exposurePct}%
      </div>

      <div style={{ height: 300 }}>
        <EquityChart data={chartData} />
      </div>
    </main>
  );
}
EOF

ls app/components
ls app/lib
mkdir -p app/components
mkdir -p app/lib
ls app
cat > app/lib/api.ts <<'EOF'
export async function getHistory() {
  const res = await fetch("http://127.0.0.1:3000/api/history", {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error("Failed to fetch history");
  }

  const json = await res.json();
  return json.data || [];
}
EOF

cat > app/components/EquityChart.tsx <<'EOF'
"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

export default function EquityChart({ data }: any) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="ts"
          tickFormatter={(v) => new Date(v).toLocaleTimeString()}
        />
        <YAxis />
        <Tooltip
          labelFormatter={(v) => new Date(String(v)).toLocaleString()}
        />
        <Line type="monotone" dataKey="equity" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
EOF

cd aoo
cd app
dir
rm page.tsx
sudo nano page.tsx
ls
cd components+
cd components
sudo nano EquityChart.tsx
ls
rm EquityChart.tsx 
sudo nano EquityChart.tsx
cd ..
sudo nano page.tsx 
rm page.tsx
sudo nano page.tsx
cd components/
ls
rm EquityChart.tsx 
sudo nano EquityChart.tsx
rm EquityChart.tsx 
sudo nano EquityChart.tsx
clear
node -v
sudo apt remove -y nodejs
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v
npm -v
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
cd /home/ubuntu/dashboard
node -v
npm -v
free -h
npx create-next-app@latest invest-dashboard
rm -r invest-dashboard/
npx create-next-app@latest invest-dashboard
cd invest-dashboard/
npm i recharts
ls
mkdir -p src/app/api/history
touch src/app/api/history/route.ts
tree
ls src/app/api/history
nano src/app/api/history/route.ts
npm run dev -- --hostname 127.0.0.1 --port 3000
npm run dev -- -H 0.0.0.0 -p 3000
cd dashboard/invest-dashboard/
npm run dev -- -H 0.0.0.0 -p 3000
cat /home/ubuntu/quant-bot/reports/latest.md
python3 - << 'PY'
import duckdb
con=duckdb.connect("/home/ubuntu/quant-bot/data/market.duckdb")
print("MAX(bars.date) =", con.execute("SELECT MAX(date) FROM bars").fetchone()[0])
print("MAX(features.date) =", con.execute("SELECT MAX(date) FROM features").fetchone()[0])
print("positions =", con.execute("SELECT COUNT(*) FROM positions").fetchone()[0])
PY

python3 - << 'PY'
import os, datetime as dt
import duckdb
import pandas as pd

# Carga env como lo hace tu API
os.environ.update({
 "TICKERS_FILE":"/home/ubuntu/quant-bot/data/tickers.txt",
 "DB_PATH":"/home/ubuntu/quant-bot/data/market.duckdb",
 "REPORTS_DIR":"/home/ubuntu/quant-bot/reports",
 "START_CASH":"100000",
 "MAX_POSITIONS":"20",
 "MAX_EXPOSURE_PCT":"0.95",
 "MIN_POSITION_USD":"1000",
 "FEE_BPS":"10",
 "SLIPPAGE_BPS":"10",
 "BUY_TOP_PCT":"0.10",
 "SELL_OUT_PCT":"0.30",
 "MAX_REPLACEMENTS_PER_DAY":"5",
 "HISTORY_YEARS":"3",
})

import run_daily as core

cfg = core.load_config()
con = core.get_db(cfg.db_path)

asof = con.execute("SELECT MAX(date) FROM bars").fetchone()[0]
print("ASOF:", asof)

sig = core.generate_signals(con, cfg, asof=asof)
print("signals rows:", len(sig))
if len(sig):
    print(sig.head(50).to_string(index=False))
PY

cd ~/quant-bot/worker
source .venv/bin/activate
python
