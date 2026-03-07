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
