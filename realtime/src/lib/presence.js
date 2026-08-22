/**
 * Presence callbacks: the hub tells Django when a user's socket count changes.
 *
 * Best-effort and non-blocking - a Django outage must never stop sockets from
 * connecting, so failures are logged and swallowed.
 */
import { config } from '../config.js';
import { logger } from './logger.js';

export async function reportPresence({ event, identity, connectionCount, panel, connectionId }) {
  if (!config.django.presenceEnabled) return false;

  const url = config.django.baseUrl.replace(/\/$/, '') + config.django.presencePath;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.django.timeoutMs);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-internal-key': config.internalApiKey,
      },
      body: JSON.stringify({
        event,                                  // 'connected' | 'disconnected'
        user_id: identity.userId,
        email: identity.email,
        role: identity.role,
        org_id: identity.orgId,
        panel: panel ?? null,
        connection_id: connectionId,
        connection_count: connectionCount,
        at: new Date().toISOString(),
      }),
      signal: controller.signal,
    });
    if (!response.ok) {
      logger.warn('Presence callback rejected', { status: response.status });
      return false;
    }
    return true;
  } catch (error) {
    logger.warn('Presence callback failed', { error: error.message });
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export default reportPresence;
