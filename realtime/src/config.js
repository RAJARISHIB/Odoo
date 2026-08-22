/**
 * Runtime configuration.
 *
 * JWT_SECRET and INTERNAL_API_KEY must match the Django API exactly - the hub
 * verifies the same access tokens Django issues, and Django authenticates to
 * the internal publish endpoint with the shared key.
 */
import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(here, '../.env') });

const str = (key, fallback = '') => (process.env[key] ?? '').trim() || fallback;
const int = (key, fallback) => {
  const value = Number.parseInt(process.env[key] ?? '', 10);
  return Number.isNaN(value) ? fallback : value;
};
const list = (key, fallback = []) => {
  const raw = str(key);
  return raw ? raw.split(',').map((item) => item.trim()).filter(Boolean) : fallback;
};

export const config = {
  env: str('NODE_ENV', 'development'),
  port: int('REALTIME_PORT', 4000),
  wsPath: str('REALTIME_WS_PATH', '/ws'),

  jwt: {
    secret: str('JWT_SECRET', 'change-me-in-production-super-secret'),
    algorithm: str('JWT_ALGORITHM', 'HS256'),
    issuer: str('JWT_ISSUER', 'hrms-api'),
  },

  internalApiKey: str('INTERNAL_API_KEY', 'change-me-internal-service-key'),

  django: {
    baseUrl: str('DJANGO_API_URL', 'http://localhost:8000'),
    // Presence callbacks are best-effort; the hub keeps working if Django is down.
    presencePath: str('DJANGO_PRESENCE_PATH', '/api/v1/internal/realtime/presence'),
    presenceEnabled: str('PRESENCE_CALLBACK_ENABLED', 'true') === 'true',
    timeoutMs: int('DJANGO_TIMEOUT_MS', 5000),
  },

  corsOrigins: list('CORS_ALLOWED_ORIGINS', ['http://localhost:4200']),

  // Sockets that miss two heartbeats are dropped, so dead tabs free their slot.
  heartbeatIntervalMs: int('WS_HEARTBEAT_INTERVAL_MS', 30000),
  // Grace period for a client that connects without a token in the query string
  // and intends to authenticate with a first `auth` message instead.
  authGraceMs: int('WS_AUTH_GRACE_MS', 5000),
  maxConnectionsPerUser: int('WS_MAX_CONNECTIONS_PER_USER', 10),
  logLevel: str('LOG_LEVEL', 'info'),
};

export default config;
