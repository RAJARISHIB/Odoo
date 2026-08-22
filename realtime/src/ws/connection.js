/**
 * Per-socket protocol handling.
 *
 * A connection is authenticated either at handshake (`?token=`) or by the first
 * `auth` frame within the grace window. Once authenticated it is registered on
 * the hub, auto-subscribed to its default channels, and then only speaks the
 * small message set in `lib/events.js`.
 */
import { AuthError, verifyAccessToken } from '../lib/auth.js';
import { config } from '../config.js';
import { defaultChannelsFor, filterAllowed, panelForRole } from '../lib/channels.js';
import {
  ClientMessage,
  ServerMessage,
  envelope,
  errorEnvelope,
  parseClientMessage,
} from '../lib/events.js';
import { hub } from '../lib/hub.js';
import { logger } from '../lib/logger.js';
import { reportPresence } from '../lib/presence.js';

export function handleConnection(socket, request, preAuthIdentity = null) {
  const meta = {
    ip: request.socket.remoteAddress,
    userAgent: request.headers['user-agent'] ?? null,
    panel: new URL(request.url, 'http://localhost').searchParams.get('panel'),
  };

  let connectionId = null;

  // Sockets that never authenticate are dropped when the grace window closes.
  const authTimer = setTimeout(() => {
    if (!connectionId) {
      socket.send(errorEnvelope('auth_timeout', 'No credentials received.'));
      socket.close(4401, 'Authentication timeout');
    }
  }, config.authGraceMs);

  /** Shared tail of both auth paths: register, subscribe, greet, report. */
  function completeAuth(identity) {
    const connection = hub.register(socket, identity, meta);
    connectionId = connection.id;
    clearTimeout(authTimer);

    const channels = defaultChannelsFor(identity);
    hub.subscribe(connectionId, channels);
    if (meta.panel) hub.setContext(connectionId, { panel: meta.panel });

    hub.send(
      connectionId,
      envelope(ServerMessage.CONNECTED, {
        connectionId,
        identity: {
          userId: identity.userId,
          email: identity.email,
          name: identity.name,
          role: identity.role,
          orgId: identity.orgId,
          panel: panelForRole(identity.role),
        },
        channels,
        heartbeatIntervalMs: config.heartbeatIntervalMs,
      }),
    );

    reportPresence({
      event: 'connected',
      identity,
      connectionCount: hub.connectionCountForUser(identity.userId),
      panel: meta.panel ?? panelForRole(identity.role),
      connectionId,
    });

    return connection;
  }

  // Handshake-authenticated sockets (`?token=`) are registered straight away.
  if (preAuthIdentity) {
    completeAuth(preAuthIdentity);
  }

  socket.on('pong', () => {
    const connection = hub.connections.get(connectionId);
    if (connection) {
      connection.isAlive = true;
      connection.lastSeenAt = Date.now();
    }
  });

  socket.on('message', (raw) => {
    const { data, error } = parseClientMessage(raw.toString());
    if (error) {
      socket.send(errorEnvelope(error.code, error.message));
      return;
    }

    // Only `auth` is accepted before the socket has an identity.
    if (!connectionId) {
      if (data.type !== ClientMessage.AUTH) {
        socket.send(errorEnvelope('unauthenticated', 'Send an auth message first.'));
        return;
      }
      try {
        completeAuth(verifyAccessToken(data.token));
      } catch (authError) {
        const code = authError instanceof AuthError ? authError.code : 'unauthenticated';
        socket.send(errorEnvelope(code, authError.message));
        socket.close(4401, 'Authentication failed');
      }
      return;
    }

    const connection = hub.connections.get(connectionId);
    if (!connection) return;
    connection.lastSeenAt = Date.now();

    switch (data.type) {
      case ClientMessage.SUBSCRIBE: {
        const { allowed, rejected } = filterAllowed(connection.identity, data.channels);
        const added = hub.subscribe(connectionId, allowed);
        hub.sendType(connectionId, ServerMessage.SUBSCRIBED, {
          channels: added,
          active: [...connection.channels],
          rejected,
        });
        break;
      }

      case ClientMessage.UNSUBSCRIBE: {
        const removed = hub.unsubscribe(connectionId, data.channels ?? []);
        hub.sendType(connectionId, ServerMessage.UNSUBSCRIBED, {
          channels: removed,
          active: [...connection.channels],
        });
        break;
      }

      case ClientMessage.UI_CONTEXT: {
        // The UI reports which panel/route/view it is on. Useful for targeting
        // messages at the screens that actually care about them.
        const context = hub.setContext(connectionId, data.payload ?? {});
        hub.sendType(connectionId, ServerMessage.UI_CONTEXT_ACK, { context });
        logger.debug('UI context', { connectionId, context });
        break;
      }

      case ClientMessage.PING:
        hub.sendType(connectionId, ServerMessage.PONG, { serverTime: new Date().toISOString() });
        break;

      case ClientMessage.AUTH:
        hub.sendType(connectionId, ServerMessage.ERROR, {
          code: 'already_authenticated',
          message: 'This connection is already authenticated.',
        });
        break;

      default:
        hub.sendType(connectionId, ServerMessage.ERROR, {
          code: 'unknown_message_type',
          message: `Unsupported message type: ${data.type}`,
        });
    }
  });

  socket.on('close', () => {
    clearTimeout(authTimer);
    if (!connectionId) return;
    const connection = hub.unregister(connectionId);
    if (connection) {
      reportPresence({
        event: 'disconnected',
        identity: connection.identity,
        connectionCount: hub.connectionCountForUser(connection.identity.userId),
        panel: connection.context.panel,
        connectionId,
      });
    }
  });

  socket.on('error', (error) => {
    logger.warn('Socket error', { connectionId, error: error.message });
  });
}

export default handleConnection;
