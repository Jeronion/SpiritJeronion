import fs from 'node:fs';
import path from 'node:path';

function unquote(value) {
  const trimmed = value.trim();
  if (trimmed.length >= 2 && ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'")))) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

export function loadEnvFile(filePath = path.resolve('.env')) {
  if (!fs.existsSync(filePath)) return;
  const content = fs.readFileSync(filePath, 'utf8');
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const separator = line.indexOf('=');
    if (separator <= 0) continue;
    const key = line.slice(0, separator).trim();
    if (!/^[A-Z_][A-Z0-9_]*$/i.test(key) || process.env[key] !== undefined) continue;
    process.env[key] = unquote(line.slice(separator + 1));
  }
}

function integer(name, fallback, minimum, maximum) {
  const value = Number(process.env[name] ?? fallback);
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${name} must be an integer between ${minimum} and ${maximum}`);
  }
  return value;
}

export function readConfig() {
  loadEnvFile();
  const config = {
    studentId: String(process.env.MESH_STUDENT_ID ?? '').trim(),
    token: String(process.env.MESH_TOKEN ?? '').trim(),
    serviceKey: String(process.env.MESH_SERVICE_KEY ?? '').trim(),
    host: String(process.env.MESH_HOST ?? '127.0.0.1').trim(),
    port: integer('MESH_PORT', 8787, 1, 65535),
    timeoutMs: integer('MESH_TIMEOUT_MS', 20000, 1000, 120000),
    cacheTtlMs: integer('MESH_CACHE_TTL_MS', 120000, 0, 3600000),
  };
  const loopbackHosts = new Set(['127.0.0.1', 'localhost', '::1']);
  if (!loopbackHosts.has(config.host) && !config.serviceKey) {
    throw new Error('MESH_SERVICE_KEY is required when MESH_HOST is not loopback');
  }
  return config;
}
