import { NextResponse } from "next/server";
import { promises as fs } from "fs";

const HISTORY_PATH = "/home/ubuntu/n8n-files/history.json";

export async function GET() {
  try {
    const raw = await fs.readFile(HISTORY_PATH, "utf8");

    // history.json debería ser un array JSON: [ {..}, {..} ]
    const data = raw.trim() ? JSON.parse(raw) : [];

    return NextResponse.json(
      { ok: true, count: Array.isArray(data) ? data.length : 0, data },
      { status: 200 }
    );
  } catch (err: any) {
    // Si el archivo no existe aún, devolvemos array vacío en vez de petar
    if (err?.code === "ENOENT") {
      return NextResponse.json({ ok: true, count: 0, data: [] }, { status: 200 });
    }

    return NextResponse.json(
      { ok: false, error: err?.message ?? "Unknown error" },
      { status: 500 }
    );
  }
}
