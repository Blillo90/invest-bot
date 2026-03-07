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
