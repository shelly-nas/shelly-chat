import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

// The frontend container cannot reach Qdrant or Ollama directly — they are on
// different Docker networks and/or behind host.docker.internal. The backend
// already checks both via its own /status endpoint using the correct internal
// hostnames, so we proxy there instead of making direct connections here.
export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/status`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      return NextResponse.json({ backend: "unhealthy", qdrant: "unknown", ollama: "unknown" });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ backend: "unreachable", qdrant: "unknown", ollama: "unknown" });
  }
}
