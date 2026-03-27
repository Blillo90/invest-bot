import { NextResponse } from "next/server";
import { promises as fs } from "fs";

const TRADES_PATH = "/home/ubuntu/quant-bot/trades.json";

export async function GET() {
  try {
    const raw = await fs.readFile(TRADES_PATH, "utf8");
    const data = raw.trim() ? JSON.parse(raw) : [];
    return NextResponse.json(
      { ok: true, count: Array.isArray(data) ? data.length : 0, data },
      { status: 200 }
    );
  } catch (err: any) {
    if (err?.code === "ENOENT") {
      return NextResponse.json({ ok: true, count: 0, data: [] }, { status: 200 });
    }
    return NextResponse.json(
      { ok: false, error: err?.message ?? "Unknown error" },
      { status: 500 }
    );
  }
}
