"use client";

import React, { useMemo, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

type Snapshot = {
  ts: string;
  slot?: "OPEN" | "MID" | "CLOSE" | string;
  equityPre?: number | null;
  equityPost?: number | null;
  cash?: number | null;
};

type RangeKey = "1D" | "7D" | "30D" | "ALL";
type SlotKey = "ALL" | "OPEN" | "MID" | "CLOSE";

function fmtMoney(v: number) {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(v);
}

function parseTs(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

function inRange(ts: string, range: RangeKey) {
  if (range === "ALL") return true;

  const d = parseTs(ts);
  if (!d) return false;

  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const day = 24 * 60 * 60 * 1000;

  if (range === "1D") return diff <= day;
  if (range === "7D") return diff <= 7 * day;
  if (range === "30D") return diff <= 30 * day;

  return true;
}

export default function EquityChart({ data }: { data: Snapshot[] }) {
  const [range, setRange] = useState<RangeKey>("ALL");
  const [slot, setSlot] = useState<SlotKey>("ALL");

  const chartData = useMemo(() => {
    const cleaned = (data || [])
      .filter((x) => x && x.ts)
      .filter((x) => inRange(x.ts, range))
      .filter((x) =>
        slot === "ALL" ? true : (x.slot || "").toUpperCase() === slot
      )
      .map((x) => {
        const eq = x.equityPost ?? x.equityPre ?? null;
        return {
          ts: x.ts,
          equity: typeof eq === "number" ? eq : null,
          label: (() => {
            const d = parseTs(x.ts);
            return d
              ? d.toLocaleString("es-ES", { hour12: false })
              : x.ts;
          })(),
        };
      })
      .filter((x) => x.equity !== null);

    cleaned.sort(
      (a, b) => +new Date(a.ts) - +new Date(b.ts)
    );

    return cleaned;
  }, [data, range, slot]);

  const domain = useMemo(() => {
    if (!chartData.length) return undefined;

    const vals = chartData.map((x) => x.equity as number);
    const min = Math.min(...vals);
    const max = Math.max(...vals);

    // Caso plano (todos iguales)
    if (min === max) {
      const pad = Math.max(100, min * 0.01);
      return [min - pad, max + pad] as [number, number];
    }

    const pad = Math.max(50, (max - min) * 0.15);
    return [min - pad, max + pad] as [number, number];
  }, [chartData]);

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-zinc-200">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-sm font-medium text-zinc-900">
            Equity
          </div>
          <div className="text-xs text-zinc-500">
            {chartData.length
              ? `${chartData.length} puntos`
              : "Sin datos"}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Slot filter */}
          <div className="flex items-center gap-1 rounded-full bg-zinc-100 p-1">
            {(["ALL", "OPEN", "MID", "CLOSE"] as SlotKey[]).map(
              (k) => (
                <button
                  key={k}
                  onClick={() => setSlot(k)}
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    slot === k
                      ? "bg-white shadow-sm"
                      : "text-zinc-600"
                  }`}
                >
                  {k}
                </button>
              )
            )}
          </div>

          {/* Range filter */}
          <div className="flex items-center gap-1 rounded-full bg-zinc-100 p-1">
            {(["1D", "7D", "30D", "ALL"] as RangeKey[]).map(
              (k) => (
                <button
                  key={k}
                  onClick={() => setRange(k)}
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    range === k
                      ? "bg-white shadow-sm"
                      : "text-zinc-600"
                  }`}
                >
                  {k}
                </button>
              )
            )}
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="mt-4 h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" hide />
            <YAxis
              domain={domain}
              width={90}
              tickFormatter={(v) =>
                new Intl.NumberFormat("es-ES", {
                  notation: "compact",
                  compactDisplay: "short",
                  maximumFractionDigits: 1,
                }).format(Number(v))
              }
            />
            <Tooltip
              labelFormatter={(_, payload) => {
                const p: any = payload?.[0]?.payload;
                return p?.label ?? "";
              }}
              formatter={(value: any) => [
                fmtMoney(Number(value)),
                "Equity",
              ]}
            />
            <Line
              type="monotone"
              dataKey="equity"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
