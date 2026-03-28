import { NextResponse } from "next/server";

const EC2_API = process.env.EC2_API_URL ?? "http://13.61.27.226:5000";

export async function GET() {
  try {
    const res = await fetch(`${EC2_API}/history`, { cache: "no-store" });
    if (!res.ok) throw new Error(`EC2 /history returned ${res.status}`);
    const data = await res.json();
    return NextResponse.json(
      { ok: true, count: Array.isArray(data) ? data.length : 0, data },
      { status: 200 }
    );
  } catch (err: any) {
    return NextResponse.json({ ok: true, count: 0, data: [] }, { status: 200 });
  }
}
