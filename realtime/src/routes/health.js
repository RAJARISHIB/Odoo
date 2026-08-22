/** Public health + protocol description. No auth: no data is exposed. */
import { Router } from 'express';

import { config } from '../config.js';
import { ClientMessage, DomainEvent, ServerMessage } from '../lib/events.js';
import { hub } from '../lib/hub.js';

export const healthRouter = Router();

const startedAt = Date.now();

healthRouter.get('/health', (_req, res) => {
  res.json({
    service: 'hrms-realtime',
    status: 'ok',
    env: config.env,
    uptimeSeconds: Math.round((Date.now() - startedAt) / 1000),
    ...hub.snapshot(),
  });
});

/** GET / - the wire protocol, handy while wiring the Angular client. */
healthRouter.get('/', (_req, res) => {
  res.json({
    service: 'hrms-realtime',
    websocket: `ws://localhost:${config.port}${config.wsPath}?token=<accessToken>&panel=<admin|user>`,
    clientMessages: Object.values(ClientMessage),
    serverMessages: Object.values(ServerMessage),
    domainEvents: Object.values(DomainEvent),
    channels: {
      'user:<userId>': 'One person, every tab they have open.',
      'org:<orgId>': 'Everyone in the organization.',
      'org:<orgId>:panel:<admin|user>': 'One panel of one organization.',
      'org:<orgId>:role:<role>': 'One role within an organization.',
      broadcast: 'Every connected client.',
    },
    internal: {
      'POST /internal/publish': 'Django -> hub fan-out (requires x-internal-key).',
      'POST /internal/broadcast': 'Shorthand for the broadcast channel.',
      'GET  /internal/connections': 'Connected clients and their UI context.',
      'GET  /internal/stats': 'Hub counters.',
      'POST /internal/disconnect': "Close a user's sockets.",
    },
  });
});

export default healthRouter;
