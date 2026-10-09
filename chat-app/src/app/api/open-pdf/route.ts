import { NextRequest, NextResponse } from "next/server";

// Get backend URL from environment variable or default
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const path = searchParams.get("path");

    if (!path) {
      return NextResponse.json(
        { error: "Path parameter is required" },
        { status: 400 },
      );
    }

    // Forward the request to the FastAPI backend (open-file endpoint)
    const response = await fetch(
      `${BACKEND_URL}/api/open-file?path=${encodeURIComponent(path)}`,
      {
        method: "GET",
      },
    );

    if (!response.ok) {
      return NextResponse.json(
        { error: `Backend error: ${response.status}` },
        { status: response.status },
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Open PDF API route error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
