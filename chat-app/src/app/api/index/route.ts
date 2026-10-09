import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: Request) {
  try {
    const body = await request.text();
    const response = await fetch(`${BACKEND_URL}/api/index`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error("Index API route error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
