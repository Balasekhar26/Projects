import { NextResponse } from "next/server";
import { initializeDatabase } from "@/lib/migrate";

export async function GET() {
  try {
    await initializeDatabase();
    return NextResponse.json({ success: true, message: "Database initialized" });
  } catch (error) {
    console.error("Database initialization failed:", error);
    return NextResponse.json(
      { error: "Database initialization failed" },
      { status: 500 }
    );
  }
}