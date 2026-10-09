import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/api/index/status`, {
      signal: AbortSignal.timeout(5000),
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ status: "error", message: "Backend niet bereikbaar" }, { status: 503 });
  }
}
