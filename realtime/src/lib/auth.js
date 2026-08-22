/**
 * Authentication for both directions of the hub:
 *   - browsers presenting a Django-issued JWT access token
 *   - Django presenting the shared internal key on /internal/*
 */
import crypto from 'node:crypto';
import jwt from 'jsonwebtoken';

import { config } from '../config.js';

export class AuthError extends Error {
  constructor(message, code = 'unauthenticated') {
    super(message);
    this.code = code;
  }
}

/**
 * Verify an access token and reduce it to the identity the hub cares about.
 * Claim names come from `backend/core/security.py`.
 */
export function verifyAccessToken(token) {
  if (!token) throw new AuthError('Missing access token.', 'token_missing');

  let payload;
  try {
    payload = jwt.verify(token, config.jwt.secret, {
      algorithms: [config.jwt.algorithm],
      issuer: config.jwt.issuer,
    });
  } catch (error) {
    const code = error.name === 'TokenExpiredError' ? 'token_expired' : 'token_invalid';
    throw new AuthError(error.message, code);
  }

  if (payload.typ !== 'access') {
    throw new AuthError('A refresh token cannot open a socket.', 'token_wrong_type');
  }

  return {
    userId: String(payload.sub),
    email: payload.email ?? null,
    name: payload.name ?? null,
    role: payload.role ?? 'employee',
    orgId: payload.org_id ? String(payload.org_id) : null,
    jti: payload.jti,
    expiresAt: payload.exp ? new Date(payload.exp * 1000).toISOString() : null,
  };
}

/**
 * Pull the token off the handshake. Browsers cannot set headers on a WebSocket,
 * so the query string is the practical path; the header form is supported for
 * server-side clients and tests.
 */
export function tokenFromRequest(request) {
  const url = new URL(request.url, 'http://localhost');
  const queryToken = url.searchParams.get('token') || url.searchParams.get('access_token');
  if (queryToken) return queryToken;

  const header = request.headers.authorization ?? '';
  const [scheme, value] = header.split(' ');
  if (scheme?.toLowerCase() === 'bearer' && value) return value;

  // `Sec-WebSocket-Protocol: bearer, <token>` - used by some WS clients.
  const protocol = request.headers['sec-websocket-protocol'];
  if (protocol) {
    const parts = protocol.split(',').map((part) => part.trim());
    if (parts.length === 2 && parts[0].toLowerCase() === 'bearer') return parts[1];
  }

  return null;
}

/** Constant-time comparison so the internal key cannot be probed by timing. */
export function verifyInternalKey(provided) {
  const expected = config.internalApiKey;
  if (!provided || typeof provided !== 'string') return false;
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

/** Express guard for the /internal/* routes. */
export function internalOnly(req, res, next) {
  if (!verifyInternalKey(req.get('x-internal-key'))) {
    return res.status(403).json({
      success: false,
      error: { code: 'invalid_internal_key', message: 'Invalid internal service key.' },
    });
  }
  return next();
}
