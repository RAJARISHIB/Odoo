/**
 * The wire protocol.
 *
 * Client -> server
 *   { type: 'auth',        token }                     authenticate after connect
 *   { type: 'subscribe',   channels: [] }              join extra channels
 *   { type: 'unsubscribe', channels: [] }              leave channels
 *   { type: 'ui.context',  payload: { panel, route, view, params } }
 *                                                      what the UI is showing now
 *   { type: 'ping' }                                   liveness
 *
 * Server -> client
 *   { type: 'connected',    payload: { connectionId, identity, channels } }
 *   { type: 'event',        event, channel, payload, emittedAt, id }
 *   { type: 'subscribed'   | 'unsubscribed', payload: { channels, rejected } }
 *   { type: 'ui.context.ack', payload: { context } }
 *   { type: 'pong',         payload: { serverTime } }
 *   { type: 'error',        payload: { code, message } }
 *
 * Kept in sync with `backend/core/constants.py::RealtimeEvent` and the Angular
 * `RealtimeService`.
 */
import { randomUUID } from 'node:crypto';

export const ClientMessage = {
  AUTH: 'auth',
  SUBSCRIBE: 'subscribe',
  UNSUBSCRIBE: 'unsubscribe',
  UI_CONTEXT: 'ui.context',
  PING: 'ping',
};

export const ServerMessage = {
  CONNECTED: 'connected',
  EVENT: 'event',
  SUBSCRIBED: 'subscribed',
  UNSUBSCRIBED: 'unsubscribed',
  UI_CONTEXT_ACK: 'ui.context.ack',
  PONG: 'pong',
  ERROR: 'error',
};

/** Domain events Django publishes - see `RealtimeEvent` on the Python side. */
export const DomainEvent = {
  ATTENDANCE_CHECKED_IN: 'attendance.checked_in',
  ATTENDANCE_CHECKED_OUT: 'attendance.checked_out',
  ATTENDANCE_UPDATED: 'attendance.updated',
  USER_CREATED: 'user.created',
  USER_UPDATED: 'user.updated',
  USER_STATUS_CHANGED: 'user.status_changed',
  ORG_UPDATED: 'organization.updated',
  NOTIFICATION: 'notification',
  SYSTEM_ANNOUNCEMENT: 'system.announcement',
};

export function envelope(type, payload = {}, extra = {}) {
  return JSON.stringify({
    id: randomUUID(),
    type,
    payload,
    serverTime: new Date().toISOString(),
    ...extra,
  });
}

export function eventEnvelope({ id, event, channel, payload, emittedAt, actorId, source }) {
  return JSON.stringify({
    id: id ?? randomUUID(),
    type: ServerMessage.EVENT,
    event,
    channel,
    payload: payload ?? {},
    actorId: actorId ?? null,
    source: source ?? 'django',
    emittedAt: emittedAt ?? new Date().toISOString(),
  });
}

export function errorEnvelope(code, message) {
  return envelope(ServerMessage.ERROR, { code, message });
}

/** Validate an inbound frame before acting on it. */
export function parseClientMessage(raw) {
  if (raw.length > 64 * 1024) {
    return { error: { code: 'message_too_large', message: 'Message exceeds 64KB.' } };
  }
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return { error: { code: 'invalid_json', message: 'Message must be valid JSON.' } };
  }
  if (!data || typeof data !== 'object' || typeof data.type !== 'string') {
    return { error: { code: 'invalid_message', message: 'Message needs a string "type".' } };
  }
  return { data };
}
