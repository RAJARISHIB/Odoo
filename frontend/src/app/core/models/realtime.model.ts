/** Websocket wire protocol - mirrors `realtime/src/lib/events.js`. */

export type ServerMessageType =
  | 'connected'
  | 'event'
  | 'subscribed'
  | 'unsubscribed'
  | 'ui.context.ack'
  | 'pong'
  | 'error';

export type DomainEventName =
  | 'attendance.checked_in'
  | 'attendance.checked_out'
  | 'attendance.updated'
  | 'user.created'
  | 'user.updated'
  | 'user.status_changed'
  | 'organization.updated'
  | 'notification'
  | 'system.announcement'
  | 'leave.request_created'
  | 'leave.request_updated'
  | 'leave.type_updated'
  | 'leave.allocation_updated'
  | 'leave.balance_updated'
  | 'holiday.updated';

export interface ServerMessage<T = unknown> {
  id: string;
  type: ServerMessageType;
  /** Present when `type` is `'event'`. */
  event?: DomainEventName;
  channel?: string;
  payload: T;
  actorId?: string | null;
  source?: string;
  emittedAt?: string;
  serverTime?: string;
}

export interface ConnectedPayload {
  connectionId: string;
  identity: {
    userId: string;
    email: string;
    name: string;
    role: string;
    orgId: string | null;
    panel: 'admin' | 'user';
  };
  channels: string[];
  heartbeatIntervalMs: number;
}

/** What the UI reports about the screen it is currently showing. */
export interface UiContext {
  panel: 'admin' | 'user';
  route: string;
  view?: string;
  params?: Record<string, unknown>;
}

export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'closed';
