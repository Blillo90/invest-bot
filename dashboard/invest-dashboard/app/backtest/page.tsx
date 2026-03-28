"use client";

import React, { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  ReferenceLine,
} from "recharts";

// ─── Types ────────────────────────────────────────────────────────────────────
type CurvePoint = { date: string; value: number };

type Metrics = {
  cagr: number;
  total_return: number;
  volatility: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  calmar: number;
  avg_exposure: number;
  num_trades: number;
  win_rate: number;
};

type AnnualReturn = { year: number; return: number };

type Variant = {
  id: string;
  label: string;
  color: string;
  metrics: Metrics;
  annual_returns: AnnualReturn[];
  equity_curve: CurvePoint[];
  drawdown_curve: CurvePoint[];
  exposure_curve: CurvePoint[];
};

type BacktestData = {
  generated_at: string;
  period: { start: string; end: string; trading_days: number };
  variants: Variant[];
};

// ─── Helpers ─────────────────────────────────────────────────────────────────
function pct(v: number | null | undefined, digits = 1) {
  if (v == null || !isFinite(v)) return "—";
  return (v * 100).toFixed(digits) + "%";
}
function num(v: number | null | undefined, digits = 2) {
  if (v == null || !isFinite(v)) return "—";
  return v.toFixed(digits);
}
function fmtDate(iso: string) {
  return iso.slice(0, 10);
}

// Downsample array keeping every Nth point (always includes first & last)
function downsample<T>(arr: T[], n: number): T[] {
  if (arr.length <= n) return arr;
  const step = Math.ceil(arr.length / n);
  const out: T[] = [];
  for (let i = 0; i < arr.length; i += step) out.push(arr[i]);
  const last = arr[arr.length - 1];
  if (out[out.length - 1] !== last) out.push(last);
  return out;
}

// Normalise equity curves to 100
function normalise(curves: { id: string; curve: CurvePoint[] }[]) {
  const dateSet = new Set<string>();
  curves.forEach(({ curve }) => curve.forEach((p) => dateSet.add(p.date)));
  const dates = Array.from(dateSet).sort();

  return dates.map((date) => {
    const row: Record<string, number | string> = { date };
    curves.forEach(({ id, curve }) => {
      const first = curve[0]?.value ?? 100000;
      const pt = curve.find((p) => p.date === date);
      if (pt) row[id] = parseFloat(((pt.value / first) * 100).toFixed(4));
    });
    return row;
  });
}

// Merge drawdown curves
function mergeDrawdown(variants: Variant[]) {
  const dateSet = new Set<string>();
  variants.forEach((v) => v.drawdown_curve.forEach((p) => dateSet.add(p.date)));
  const dates = Array.from(dateSet).sort();

  return dates.map((date) => {
    const row: Record<string, number | string> = { date };
    variants.forEach((v) => {
      const pt = v.drawdown_curve.find((p) => p.date === date);
      if (pt) row[v.id] = pt.value;
    });
    return row;
  });
}

// Merge exposure curves
function mergeExposure(variants: Variant[]) {
  const strategy = variants.filter(
    (v) => !["spy", "acwi"].includes(v.id)
  );
  const dateSet = new Set<string>();
  strategy.forEach((v) => v.exposure_curve.forEach((p) => dateSet.add(p.date)));
  const dates = Array.from(dateSet).sort();

  return dates.map((date) => {
    const row: Record<string, number | string> = { date };
    strategy.forEach((v) => {
      const pt = v.exposure_curve.find((p) => p.date === date);
      if (pt) row[v.id] = pt.value;
    });
    return row;
  });
}

// All years present in data
function allYears(variants: Variant[]): number[] {
  const ys = new Set<number>();
  variants.forEach((v) => v.annual_returns.forEach((r) => ys.add(r.year)));
  return Array.from(ys).sort();
}

// ─── Metric tone ─────────────────────────────────────────────────────────────
function metricClass(key: string, v: number): string {
  if (key === "max_drawdown") return v < -0.25 ? "text-rose-600" : v < -0.15 ? "text-amber-600" : "text-emerald-600";
  if (key === "cagr" || key === "total_return") return v > 0.1 ? "text-emerald-600" : v > 0 ? "text-amber-600" : "text-rose-600";
  if (key === "sharpe" || key === "sortino") return v > 0.5 ? "text-emerald-600" : v > 0 ? "text-amber-600" : "text-rose-600";
  if (key === "calmar") return v > 0.5 ? "text-emerald-600" : v > 0 ? "text-amber-600" : "text-rose-600";
  return "text-zinc-900";
}

