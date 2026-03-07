// app/page.tsx

import EquityChart from "./components/EquityChart";

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

function fmtMoney(v?: number | null) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(v);
}

function fmtPct(v?: number | null) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: 2,
  }).format(v) + "%";
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
      <div className="mt-2 text-2xl font-semibold text-zinc-900">
        {value}
      </div>
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

  return (
    <main className="min-h-screen bg-zinc-50">
      <div className="mx-auto max-w-6xl px-4 py-10">

        {/* HEADER */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-900">
              Invest Dashboard
            </h1>
            <p className="text-sm text-zinc-600">
              Última actualización:{" "}
              <span className="font-medium">
                {fmtDate(last?.ts)}
              </span>
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm text-zinc-600">Último slot:</span>
            <SlotPill slot={last?.slot} />
          </div>
        </div>

        {/* CARDS */}
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card label="Equity" value={fmtMoney(equity)} />
          <Card label="Cash" value={fmtMoney(last?.cash)} />
          <Card label="Exposure" value={fmtPct(last?.exposurePct)} />
          <Card label="Drawdown" value={fmtPct(last?.drawdownPct)} />
        </div>

        {/* CHART */}
        <div className="mt-6">
          <EquityChart data={sorted} />
        </div>

        {/* TABLE */}
        <div className="mt-6 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
          <div className="text-sm font-medium text-zinc-900 mb-4">
            Historial
          </div>

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
                      <td className="py-2 pr-4">
                        {fmtDate(row.ts)}
                      </td>
                      <td className="py-2 pr-4">
                        <SlotPill slot={row.slot} />
                      </td>
                      <td className="py-2 pr-4 font-medium">
                        {fmtMoney(eq)}
                      </td>
                      <td className="py-2 pr-4">
                        {fmtMoney(row.cash)}
                      </td>
                      <td className="py-2 pr-4">
                        {fmtPct(row.exposurePct)}
                      </td>
                      <td className="py-2">
                        {fmtPct(row.drawdownPct)}
                      </td>
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
