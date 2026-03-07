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