function annualClass(v: number) {
  if (v > 0.15) return "bg-emerald-100 text-emerald-800";
  if (v > 0.05) return "bg-emerald-50 text-emerald-700";
  if (v >= 0)   return "bg-zinc-50 text-zinc-700";
  if (v > -0.1) return "bg-amber-50 text-amber-700";
  return "bg-rose-100 text-rose-700";
}

// ─── Chart tooltip ───────────────────────────────────────────────────────────
const CustomTooltip = ({
  active,
  payload,
  label,
  suffix = "",
}: {
  active?: boolean;
  payload?: any[];
  label?: string;
  suffix?: string;
}) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-zinc-200 bg-white px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-semibold text-zinc-700">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-zinc-600">{p.name}:</span>
          <span className="font-medium text-zinc-900">
            {typeof p.value === "number" ? p.value.toFixed(2) : p.value}
            {suffix}
          </span>
        </div>
      ))}
    </div>
  );
};

// ─── Verdict box ─────────────────────────────────────────────────────────────
function Verdict({ variants }: { variants: Variant[] }) {
  const bot      = variants.find((v) => v.id === "current_bot");
  const fill     = variants.find((v) => v.id === "fill_to_target");
  const improved = variants.find((v) => v.id === "improved");
  const ew       = variants.find((v) => v.id === "equal_weight");
  const spy      = variants.find((v) => v.id === "spy");
  if (!bot || !improved || !spy) return null;

  const beatsSpy = (improved.metrics.cagr ?? 0) > (spy.metrics.cagr ?? 0);
  const gapToSpy = (spy.metrics.cagr ?? 0) - (improved.metrics.cagr ?? 0);
  const uSize    = (variants[0] as any)?.universe_size;

  return (
    <div className="rounded-2xl border border-zinc-200 bg-zinc-950 p-5 text-white">
      <div className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
        Veredicto cuantitativo
      </div>
      <div className="space-y-2 text-sm leading-relaxed text-zinc-200">
        <p>
          Universo ampliado a{" "}
          <span className="font-bold text-white">~266 tickers</span>.
          La exposición del bot actual subió de ~48% a{" "}
          <span className="font-bold text-amber-400">
            {pct(bot.metrics.avg_exposure, 0)}
          </span>{" "}
          — pero el CAGR{" "}
          <span className="font-bold text-rose-400">empeoró</span> ({pct(bot.metrics.cagr)}).
          Con más candidatos, el ranking buy_top_pct=7% selecciona activos mediocres del universo ampliado.
        </p>
        <p>
          <span className="font-semibold text-white">Improved</span> genera un CAGR del{" "}
          <span className="font-bold text-emerald-400">{pct(improved.metrics.cagr)}</span>{" "}
          (Sharpe {num(improved.metrics.sharpe)}) — la única variante activa con retorno positivo.
          Exposición media: {pct(improved.metrics.avg_exposure, 0)}.
        </p>
        {ew && (
          <p>
            <span className="font-semibold text-white">Equal Weight</span> (rebalanceo mensual, top 150 por liquidez)
            logra{" "}
            <span className="font-bold text-emerald-400">{pct(ew.metrics.cagr)}</span>{" "}
            de CAGR con Sharpe {num(ew.metrics.sharpe)} —{" "}
            <span className="text-amber-300 font-semibold">casi iguala a ACWI</span> y supera a Improved.
            Esto indica que el alpha del ranking no justifica aún los costes de rotación.
          </p>
        )}
        <p>
          {beatsSpy ? (
            <span className="text-emerald-400 font-semibold">Improved supera a SPY.</span>
          ) : (
            <>
              SPY sigue siendo la referencia más difícil (
              {pct(spy.metrics.cagr)}, Sharpe {num(spy.metrics.sharpe)}).
              Gap vs Improved:{" "}
              <span className="font-bold text-rose-400">-{pct(gapToSpy)}</span> de CAGR anual.
            </>
          )}
        </p>
        <p className="mt-2 text-zinc-400 text-xs">
          Improved — Sharpe: {num(improved.metrics.sharpe)} · Sortino:{" "}
          {num(improved.metrics.sortino)} · Max DD:{" "}
          {pct(improved.metrics.max_drawdown)} · Calmar: {num(improved.metrics.calmar)}
        </p>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function BacktestPage() {
  const [data, setData] = useState<BacktestData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeVariants, setActiveVariants] = useState<Set<string>>(
    new Set(["current_bot", "improved", "bottest2", "ema_sma_bollinger", "ema_sma_bollinger_v2", "spy", "acwi"])
  );

  useEffect(() => {
    fetch("/backtest-results.json")
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, []);

  const toggleVariant = (id: string) => {
    setActiveVariants((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { if (next.size > 1) next.delete(id); }
      else next.add(id);
      return next;
    });
  };

  const visibleVariants = useMemo(
    () => data?.variants.filter((v) => activeVariants.has(v.id)) ?? [],
    [data, activeVariants]
  );

  const equityData = useMemo(() => {
    if (!visibleVariants.length) return [];
    const raw = normalise(
      visibleVariants.map((v) => ({ id: v.id, curve: v.equity_curve }))
    );
    return downsample(raw, 300);
  }, [visibleVariants]);

  const drawdownData = useMemo(() => {
    if (!visibleVariants.length) return [];
    return downsample(mergeDrawdown(visibleVariants), 300);
  }, [visibleVariants]);

  const exposureData = useMemo(() => {
    if (!visibleVariants.length) return [];
    return downsample(mergeExposure(visibleVariants), 300);
  }, [visibleVariants]);

  const years = useMemo(() => (data ? allYears(data.variants) : []), [data]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50">
        <div className="text-sm text-zinc-500">Cargando resultados del backtest...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50">
        <div className="text-sm text-rose-600">
          Error cargando backtest-results.json: {error}
        </div>
      </div>
    );
  }

  const allVariants = data.variants;

  return (
    <div className="min-h-screen bg-zinc-50">
      {/* Nav */}
      <nav className="border-b border-zinc-200 bg-white px-6 py-3">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-sm text-zinc-500 hover:text-zinc-900">
              Dashboard en vivo
            </Link>
            <span className="text-zinc-300">/</span>
            <span className="text-sm font-semibold text-zinc-900">
              Backtest
            </span>
          </div>
          <div className="text-xs text-zinc-400">
            Generado:{" "}
            {new Date(data.generated_at).toLocaleString("es-ES", {
              hour12: false,
            })}
          </div>
        </div>
      </nav>

      <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-zinc-900">
            Backtest de Estrategia Momentum
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Periodo: {data.period.start} al {data.period.end} &nbsp;·&nbsp;{" "}
            {data.period.trading_days} días de trading &nbsp;·&nbsp;{" "}
            {data.variants.length} variantes comparadas &nbsp;·&nbsp; Capital inicial: $100,000
          </p>
        </div>

        {/* Veredicto */}
        <Verdict variants={allVariants} />

        {/* Selector de variantes */}
        <div className="flex flex-wrap gap-2">
          {allVariants.map((v) => (
            <button
              key={v.id}
              onClick={() => toggleVariant(v.id)}
              className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition-all ${
                activeVariants.has(v.id)
                  ? "ring-transparent shadow-sm"
                  : "bg-white text-zinc-400 ring-zinc-200 opacity-50"
              }`}
              style={
                activeVariants.has(v.id)
                  ? { background: v.color, color: "#fff" }
                  : {}
              }
            >
              {v.label}
            </button>
          ))}
        </div>

        {/* Metrics table */}
        <div className="overflow-x-auto rounded-2xl bg-white shadow-sm ring-1 ring-zinc-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100">
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Variante
                </th>
                {[
                  ["CAGR", "cagr"],
                  ["Total Return", "total_return"],
                  ["Volatilidad", "volatility"],
                  ["Sharpe", "sharpe"],
                  ["Sortino", "sortino"],
                  ["Max DD", "max_drawdown"],
                  ["Calmar", "calmar"],
                  ["Exp. media", "avg_exposure"],
                  ["Nº Trades", "num_trades"],
                ].map(([label, key]) => (
                  <th
                    key={key}
                    className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wider text-zinc-500"
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-50">
              {allVariants.map((v) => {
                const m = v.metrics;
                const isActive = activeVariants.has(v.id);
                return (
                  <tr
                    key={v.id}
                    onClick={() => toggleVariant(v.id)}
                    className={`cursor-pointer transition-colors hover:bg-zinc-50 ${
                      !isActive ? "opacity-40" : ""
                    }`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span
                          className="h-3 w-3 rounded-full flex-shrink-0"
                          style={{ background: v.color }}
                        />
                        <span className="font-semibold text-zinc-900">
                          {v.label}
                        </span>
                      </div>
                    </td>
                    {[
                      ["cagr", pct(m.cagr)],
                      ["total_return", pct(m.total_return)],
                      ["volatility", pct(m.volatility)],
                      ["sharpe", num(m.sharpe)],
                      ["sortino", num(m.sortino)],
                      ["max_drawdown", pct(m.max_drawdown)],
                      ["calmar", num(m.calmar)],
                      ["avg_exposure", pct(m.avg_exposure, 0)],
                      ["num_trades", m.num_trades.toString()],
                    ].map(([key, val]) => (
                      <td
                        key={key as string}
                        className={`px-3 py-3 text-right font-mono font-semibold ${metricClass(
                          key as string,
                          key === "num_trades" ? 0 : (m as any)[key as string]
                        )}`}
                      >
                        {val}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Equity chart */}
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-zinc-200">
          <div className="mb-1 text-sm font-semibold text-zinc-900">
            Curva de equity normalizada (base 100)
          </div>
          <div className="mb-4 text-xs text-zinc-400">
            Capital inicial = 100 · incluye costes de 20bps por operación
          </div>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={equityData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
                <XAxis dataKey="date" hide />
                <YAxis
                  width={55}
                  tickFormatter={(v) => v.toFixed(0)}
                  domain={["auto", "auto"]}
                />
                <Tooltip
                  content={(props: any) => (
                    <CustomTooltip {...props} suffix="" />
                  )}
                />
                <Legend
                  formatter={(value) =>
                    allVariants.find((v) => v.id === value)?.label ?? value
                  }
                />
                {visibleVariants.map((v) => (
                  <Line
                    key={v.id}
                    type="monotone"
                    dataKey={v.id}
                    stroke={v.color}
                    strokeWidth={v.id === "improved" ? 2.5 : 1.5}
                    dot={false}
                    isAnimationActive={false}
                    name={v.id}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Drawdown chart */}
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-zinc-200">
          <div className="mb-1 text-sm font-semibold text-zinc-900">
            Drawdown (%)
          </div>
          <div className="mb-4 text-xs text-zinc-400">
            Pérdida desde el máximo histórico en cada punto
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={drawdownData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
                <XAxis dataKey="date" hide />
                <YAxis
                  width={55}
                  tickFormatter={(v) => v.toFixed(1) + "%"}
                  domain={["auto", 0]}
                />
                <ReferenceLine y={0} stroke="#e4e4e7" />
                <Tooltip
                  content={(props: any) => (
                    <CustomTooltip {...props} suffix="%" />
                  )}
                />
                <Legend
                  formatter={(value) =>
                    allVariants.find((v) => v.id === value)?.label ?? value
                  }
                />
                {visibleVariants.map((v) => (
                  <Line
                    key={v.id}
                    type="monotone"
                    dataKey={v.id}
                    stroke={v.color}
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                    name={v.id}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Exposición chart */}
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-zinc-200">
          <div className="mb-1 text-sm font-semibold text-zinc-900">
            Exposición al mercado (%)
          </div>
          <div className="mb-4 text-xs text-zinc-400">
            Solo estrategias activas · SPY/ACWI son siempre 100%
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={exposureData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
                <XAxis dataKey="date" hide />
                <YAxis
                  width={55}
                  domain={[0, 100]}
                  tickFormatter={(v) => v + "%"}
                />
                <Tooltip
                  content={(props: any) => (
                    <CustomTooltip {...props} suffix="%" />
                  )}
                />
                <Legend
                  formatter={(value) =>
                    allVariants.find((v) => v.id === value)?.label ?? value
                  }
                />
                {visibleVariants
                  .filter((v) => !["spy", "acwi"].includes(v.id))
                  .map((v) => (
                    <Line
                      key={v.id}
                      type="monotone"
                      dataKey={v.id}
                      stroke={v.color}
                      strokeWidth={1.5}
                      dot={false}
                      isAnimationActive={false}
                      name={v.id}
                    />
                  ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Annual returns table */}
        <div className="overflow-x-auto rounded-2xl bg-white shadow-sm ring-1 ring-zinc-200">
          <div className="border-b border-zinc-100 px-5 py-3">
            <div className="text-sm font-semibold text-zinc-900">
              Retornos anuales
            </div>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-100">
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Variante
                </th>
                {years.map((y) => (
                  <th
                    key={y}
                    className="px-3 py-3 text-center text-xs font-semibold uppercase tracking-wider text-zinc-500"
                  >
                    {y}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-50">
              {allVariants.map((v) => (
                <tr key={v.id}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span
                        className="h-3 w-3 rounded-full flex-shrink-0"
                        style={{ background: v.color }}
                      />
                      <span className="font-semibold text-zinc-900">
                        {v.label}
                      </span>
                    </div>
                  </td>
                  {years.map((y) => {
                    const ar = v.annual_returns.find((r) => r.year === y);
                    const val = ar?.return;
                    return (
                      <td key={y} className="px-3 py-3 text-center">
                        {val != null ? (
                          <span
                            className={`inline-block rounded-md px-2 py-0.5 text-xs font-semibold ${annualClass(
                              val
                            )}`}
                          >
                            {pct(val, 1)}
                          </span>
                        ) : (
                          <span className="text-zinc-300">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Diagnóstico */}
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-zinc-200">
            <div className="mb-2 text-sm font-semibold text-zinc-900">
              Cambios implementados (Improved)
            </div>
            <ul className="space-y-1.5 text-xs text-zinc-600">
              <li className="flex gap-2">
                <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-emerald-500" />
                <span>
                  <strong>buy_top_pct: 0.07 → 0.15</strong> — doble de
                  candidatos primarios (6 → 13 con 88 tickers)
                </span>
              </li>
              <li className="flex gap-2">
                <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-emerald-500" />
                <span>
                  <strong>sell_out_pct: 0.20 → 0.30</strong> — menor rotación,
                  menos costes de transacción
                </span>
              </li>
              <li className="flex gap-2">
                <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-emerald-500" />
                <span>
                  <strong>fill_relaxed_trend</strong> — relleno usa{" "}
                  <code>close &gt; sma_100</code> en vez de{" "}
                  <code>sma_50 &gt; sma_100</code>, manteniendo orden por score
                </span>
              </li>
              <li className="flex gap-2">
                <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-emerald-500" />
                <span>
                  <strong>Exposición: 48% → 94%</strong> — problema de cash
                  drag estructural resuelto
                </span>
              </li>
            </ul>
          </div>

          <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-zinc-200">
            <div className="mb-2 text-sm font-semibold text-zinc-900">
              Limitaciones del backtest
            </div>
            <ul className="space-y-1.5 text-xs text-zinc-600">
              <li className="flex gap-2">
                <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-amber-500" />
                <span>
                  <strong>Survivorship bias</strong> — universo de 75 large-caps
                  actualmente activos, sin delisted históricos
                </span>
              </li>
              <li className="flex gap-2">
                <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-amber-500" />
                <span>
                  <strong>Look-ahead parcial</strong> — señal y ejecución al
                  cierre del mismo día (documentado en código)
                </span>
              </li>
              <li className="flex gap-2">
                <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-amber-500" />
                <span>
                  <strong>Costes conservadores</strong> — 20bps fee+slippage
                  por operación
                </span>
              </li>
              <li className="flex gap-2">
                <span className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-zinc-400" />
                <span>
                  <strong>Periodo</strong> — 2023-2026, mercado mayoritariamente
                  alcista con tech dominante. Resultados pueden no extrapolarse
                </span>
              </li>
            </ul>
          </div>
        </div>

        <div className="pb-8 text-center text-xs text-zinc-400">
          Datos: yfinance · Simulación: Python vectorized · Deploy: Vercel
        </div>
      </div>
    </div>
  );
}
