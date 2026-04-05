import { readFile } from "fs/promises";
import { extname } from "path";
import { LiteParse } from "@llamaindex/liteparse";
import mammoth from "mammoth";
import ExcelJS from "exceljs";
import { createOpenAI } from "@ai-sdk/openai";
import { generateText } from "ai";
import * as cheerio from "cheerio";
import * as yaml from "yaml";
import { env } from "@/env";
import { logger } from "@/lib/logger";
import type { ParsedSegment } from "@/lib/chunker";

export type { ParsedSegment };

const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp"]);

const TEXT_EXTENSIONS = new Set([
  ".md",
  ".txt",
  ".log",
  ".csv",
  ".json",
  ".yaml",
  ".yml",
  ".html",
  ".htm",
  ".xml",
  ".ts",
  ".js",
  ".py",
  ".sh",
  ".sql",
]);

const MIME_MAP: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
};

/**
 * 解析文件为 ParsedSegment[]。
 * - PDF: LiteParse（纯 JS，无需 LibreOffice）
 * - DOCX: mammoth（纯 JS）
 * - XLSX/XLS: exceljs（纯 JS），按工作表分 segment
 * - 文本格式: 直接读取
 * - 图片: Vision API 生成描述
 */
export async function parseFile(
  filePath: string,
  filename: string,
): Promise<ParsedSegment[]> {
  const ext = extname(filename).toLowerCase();

  switch (ext) {
    case ".pdf":
      return parsePdf(filePath);
    case ".docx":
    case ".doc":
      return parseDocx(filePath);
    case ".xlsx":
    case ".xls":
      return parseXlsx(filePath);
    default:
      if (IMAGE_EXTENSIONS.has(ext)) return parseImage(filePath, filename);
      if (TEXT_EXTENSIONS.has(ext)) return parseTextFile(filePath, ext);
      // 未知格式尝试当文本读取
      return parseTextFile(filePath, ext);
  }
}

// ── PDF ──────────────────────────────────────────────────

async function parsePdf(filePath: string): Promise<ParsedSegment[]> {
  const parser = new LiteParse({
    ocrEnabled: false,
    preciseBoundingBox: false,
  });

  const result = await parser.parse(filePath, true);

  return result.pages
    .filter((page) => page.text.trim())
    .map((page) => ({
      content: page.text.trim(),
      metadata: { page: page.pageNum },
    }));
}

// ── DOCX ─────────────────────────────────────────────────

async function parseDocx(filePath: string): Promise<ParsedSegment[]> {
  const buffer = await readFile(filePath);
  const { value: text } = await mammoth.extractRawText({ buffer });
  if (!text.trim()) return [];
  return [{ content: text, metadata: {} }];
}

// ── XLSX ─────────────────────────────────────────────────

async function parseXlsx(filePath: string): Promise<ParsedSegment[]> {
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.readFile(filePath);

  const segments: ParsedSegment[] = [];

  workbook.eachSheet((sheet) => {
    const rows: string[] = [];
    sheet.eachRow((row) => {
      const cells = Array.isArray(row.values)
        ? row.values.slice(1) // exceljs row.values[0] is always undefined
        : [];
      rows.push(cells.map((c) => String(c ?? "")).join("\t"));
    });
    const content = rows.join("\n");
    if (content.trim()) {
      segments.push({ content, metadata: { sheet: sheet.name } });
    }
  });

  return segments;
}

// ── 图片 ─────────────────────────────────────────────────

async function parseImage(
  filePath: string,
  filename: string,
): Promise<ParsedSegment[]> {
  const bytes = await readFile(filePath);
  const ext = extname(filename).toLowerCase();
  const mime = MIME_MAP[ext] || "image/png";
  const b64 = bytes.toString("base64");

  const dashscope = createOpenAI({
    apiKey: env.DASHSCOPE_API_KEY,
    baseURL: env.LLM_BASE_URL,
  });

  const { text } = await generateText({
    model: dashscope.chat(env.VISION_MODEL),
    messages: [
      {
        role: "user",
        content: [
          { type: "image", image: `data:${mime};base64,${b64}` },
          { type: "text", text: "请详细描述这张图片的内容。" },
        ],
      },
    ],
    maxOutputTokens: 1000,
  });

  logger.info({ filename }, "Image described via Vision API");

  return [{ content: text, metadata: { source: "vision_description" } }];
}

// ── 文本格式 ─────────────────────────────────────────────

async function parseTextFile(
  filePath: string,
  ext: string,
): Promise<ParsedSegment[]> {
  const raw = await readFile(filePath, "utf-8");

  let content: string;

  switch (ext) {
    case ".json": {
      try {
        content = JSON.stringify(JSON.parse(raw), null, 2);
      } catch {
        content = raw;
      }
      break;
    }
    case ".yaml":
    case ".yml": {
      try {
        content = yaml.stringify(yaml.parse(raw));
      } catch {
        content = raw;
      }
      break;
    }
    case ".html":
    case ".htm": {
      const $ = cheerio.load(raw);
      $("script, style").remove();
      content = $("body").text().trim() || raw;
      break;
    }
    default:
      content = raw;
  }

  if (!content.trim()) return [];
  return [{ content, metadata: {} }];
}
