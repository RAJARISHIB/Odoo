/**
 * HRMS realtime hub.
 *
 *   Angular  --ws://host/ws?token=...-->  this server  <--POST /internal/publish--  Django
 *
 * One process serves both: an Express app for the internal HTTP API and a
 * `ws` server sharing the same port for browser sockets.
 */
import cors from 'cors';
import express from 'express';
import http from 'node:http';
import { WebSocketServer } from 'ws';

import { AuthError, tokenFromRequest, verifyAccessToken } from './lib/auth.js';
import { config } from './config.js';
import { handleConnection } from './ws/connection.js';
import { healthRouter } from './routes/health.js';
import { hub } from './lib/hub.js';
import { internalRouter } from './routes/internal.js';
import { logger } from './lib/logger.js';

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------
const app = express();

app.use(express.json({ limit: '1mb' }));
app.use(
  cors({
    origin: config.corsOrigins,
    credentials: true,
    allowedHeaders: ['Content-Type', 'Authorization', 'x-internal-key'],
  }),
);

app.use('/', healthRouter);
app.use('/internal', internalRouter);

app.use((_req, res) => {
  res.status(404).json({
    success: false,
    error: { code: 'not_found', message: 'Endpoint not found.' },
  });
});

// eslint-disable-next-line no-unused-vars -- Express identifies error handlers by arity.
app.use((error, _req, res, _next) => {
  logger.error('HTTP error', { error: error.message });
  res.status(500).json({
    success: false,
    error: { code: 'internal_error', message: 'An unexpected error occurred.' },
  });
});

const server = http.createServer(app);

// ---------------------------------------------------------------------------
// WebSocket
// ---------------------------------------------------------------------------
// `noServer` so the handshake can be rejected before the upgrade completes -
// a client with a bad token never becomes a socket.
const wss = new WebSocketServer({ noServer: true, maxPayload: 64 * 1024 });

server.on('upgrade', (request, socket, head) => {
  const { pathname } = new URL(request.url, 'http://localhost');
  if (pathname !== config.wsPath) {
    socket.write('HTTP/1.1 404 Not Found\r\n\r\n');
    socket.destroy();
    return;
  }

  const token = tokenFromRequest(request);
  let identity = null;

  if (token) {
    try {
      identity = verifyAccessToken(token);
    } catch (error) {
      const code = error instanceof AuthError ? error.code : 'unauthenticated';
      logger.warn('Rejected websocket handshake', { code });
      socket.write('HTTP/1.1 401 Unauthorized\r\n\r\n');
      socket.destroy();
      return;
    }
  }
  // No token at handshake is allowed: the client then has `authGraceMs` to send
  // an `auth` frame (used by clients that cannot put a token in the URL).

  wss.handleUpgrade(request, socket, head, (ws) => {
    wss.emit('connection', ws, request, identity);
  });
});

wss.on('connection', (socket, request, identity) => {
  handleConnection(socket, request, identity);
});

hub.startHeartbeat();

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
server.listen(config.port, () => {
  logger.info('Realtime hub listening', {
    port: config.port,
    ws: `ws://localhost:${config.port}${config.wsPath}`,
    env: config.env,
  });
});

function shutdown(signal) {
  logger.info(`Received ${signal}, shutting down.`);
  hub.shutdown();
  wss.close();
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 5000).unref();
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('unhandledRejection', (reason) => {
  logger.error('Unhandled rejection', { reason: String(reason) });
});

export { app, server, wss };
