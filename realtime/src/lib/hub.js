/**
 * The connection registry.
 *
 * Holds every live socket and the channel index used to fan a message out.
 * Everything is in-process: fine for a single node, and the seam to swap in
 * Redis pub/sub later is `publish()` alone.
 */
import { randomUUID } from 'node:crypto';

import { config } from '../config.js';
import { eventEnvelope, envelope, ServerMessage } from './events.js';
import { logger } from './logger.js';

class Hub {
  constructor() {
    /** @type {Map<string, object>} connectionId -> connection record */
    this.connections = new Map();
    /** @type {Map<string, Set<string>>} channel -> connectionIds */
    this.channelIndex = new Map();
    /** @type {Map<string, Set<string>>} userId -> connectionIds */
    this.userIndex = new Map();
    this.stats = { totalConnections: 0, messagesPublished: 0, messagesDelivered: 0 };
  }

  // -- lifecycle ---------------------------------------------------------
  register(socket, identity, meta = {}) {
    const existing = this.userIndex.get(identity.userId);
    if (existing && existing.size >= config.maxConnectionsPerUser) {
      // Drop the oldest so a leaking tab cannot exhaust a user's slots.
      const oldest = [...existing][0];
      this.close(oldest, 1013, 'Too many connections for this user.');
    }

    const connection = {
      id: randomUUID(),
      socket,
      identity,
      channels: new Set(),
      // Metadata the UI sends about what it is currently showing.
      context: { panel: meta.panel ?? null, route: null, view: null, params: {} },
      connectedAt: new Date().toISOString(),
      lastSeenAt: Date.now(),
      isAlive: true,
      userAgent: meta.userAgent ?? null,
      ip: meta.ip ?? null,
    };

    this.connections.set(connection.id, connection);
    this._indexUser(identity.userId, connection.id);
    this.stats.totalConnections += 1;

    logger.info('Client connected', {
      connectionId: connection.id,
      user: identity.email,
      role: identity.role,
      total: this.connections.size,
    });
    return connection;
  }

  unregister(connectionId) {
    const connection = this.connections.get(connectionId);
    if (!connection) return null;

    for (const channel of connection.channels) {
      this._removeFromChannel(channel, connectionId);
    }
    const userConnections = this.userIndex.get(connection.identity.userId);
    if (userConnections) {
      userConnections.delete(connectionId);
      if (!userConnections.size) this.userIndex.delete(connection.identity.userId);
    }
    this.connections.delete(connectionId);

    logger.info('Client disconnected', {
      connectionId,
      user: connection.identity.email,
      total: this.connections.size,
    });
    return connection;
  }

  close(connectionId, code = 1000, reason = 'Closed by server') {
    const connection = this.connections.get(connectionId);
    if (!connection) return;
    try {
      connection.socket.close(code, reason);
    } catch (error) {
      logger.warn('Failed to close socket', { connectionId, error: error.message });
    }
  }

  // -- subscriptions -----------------------------------------------------
  subscribe(connectionId, channels) {
    const connection = this.connections.get(connectionId);
    if (!connection) return [];
    const added = [];
    for (const channel of channels) {
      if (connection.channels.has(channel)) continue;
      connection.channels.add(channel);
      if (!this.channelIndex.has(channel)) this.channelIndex.set(channel, new Set());
      this.channelIndex.get(channel).add(connectionId);
      added.push(channel);
    }
    return added;
  }

  unsubscribe(connectionId, channels) {
    const connection = this.connections.get(connectionId);
    if (!connection) return [];
    const removed = [];
    for (const channel of channels) {
      if (!connection.channels.delete(channel)) continue;
      this._removeFromChannel(channel, connectionId);
      removed.push(channel);
    }
    return removed;
  }

  setContext(connectionId, context) {
    const connection = this.connections.get(connectionId);
    if (!connection) return null;
    connection.context = {
      panel: context.panel ?? connection.context.panel,
      route: context.route ?? null,
      view: context.view ?? null,
      params: context.params ?? {},
      updatedAt: new Date().toISOString(),
    };
    return connection.context;
  }

