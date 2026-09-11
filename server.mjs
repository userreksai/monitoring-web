import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer, request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { extname, resolve, sep } from "node:path";

const port = Number(process.env.PORT || 8900);
const apiBaseUrl = new URL(process.env.API_BASE_URL || "http://127.0.0.1:8901");
const distRoot = resolve(process.cwd(), "dist");
const indexFile = resolve(distRoot, "index.html");

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function proxyApi(clientRequest, clientResponse) {
  const target = new URL(clientRequest.url, apiBaseUrl);
  const transport = target.protocol === "https:" ? httpsRequest : httpRequest;
  const headers = { ...clientRequest.headers, host: target.host };

  const upstreamRequest = transport(target, { method: clientRequest.method, headers }, (upstreamResponse) => {
    clientResponse.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers);
    upstreamResponse.pipe(clientResponse);
  });

  upstreamRequest.on("error", (error) => {
    if (clientResponse.headersSent) {
      clientResponse.destroy(error);
      return;
    }
    clientResponse.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
    clientResponse.end(JSON.stringify({ error: "后端服务暂不可用", detail: error.message }));
  });
  clientRequest.on("aborted", () => upstreamRequest.destroy());
  clientRequest.pipe(upstreamRequest);
}

function serveFrontend(request, response) {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(request.url, `http://${request.headers.host || "localhost"}`).pathname);
  } catch {
    response.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("Bad Request");
    return;
  }

  const relativePath = pathname.replace(/^\/+/, "");
  const candidate = resolve(distRoot, relativePath || "index.html");
  const insideDist = candidate === distRoot || candidate.startsWith(`${distRoot}${sep}`);
  let filePath = insideDist && existsSync(candidate) && statSync(candidate).isFile() ? candidate : indexFile;

  if (!existsSync(filePath)) {
    response.writeHead(503, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
    response.end(JSON.stringify({ error: "前端构建产物不存在，请先执行 pnpm run build" }));
    return;
  }

  const extension = extname(filePath).toLowerCase();
  const immutableAsset = filePath !== indexFile && /\.[a-f0-9]{8,}\./i.test(filePath);
  response.writeHead(200, {
    "Content-Type": mimeTypes[extension] || "application/octet-stream",
    "Cache-Control": immutableAsset ? "public, max-age=31536000, immutable" : "no-cache",
  });
  createReadStream(filePath).on("error", () => response.destroy()).pipe(response);
}

createServer((request, response) => {
  const pathname = new URL(request.url, `http://${request.headers.host || "localhost"}`).pathname;
  if (pathname === "/api" || pathname.startsWith("/api/")) {
    proxyApi(request, response);
    return;
  }
  serveFrontend(request, response);
}).listen(port, "0.0.0.0", () => {
  console.log(`Monitoring frontend: http://0.0.0.0:${port}`);
  console.log(`API proxy target: ${apiBaseUrl.origin}`);
});
