// app/page.tsx

import EquityChart from "./components/EquityChart";
import { readFile, readdir } from "fs/promises";
import path from "path";

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

type Trade = {
  reportDate: string;
  side: string;
  symbol: string;
  shares: number | null;
  close: number | null;
  effective: number | null;
  reason: string;
};

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

function yyyyMmDdFromIso(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
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

function parseTradesFromMarkdown(md: string, reportDate: string): Trade[] {
  const sectionMatch = md.match(/## Trades de hoy([\s\S]*?)(## |$)/);
  if (!sectionMatch) return [];

  const section = sectionMatch[1];

  const lines = section
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.startsWith("-"));

  const trades: Trade[] = [];

  for (const line of lines) {
    if (line.includes("(sin trades hoy)")) continue;

    const match = line.match(
      /- \*\*(BUY|SELL)\s+([A-Z0-9.\-]+)\*\*\s+\|\s+shares\s+([\d.]+)\s+\|\s+close\s+([\d.]+)\s+\|\s+eff\s+([\d.]+)\s+\|\s+(.+)$/
    );

    if (!match) continue;

    trades.push({
      reportDate,
      side: match[1],
      symbol: match[2],
      shares: Number(match[3]),
      close: Number(match[4]),
      effective: Number(match[5]),
      reason: match[6],
    });
  }

  return trades;
}

async function getLatestTrades(): Promise<Trade[]> {
  try {
    const md = await readFile("/home/ubuntu/n8n-files/latest.md", "utf8");
    return parseTradesFromMarkdown(md, "latest");
  } catch {
    return [];
  }
}

async function getTradesFromReportsForDay(day: string): Promise<Trade[]> {
  try {
    const reportsDir = "/home/ubuntu/quant-bot/reports";
    const files = await readdir(reportsDir);

    const mdFiles = files
      .filter((f) => f.endsWith(".md"))
      .filter((f) => f !== "latest.md")
      .sort();

    const allTrades: Trade[] = [];

    for (const file of mdFiles) {
      const reportDate = path.basename(file, ".md");
      if (reportDate !== day) continue;

      const fullPath = path.join(reportsDir, file);
      const md = await readFile(fullPath, "utf8");
      allTrades.push(...parseTradesFromMarkdown(md, reportDate));
    }

    return allTrades;
  } catch {
    return [];
  }
}

function TradesTable({
  trades,
  emptyText,
}: {
  trades: Trade[];
  emptyText: string;
}) {
  if (trades.length === 0) {
    return <div className="text-sm text-zinc-500">{emptyText}</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-zinc-500">
          <tr>
            <th className="pb-2 pr-4">Acción</th>
            <th className="pb-2 pr-4">Ticker</th>
            <th className="pb-2 pr-4">Shares</th>
            <th className="pb-2 pr-4">Close</th>
            <th className="pb-2 pr-4">Precio efectivo</th>
            <th className="pb-2">Motivo</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={`${t.reportDate}-${t.symbol}-${i}`} className="border-t border-zinc-100">
              <td className="py-2 pr-4">
                <SidePill side={t.side} />
              </td>
              <td className="py-2 pr-4 font-medium">{t.symbol}</td>
              <td className="py-2 pr-4">{fmtNum(t.shares, 4)}</td>
              <td className="py-2 pr-4">{fmtNum(t.close, 2)}</td>
              <td className="py-2 pr-4">{fmtNum(t.effective, 2)}</td>
              <td className="py-2">{t.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

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

  const latestTrades = await getLatestTrades();
  const currentDay = yyyyMmDdFromIso(last?.ts);
  const dayTrades = await getTradesFromReportsForDay(currentDay);

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

          <div className="flex items-center gap-2">
            <span className="text-sm text-zinc-600">Último slot:</span>
            <SlotPill slot={last?.slot} />
          </div>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card label="Equity" value={fmtMoney(equity)} />
          <Card label="Cash" value={fmtMoney(last?.cash)} />
          <Card label="Exposure" value={fmtPct(last?.exposurePct)} />
          <Card label="Drawdown" value={fmtPct(last?.drawdownPct)} />
        </div>

        <div className="mt-6">
          <EquityChart data={sorted} />
        </div>

        <div className="mt-6 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
          <div className="mb-4 text-sm font-medium text-zinc-900">
            Operaciones del último reporte
          </div>

          <TradesTable
            trades={latestTrades}
            emptyText="Sin operaciones en este slot."
          />
        </div>

        <div className="mt-6 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
          <div className="mb-4 text-sm font-medium text-zinc-900">
            Operaciones del día
          </div>

          <TradesTable
            trades={dayTrades}
            emptyText="Sin operaciones registradas en este día."
          />
        </div>

        <div className="mt-6 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
          <div className="mb-4 text-sm font-medium text-zinc-900">Historial</div>

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