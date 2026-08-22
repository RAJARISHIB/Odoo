/**
 * Internal HTTP surface - how Django reaches the hub.
 *
 * Every route here is authenticated with the shared `x-internal-key` header,
 * never a user token, and must not be exposed to the public internet.
 */
import { Router } from 'express';

import { internalOnly } from '../lib/auth.js';
import { hub } from '../lib/hub.js';
import { logger } from '../lib/logger.js';

export const internalRouter = Router();

internalRouter.use(internalOnly);

/**
 * POST /internal/publish
 *
 * Body (produced by `backend/core/realtime.py::publish`):
 *   { id, event, channels: [], payload: {}, actor_id, emitted_at, source }
 */
internalRouter.post('/publish', (req, res) => {
  const { id, event, channels, payload, actor_id: actorId, emitted_at: emittedAt, source } = req.body ?? {};

  if (typeof event !== 'string' || !event.length) {
    return res.status(422).json({
      success: false,
      error: { code: 'invalid_event', message: '"event" is required.' },
    });
  }
  if (!Array.isArray(channels) || !channels.length) {
    return res.status(422).json({
      success: false,
      error: { code: 'invalid_channels', message: '"channels" must be a non-empty array.' },
    });
  }

  const result = hub.publish({ id, event, channels, payload, emittedAt, actorId, source });
  logger.info('Publish', { event, channels, delivered: result.delivered });

  return res.json({ success: true, data: { event, channels, ...result } });
});

/** POST /internal/broadcast - shorthand for the `broadcast` channel. */
internalRouter.post('/broadcast', (req, res) => {
  const { event, payload } = req.body ?? {};
  if (!event) {
    return res.status(422).json({
      success: false,
      error: { code: 'invalid_event', message: '"event" is required.' },
    });
  }
  const result = hub.publish({ event, channels: ['broadcast'], payload, source: 'django' });
  return res.json({ success: true, data: { event, ...result } });
});

/** GET /internal/connections - who is connected, and what screen they are on. */
internalRouter.get('/connections', (req, res) => {
  const { user_id: userId, org_id: orgId } = req.query;
  let connections = hub.describeConnections();

  if (userId) connections = connections.filter((c) => c.userId === String(userId));
  if (orgId) connections = connections.filter((c) => c.orgId === String(orgId));

  res.json({ success: true, data: connections, meta: { total: connections.length } });
});

/** GET /internal/stats - counters for a dashboard or a smoke test. */
internalRouter.get('/stats', (_req, res) => {
  res.json({ success: true, data: hub.snapshot() });
});

/** POST /internal/disconnect - force a user's sockets to close (e.g. on ban). */
internalRouter.post('/disconnect', (req, res) => {
  const { user_id: userId, reason } = req.body ?? {};
  const connections = hub.describeConnections().filter((c) => c.userId === String(userId));
  connections.forEach((c) => hub.close(c.connectionId, 4001, reason ?? 'Session ended'));
  res.json({ success: true, data: { closed: connections.length } });
});

export default internalRouter;