  // -- delivery ----------------------------------------------------------
  /**
   * Fan one message out to every socket subscribed to any of `channels`.
   * A socket subscribed to two of the listed channels still receives it once.
   */
  publish(message) {
    const { channels = [], event, payload, id, emittedAt, actorId, source } = message;
    const seen = new Set();
    let delivered = 0;

    for (const channel of channels) {
      const subscribers = this.channelIndex.get(channel);
      if (!subscribers?.size) continue;

      const frame = eventEnvelope({ id, event, channel, payload, emittedAt, actorId, source });
      for (const connectionId of subscribers) {
        if (seen.has(connectionId)) continue;
        seen.add(connectionId);
        if (this.send(connectionId, frame)) delivered += 1;
      }
    }

    this.stats.messagesPublished += 1;
    this.stats.messagesDelivered += delivered;
    logger.debug('Published event', { event, channels, delivered });
    return { delivered, recipients: seen.size };
  }

  send(connectionId, frame) {
    const connection = this.connections.get(connectionId);
    if (!connection || connection.socket.readyState !== connection.socket.OPEN) return false;
    try {
      connection.socket.send(frame);
      return true;
    } catch (error) {
      logger.warn('Send failed', { connectionId, error: error.message });
      return false;
    }
  }

  sendType(connectionId, type, payload, extra) {
    return this.send(connectionId, envelope(type, payload, extra));
  }

  // -- introspection -----------------------------------------------------
  connectionCountForUser(userId) {
    return this.userIndex.get(String(userId))?.size ?? 0;
  }

  snapshot() {
    return {
      connections: this.connections.size,
      users: this.userIndex.size,
      channels: this.channelIndex.size,
      stats: this.stats,
    };
  }

  describeConnections() {
    return [...this.connections.values()].map((connection) => ({
      connectionId: connection.id,
      userId: connection.identity.userId,
      email: connection.identity.email,
      role: connection.identity.role,
      orgId: connection.identity.orgId,
      channels: [...connection.channels],
      context: connection.context,
      connectedAt: connection.connectedAt,
    }));
  }

  // -- heartbeat ---------------------------------------------------------
  /** Ping every socket; drop the ones that missed the previous round. */
  startHeartbeat() {
    if (this.heartbeatTimer) return;
    this.heartbeatTimer = setInterval(() => {
      for (const connection of this.connections.values()) {
        if (!connection.isAlive) {
          logger.warn('Dropping unresponsive client', { connectionId: connection.id });
          connection.socket.terminate();
          this.unregister(connection.id);
          continue;
        }
        connection.isAlive = false;
        try {
          connection.socket.ping();
        } catch {
          this.unregister(connection.id);
        }
      }
    }, config.heartbeatIntervalMs);
    this.heartbeatTimer.unref?.();
  }

  stopHeartbeat() {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }

  shutdown() {
    this.stopHeartbeat();
    for (const connection of this.connections.values()) {
      this.sendType(connection.id, ServerMessage.ERROR, {
        code: 'server_shutdown',
        message: 'Server is shutting down.',
      });
      connection.socket.close(1001, 'Server shutting down');
    }
    this.connections.clear();
    this.channelIndex.clear();
    this.userIndex.clear();
  }

  // -- internals ---------------------------------------------------------
  _indexUser(userId, connectionId) {
    if (!this.userIndex.has(userId)) this.userIndex.set(userId, new Set());
    this.userIndex.get(userId).add(connectionId);
  }

  _removeFromChannel(channel, connectionId) {
    const subscribers = this.channelIndex.get(channel);
    if (!subscribers) return;
    subscribers.delete(connectionId);
    if (!subscribers.size) this.channelIndex.delete(channel);
  }
}

export const hub = new Hub();
export default hub;
