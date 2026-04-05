/**
 * 生成测试用的 PDF / DOCX / XLSX fixture 文件。
 * 运行: bun tests/fixtures/generate.ts
 */
import { writeFile } from "fs/promises";
import { join } from "path";
import { PDFDocument, StandardFonts } from "pdf-lib";
import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
} from "docx";
import ExcelJS from "exceljs";

const DIR = import.meta.dir;

async function genPdf() {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const page = doc.addPage();

  const lines = [
    { text: "MySQL Slow Query Troubleshooting Guide", size: 16, y: 740 },
    { text: "Step 1: Enable slow query log: SET GLOBAL slow_query_log = ON;", size: 11, y: 710 },
    { text: "Step 2: Set threshold: SET GLOBAL long_query_time = 1;", size: 11, y: 694 },
    { text: "Step 3: Use EXPLAIN to analyze query execution plan.", size: 11, y: 678 },
    { text: "Step 4: Check for missing indexes on frequently queried columns.", size: 11, y: 662 },
    { text: "Step 5: Optimize SQL structure, avoid SELECT * and subqueries.", size: 11, y: 646 },
    { text: "Step 6: Monitor replication lag on slave nodes.", size: 11, y: 630 },
    { text: "Step 7: Review connection pool settings for high-traffic services.", size: 11, y: 614 },
  ];

  for (const { text, size, y } of lines) {
    page.drawText(text, { x: 50, y, size, font });
  }

  await writeFile(join(DIR, "sample.pdf"), await doc.save());
  console.log("  sample.pdf");
}

async function genDocx() {
  const doc = new Document({
    sections: [
      {
        children: [
          new Paragraph({
            text: "Nginx 反向代理配置",
            heading: HeadingLevel.HEADING_1,
          }),
          new Paragraph({
            children: [
              new TextRun("本文档说明生产环境 Nginx 的核心配置项。"),
            ],
          }),
          new Paragraph({
            text: "upstream 配置",
            heading: HeadingLevel.HEADING_2,
          }),
          new Paragraph({
            children: [
              new TextRun(
                "upstream backend {\n" +
                  "    server 10.0.1.10:8080 weight=3;\n" +
                  "    server 10.0.1.11:8080 weight=2;\n" +
                  "    keepalive 32;\n" +
                  "}",
              ),
            ],
          }),
          new Paragraph({
            text: "location 配置",
            heading: HeadingLevel.HEADING_2,
          }),
          new Paragraph({
            children: [
              new TextRun(
                "location /api/ {\n" +
                  "    proxy_pass http://backend;\n" +
                  "    proxy_set_header Host $host;\n" +
                  "    proxy_connect_timeout 5s;\n" +
                  "}",
              ),
            ],
          }),
        ],
      },
    ],
  });

  const buffer = await Packer.toBuffer(doc);
  await writeFile(join(DIR, "sample.docx"), buffer);
  console.log("  sample.docx");
}

async function genXlsx() {
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet("服务器清单");

  ws.addRow(["主机名", "IP地址", "CPU", "内存", "角色", "状态"]);
  ws.addRow(["web-01", "10.0.1.10", "8C", "16Gi", "Web服务器", "在线"]);
  ws.addRow(["web-02", "10.0.1.11", "8C", "16Gi", "Web服务器", "在线"]);
  ws.addRow(["db-master", "10.0.2.10", "16C", "64Gi", "数据库主", "在线"]);
  ws.addRow(["db-slave", "10.0.2.11", "16C", "64Gi", "数据库从", "在线"]);
  ws.addRow(["redis-01", "10.0.3.10", "4C", "32Gi", "缓存", "在线"]);

  await wb.xlsx.writeFile(join(DIR, "sample.xlsx"));
  console.log("  sample.xlsx");
}

async function genPng() {
  // 生成一个 32x32 像素的 PNG，四色象限（红/绿/蓝/黄），Vision 模型能识别颜色
  const width = 32;
  const height = 32;

  // 像素数据：每行 = filter byte(0) + RGBA * width
  const rawData: number[] = [];
  const colors = [
    [255, 0, 0, 255],   // 左上：红
    [0, 128, 0, 255],   // 右上：绿
    [0, 0, 255, 255],   // 左下：蓝
    [255, 255, 0, 255], // 右下：黄
  ];
  for (let y = 0; y < height; y++) {
    rawData.push(0); // filter: None
    for (let x = 0; x < width; x++) {
      const ci = (y < height / 2 ? 0 : 2) + (x < width / 2 ? 0 : 1);
      rawData.push(...colors[ci]);
    }
  }

  // zlib deflate
  const deflated = Bun.deflateSync(new Uint8Array(rawData));

  // PNG 构建辅助
  function crc32(buf: Uint8Array): number {
    let c = 0xffffffff;
    for (const b of buf) {
      c ^= b;
      for (let i = 0; i < 8; i++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
    }
    return (c ^ 0xffffffff) >>> 0;
  }

  function chunk(type: string, data: Uint8Array): Uint8Array {
    const typeBytes = new TextEncoder().encode(type);
    const buf = new Uint8Array(4 + 4 + data.length + 4);
    const view = new DataView(buf.buffer);
    view.setUint32(0, data.length);
    buf.set(typeBytes, 4);
    buf.set(data, 8);
    const crcData = new Uint8Array(4 + data.length);
    crcData.set(typeBytes);
    crcData.set(data, 4);
    view.setUint32(8 + data.length, crc32(crcData));
    return buf;
  }

  // IHDR: width, height, bit depth 8, color type 6 (RGBA)
  const ihdrData = new Uint8Array(13);
  const ihdrView = new DataView(ihdrData.buffer);
  ihdrView.setUint32(0, width);
  ihdrView.setUint32(4, height);
  ihdrData[8] = 8;  // bit depth
  ihdrData[9] = 6;  // color type: RGBA
  ihdrData[10] = 0; // compression
  ihdrData[11] = 0; // filter
  ihdrData[12] = 0; // interlace

  const signature = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = chunk("IHDR", ihdrData);
  const idat = chunk("IDAT", deflated);
  const iend = chunk("IEND", new Uint8Array(0));

  const png = new Uint8Array(signature.length + ihdr.length + idat.length + iend.length);
  let offset = 0;
  for (const part of [signature, ihdr, idat, iend]) {
    png.set(part, offset);
    offset += part.length;
  }

  await writeFile(join(DIR, "sample.png"), png);
  console.log("  sample.png");
}

await genPdf();
await genDocx();
await genXlsx();
await genPng();
console.log("Done!");
