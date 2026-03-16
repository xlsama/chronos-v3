import { readFileSync } from "fs";
import { resolve } from "path";
import dotenv from "dotenv";

let loaded = false;

export function loadEnv(): void {
  if (loaded) return;
  loaded = true;

  // Load backend/.env for secrets
  const envPath = resolve(import.meta.dirname, "../../backend/.env");
  try {
    const content = readFileSync(envPath, "utf-8");
    const parsed = dotenv.parse(content);
    for (const [key, value] of Object.entries(parsed)) {
      if (!process.env[key]) {
        process.env[key] = value;
      }
    }
  } catch {
    // .env file is optional if vars are set in environment
  }
}

export function requireEnv(key: string): string {
  loadEnv();
  const value = process.env[key];
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}. Set it in env or backend/.env`);
  }
  return value;
}
