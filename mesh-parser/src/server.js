import crypto from 'node:crypto';
import http from 'node:http';
import {createMeshService} from './app.js';
import {readConfig} from './config.js';
import {createMeshClient, MeshUpstreamError} from './mesh-client.js';

const config = readConfig();
let executeMesh;
let startupError;
try {
  executeMesh = createMeshService({client: createMeshClient(config), cacheTtlMs: config.cacheTtlMs});
} catch (error) {
  startupError = error;
}

function authorized(request) {
  if (!config.serviceKey) return true;
  const supplied = String(request.headers['x-mesh-key'] ?? '');
  const expectedBuffer = Buffer.from(config.serviceKey);
  const suppliedBuffer = Buffer.from(supplied);
  return expectedBuffer.length === suppliedBuffer.length && crypto.timingSafeEqual(expectedBuffer, suppliedBuffer);
}

function send(response, status, body) {
  const data = JSON.stringify(body);
  response.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(data),
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff',
  });
  response.end(data);
}

async function readJson(request) {
  const chunks = [];
  let length = 0;
  for await (const chunk of request) {
    length += chunk.length;
    if (length > 32768) throw Object.assign(new Error('Request body is too large'), {status: 413, code: 'BODY_TOO_LARGE'});
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); }
  catch { throw Object.assign(new Error('Request body must be valid JSON'), {status: 400, code: 'INVALID_JSON'}); }
}

const server = http.createServer(async (request, response) => {
  const started = Date.now();
  let status = 500;
  try {
    const url = new URL(request.url, `http://${request.headers.host || 'localhost'}`);
    if (request.method === 'GET' && url.pathname === '/health') {
      status = startupError ? 503 : 200;
      send(response, status, {ok: !startupError, configured: !startupError, service: 'spiritjeronion-mesh-parser'});
      return;
    }
    if (request.method !== 'POST' || url.pathname !== '/mesh') {
      status = 404;
      send(response, status, {ok: false, error: {code: 'NOT_FOUND', message: 'Use POST /mesh'}});
      return;
    }
    if (!authorized(request)) {
      status = 401;
      send(response, status, {ok: false, error: {code: 'UNAUTHORIZED', message: 'Invalid service key'}});
      return;
    }
    if (startupError) throw startupError;
    const body = await readJson(request);
    const result = await executeMesh(body);
    status = 200;
    send(response, status, result);
  } catch (error) {
    status = Number(error?.status) || (error instanceof MeshUpstreamError ? error.status : 500);
    const code = error?.code || 'INTERNAL_ERROR';
    const message = status >= 500 && code === 'INTERNAL_ERROR' ? 'Internal parser error' : error.message;
    send(response, status, {ok: false, error: {code, message}});
  } finally {
    process.stdout.write(`${new Date().toISOString()} ${request.method} ${request.url} ${status} ${Date.now() - started}ms\n`);
  }
});

server.listen(config.port, config.host, () => {
  process.stdout.write(`MESH parser listening on http://${config.host}:${config.port}\n`);
  if (startupError) process.stdout.write('MESH parser is not configured yet; fill .env and restart.\n');
});

function shutdown() {
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 5000).unref();
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
