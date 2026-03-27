// app/page.tsx

import Link from "next/link";
import EquityChart from "./components/EquityChart";
import { readFile } from "fs/promises";

type Snapshot = {
  ts: string;
  slot?: "OPEN" | "MID" | "CLOSE" | string;
  equityPre?: number | null;
  equityPost?: number | null;
  cash?: number | null;
  exposurePct?: number | null;
  drawdownPct?: number | null;
  targetPerPos?: number | null;
  rawLen?: number | null;
};


const TICKER_NAMES: Record<string, string> = {
  AAPL: "Apple", MSFT: "Microsoft", NVDA: "Nvidia", AMZN: "Amazon",
  META: "Meta", GOOGL: "Alphabet", TSLA: "Tesla", AMD: "AMD",
  INTC: "Intel", NFLX: "Netflix", CRM: "Salesforce", ADBE: "Adobe",
  CSCO: "Cisco", ORCL: "Oracle", SNOW: "Snowflake", PLTR: "Palantir",
  ANET: "Arista Networks", PANW: "Palo Alto", FTNT: "Fortinet",
  NOW: "ServiceNow", TTD: "The Trade Desk", UNH: "UnitedHealth",
  LLY: "Eli Lilly", JNJ: "Johnson & Johnson", ABT: "Abbott",
  MRK: "Merck", PFE: "Pfizer", AMGN: "Amgen", ISRG: "Intuitive Surgical",
  TMO: "Thermo Fisher", JPM: "JPMorgan", BAC: "Bank of America",
  GS: "Goldman Sachs", MS: "Morgan Stanley", BLK: "BlackRock",
  SPGI: "S&P Global", AXP: "Amex", CB: "Chubb", V: "Visa", MA: "Mastercard",
  CAT: "Caterpillar", DE: "John Deere", HON: "Honeywell", GE: "GE Aerospace",
  RTX: "RTX Corp", LMT: "Lockheed Martin", UPS: "UPS", HD: "Home Depot",
  PG: "Procter & Gamble", KO: "Coca-Cola", PEP: "PepsiCo", COST: "Costco",
  WMT: "Walmart", NKE: "Nike", SBUX: "Starbucks", MCD: "McDonald's",
  TJX: "TJX Companies", LOW: "Lowe's", XOM: "ExxonMobil", CVX: "Chevron",
  COP: "ConocoPhillips", SLB: "SLB", FCX: "Freeport-McMoRan",
  NEM: "Newmont", LIN: "Linde", "BRK-B": "Berkshire Hathaway",
  DIS: "Disney", LRCX: "Lam Research", XLK: "Tech ETF", XLF: "Finance ETF",
  XLE: "Energy ETF", XLV: "Health ETF", XLI: "Industrial ETF",
};

function TickerCell({ symbol }: { symbol: string }) {
  const name = TICKER_NAMES[symbol];
  return (
    <div>
      <div className="font-medium">{symbol}</div>
      {name && <div className="text-xs text-zinc-400">{name}</div>}
    </div>
  );
}

function fmtMoney(v?: number | null) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(v);
}

function fmtNum(v?: number | null, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("es-ES", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(v);
}

function fmtPct(v?: number | null) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return (
    new Intl.NumberFormat("es-ES", {
      maximumFractionDigits: 2,
    }).format(v) + "%"
  );
}

function fmtDate(iso?: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("es-ES", { hour12: false });
}

function SlotPill({ slot }: { slot?: string }) {
  const s = (slot || "—").toUpperCase();

  const base =
    "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset";

  const cls =
    s === "OPEN"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : s === "MID"
      ? "bg-amber-50 text-amber-700 ring-amber-200"
      : s === "CLOSE"
      ? "bg-sky-50 text-sky-700 ring-sky-200"
      : "bg-zinc-50 text-zinc-700 ring-zinc-200";

  return <span className={`${base} ${cls}`}>{s}</span>;
}

function SidePill({ side }: { side?: string }) {
  const s = (side || "—").toUpperCase();

  const base =
    "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset";

  const cls =
    s === "BUY"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : s === "SELL"
      ? "bg-rose-50 text-rose-700 ring-rose-200"
      : "bg-zinc-50 text-zinc-700 ring-zinc-200";

  return <span className={`${base} ${cls}`}>{s}</span>;
}

function Card({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
      <div className="text-sm text-zinc-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-zinc-900">{value}</div>
    </div>
  );
}

function PnlCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "positive" | "negative" | "neutral";
}) {
  const valueClass =
    tone === "positive"
      ? "text-emerald-600"
      : tone === "negative"
      ? "text-rose-600"
      : "text-zinc-900";

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
      <div className="text-sm text-zinc-500">{label}</div>
      <div className={`mt-2 text-2xl font-semibold ${valueClass}`}>
        {value}
      </div>
    </div>
  );
}

/** Lee solo el header de latest.md para extraer la fecha del último reporte.
 *  Línea 1 del archivo: "# Reporte diario — YYYY-MM-DD" (formato muy estable).
 *  Si el archivo no existe o no matchea, retorna null de forma segura.
 */
async function getLastReportDate(): Promise<string | null> {
  try {
    const md = await readFile("/home/ubuntu/quant-bot/reports/latest.md", "utf8");
    const match = md.match(/^# Reporte diario — (\d{4}-\d{2}-\d{2})/m);
    return match ? match[1] : null;
  } catch {
    return null;
  }
}

type Position = {
  symbol: string;
  shares: number;
  avgPrice: number;
  close: number | null;
  mv: number | null;
  pnlPct: number | null;
};

function parsePositionsFromMarkdown(md: string): Position[] {
  const sectionMatch = md.match(/## Posiciones actuales([\s\S]*?)(## |$)/);
  if (!sectionMatch) return [];

  const lines = sectionMatch[1]
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.startsWith("-"));

  const NUM = "([+-]?[\\d.]+|nan)";
  const re = new RegExp(
    `- \\*\\*([A-Z0-9.\\-]+)\\*\\*:\\s+([\\d.]+)\\s+sh\\s+\\|\\s+avg\\s+([\\d.]+)\\s+\\|\\s+close\\s+${NUM}\\s+\\|\\s+mv\\s+${NUM}\\s+\\|\\s+pnl\\s+${NUM}%`
  );

  const positions: Position[] = [];
  for (const line of lines) {
    if (line.includes("(sin posiciones)")) continue;
    const match = line.match(re);
    if (!match) continue;
    const parseNum = (s: string) => (s === "nan" ? null : Number(s));
    positions.push({
      symbol: match[1],
      shares: Number(match[2]),
      avgPrice: Number(match[3]),
      close: parseNum(match[4]),
      mv: parseNum(match[5]),
      pnlPct: parseNum(match[6]),
    });
  }
  return positions;
}

async function getCurrentPositions(): Promise<Position[]> {
  try {
    const md = await readFile("/home/ubuntu/quant-bot/reports/latest.md", "utf8");
    return parsePositionsFromMarkdown(md);
  } catch {
    return [];
  }
}

type TradeLog = {
  id: number;
  date: string;
  symbol: string;
  side: string;
  shares: number;
  price_close: number;
  price_effective: number;
  value: number;
  reason: string;
};

export default async function Page() {
  const res = await fetch("http://localhost:3000/api/history", {
    cache: "no-store",
  });

  const json = await res.json();
  const data: Snapshot[] = json?.data || [];

  const sorted = [...data].sort(
    (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime()
  );

  const last = sorted.length ? sorted[sorted.length - 1] : null;
  const equity = last?.equityPost ?? last?.equityPre ?? null;

  const positions = await getCurrentPositions();

  const tradesRes = await fetch("http://localhost:3000/api/trades", {
    cache: "no-store",
  });
  const tradesJson = await tradesRes.json();
  const tradesLog: TradeLog[] = tradesJson?.data || [];

  // Trades del último reporte: leer solo el header de latest.md para obtener
  // la fecha, luego filtrar el histórico estructurado. Evita parsear líneas
  // de markdown y garantiza que ambas tablas usan la misma fuente de datos.
  const lastReportDate = await getLastReportDate();
  const lastReportTrades = lastReportDate
    ? tradesLog.filter((t) => t.date === lastReportDate)
    : [];

  // Calcular PnL para cada SELL cruzando con el BUY anterior del mismo símbolo
  const buyPriceMap: Record<string, number> = {};
  const tradesAsc = [...tradesLog].sort((a, b) => a.date.localeCompare(b.date));
  tradesAsc.forEach((t) => {
    if (t.side === "BUY") buyPriceMap[t.symbol] = t.price_effective;
  });
  const pnlMap: Record<number, { abs: number; pct: number }> = {};
  tradesAsc.forEach((t) => {
    if (t.side === "SELL" && buyPriceMap[t.symbol] != null) {
      const buyPrice = buyPriceMap[t.symbol];
      const pnlAbs = (t.price_effective - buyPrice) * t.shares;
      const pnlPct = (t.price_effective / buyPrice - 1) * 100;
      pnlMap[t.id] = { abs: pnlAbs, pct: pnlPct };
    }
  });

  const initialCapital = 100000;

  const pnlAbs =
    equity !== null && equity !== undefined ? equity - initialCapital : null;

  const pnlPct =
    equity !== null && equity !== undefined && initialCapital > 0
      ? ((equity / initialCapital) - 1) * 100
      : null;

  const pnlTone: "positive" | "negative" | "neutral" =
    pnlAbs === null || pnlAbs === undefined
      ? "neutral"
      : pnlAbs > 0
      ? "positive"
      : pnlAbs < 0
      ? "negative"
      : "neutral";

  return (
    <main className="min-h-screen bg-zinc-50">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-900">
              Invest Dashboard
            </h1>
            <p className="text-sm text-zinc-600">
              Última actualización:{" "}
              <span className="font-medium">{fmtDate(last?.ts)}</span>
            </p>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-zinc-600">Último slot:</span>
              <SlotPill slot={last?.slot} />
            </div>
            <Link
              href="/backtest"
              className="rounded-full bg-zinc-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700 transition-colors"
            >
              Ver Backtest
            </Link>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-6">
          <Card label="Equity" value={fmtMoney(equity)} />
          <Card label="Cash" value={fmtMoney(last?.cash)} />
          <Card label="Exposure" value={fmtPct(last?.exposurePct)} />
          <Card label="Drawdown" value={fmtPct(last?.drawdownPct)} />
          <PnlCard label="PnL total" value={fmtMoney(pnlAbs)} tone={pnlTone} />
          <PnlCard label="PnL total %" value={fmtPct(pnlPct)} tone={pnlTone} />
        </div>

        <div className="mt-6">
          <EquityChart data={sorted} />
        </div>

        <div className="mt-6 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
          <div className="mb-4 text-sm font-medium text-zinc-900">Posiciones actuales</div>

          {positions.length === 0 ? (
            <div className="text-sm text-zinc-500">Sin posiciones abiertas.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-zinc-500">
                  <tr>
                    <th className="pb-2 pr-4">Ticker</th>
                    <th className="pb-2 pr-4">Shares</th>
                    <th className="pb-2 pr-4">Precio medio</th>
                    <th className="pb-2 pr-4">Close actual</th>
                    <th className="pb-2 pr-4">Valor (USD)</th>
                    <th className="pb-2">PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => {
                    const pnlAbs = p.close != null ? (p.close - p.avgPrice) * p.shares : null;
                    const tone = p.pnlPct == null ? "text-zinc-500" : p.pnlPct >= 0 ? "text-emerald-600" : "text-rose-600";
                    return (
                      <tr key={p.symbol} className="border-t border-zinc-100">
                        <td className="py-2 pr-4"><TickerCell symbol={p.symbol} /></td>
                        <td className="py-2 pr-4">{fmtNum(p.shares, 4)}</td>
                        <td className="py-2 pr-4">{fmtNum(p.avgPrice, 2)}</td>
                        <td className="py-2 pr-4">{fmtNum(p.close, 2)}</td>
                        <td className="py-2 pr-4">{fmtMoney(p.mv)}</td>
                        <td className={`py-2 font-medium ${tone}`}>
                          {pnlAbs != null && p.pnlPct != null
                            ? `${pnlAbs >= 0 ? "+" : ""}${fmtMoney(pnlAbs)} (${p.pnlPct >= 0 ? "+" : ""}${fmtNum(p.pnlPct, 2)}%)`
                            : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="mt-6 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
          <div className="mb-4 text-sm font-medium text-zinc-900">
            Operaciones del último reporte
            {lastReportDate && (
              <span className="ml-2 text-xs font-normal text-zinc-400">{lastReportDate}</span>
            )}
          </div>

          {lastReportTrades.length === 0 ? (
            <div className="text-sm text-zinc-500">
              {lastReportDate ? "Sin operaciones en este reporte." : "No hay datos del último reporte."}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-zinc-500">
                  <tr>
                    <th className="pb-2 pr-4">Acción</th>
                    <th className="pb-2 pr-4">Ticker</th>
                    <th className="pb-2 pr-4">Shares</th>
                    <th className="pb-2 pr-4">Close</th>
                    <th className="pb-2 pr-4">Precio efectivo</th>
                    <th className="pb-2 pr-4">Valor (USD)</th>
                    <th className="pb-2">Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {lastReportTrades.map((t) => (
                    <tr key={t.id} className="border-t border-zinc-100">
                      <td className="py-2 pr-4">
                        <SidePill side={t.side} />
                      </td>
                      <td className="py-2 pr-4"><TickerCell symbol={t.symbol} /></td>
                      <td className="py-2 pr-4">{fmtNum(t.shares, 4)}</td>
                      <td className="py-2 pr-4">{fmtNum(t.price_close, 2)}</td>
                      <td className="py-2 pr-4">{fmtNum(t.price_effective, 2)}</td>
                      <td className="py-2 pr-4">{fmtMoney(t.value)}</td>
                      <td className="py-2">{t.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="mt-6 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
          <div className="mb-4 text-sm font-medium text-zinc-900">Histórico de operaciones</div>

          {tradesLog.length === 0 ? (
            <div className="text-sm text-zinc-500">Sin operaciones registradas.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-zinc-500">
                  <tr>
                    <th className="pb-2 pr-4">Fecha</th>
                    <th className="pb-2 pr-4">Acción</th>
                    <th className="pb-2 pr-4">Ticker</th>
                    <th className="pb-2 pr-4">Shares</th>
                    <th className="pb-2 pr-4">Close</th>
                    <th className="pb-2 pr-4">Precio efectivo</th>
                    <th className="pb-2 pr-4">Valor (USD)</th>
                    <th className="pb-2 pr-4">PnL</th>
                    <th className="pb-2">Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {tradesLog.map((t) => {
                    const pnl = pnlMap[t.id];
                    return (
                    <tr key={t.id} className="border-t border-zinc-100">
                      <td className="py-2 pr-4 text-zinc-500">{t.date}</td>
                      <td className="py-2 pr-4">
                        <SidePill side={t.side} />
                      </td>
                      <td className="py-2 pr-4"><TickerCell symbol={t.symbol} /></td>
                      <td className="py-2 pr-4">{fmtNum(t.shares, 4)}</td>
                      <td className="py-2 pr-4">{fmtNum(t.price_close, 2)}</td>
                      <td className="py-2 pr-4">{fmtNum(t.price_effective, 2)}</td>
                      <td className="py-2 pr-4">{fmtMoney(t.value)}</td>
                      <td className="py-2 pr-4">
                        {pnl != null ? (
                          <span className={pnl.abs >= 0 ? "text-emerald-600 font-medium" : "text-rose-600 font-medium"}>
                            {pnl.abs >= 0 ? "+" : ""}{fmtMoney(pnl.abs)} ({pnl.abs >= 0 ? "+" : ""}{fmtNum(pnl.pct, 2)}%)
                          </span>
                        ) : (
                          <span className="text-zinc-400">—</span>
                        )}
                      </td>
                      <td className="py-2">{t.reason}</td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="mt-6 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
          <div className="mb-4 text-sm font-medium text-zinc-900">Historial de equity</div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-zinc-500">
                <tr>
                  <th className="pb-2 pr-4">Fecha</th>
                  <th className="pb-2 pr-4">Slot</th>
                  <th className="pb-2 pr-4">Equity</th>
                  <th className="pb-2 pr-4">Cash</th>
                  <th className="pb-2 pr-4">Exposure</th>
                  <th className="pb-2">DD</th>
                </tr>
              </thead>
              <tbody>
                {[...sorted].reverse().map((row, i) => {
                  const eq = row.equityPost ?? row.equityPre;
                  return (
                    <tr key={i} className="border-t border-zinc-100">
                      <td className="py-2 pr-4">{fmtDate(row.ts)}</td>
                      <td className="py-2 pr-4">
                        <SlotPill slot={row.slot} />
                      </td>
                      <td className="py-2 pr-4 font-medium">{fmtMoney(eq)}</td>
                      <td className="py-2 pr-4">{fmtMoney(row.cash)}</td>
                      <td className="py-2 pr-4">{fmtPct(row.exposurePct)}</td>
                      <td className="py-2">{fmtPct(row.drawdownPct)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </main>
  );
}