import { Injectable, signal } from '@angular/core';
import { Observable, Subject, filter } from 'rxjs';

import {
  ConnectedPayload,
  ConnectionStatus,
  DomainEventName,
  ServerMessage,
  UiContext,
} from '../models/realtime.model';
import { environment } from '../../../environments/environment';

/**
 * Websocket client for the Express hub.
 *
 * Connects with the access token, auto-subscribes server-side to the channels
 * this user is allowed on, reports the UI's current screen as metadata, and
 * reconnects with backoff. Components consume `on(event)` rather than the raw
 * socket.
 */
@Injectable({ providedIn: 'root' })
export class Realtime {
  private socket: WebSocket | null = null;
  private token: string | null = null;
  private panel: 'admin' | 'user' = 'user';
  private reconnectDelay = environment.wsReconnectDelay;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  /** Sent as soon as the socket opens, so context survives a reconnect. */
  private pendingContext: UiContext | null = null;
  private manualClose = false;

  private readonly messages$ = new Subject<ServerMessage>();

  readonly status = signal<ConnectionStatus>('idle');
  readonly connectionId = signal<string | null>(null);
  readonly subscribedChannels = signal<string[]>([]);
  /** Last few events, newest first - drives the notification bell. */
  readonly recentEvents = signal<ServerMessage[]>([]);

  // -----------------------------------------------------------------
  // Connection
  // -----------------------------------------------------------------
  connect(token: string, panel: 'admin' | 'user' = 'user'): void {
    if (!token) return;
    // Same token and a live socket: nothing to do.
    if (this.socket && this.token === token && this.status() === 'connected') return;

    this.token = token;
    this.panel = panel;
    this.manualClose = false;
    this.open();
  }

  disconnect(): void {
    this.manualClose = true;
    this.clearTimers();
    this.socket?.close(1000, 'Client signed out');
    this.socket = null;
    this.token = null;
    this.status.set('closed');
    this.connectionId.set(null);
    this.subscribedChannels.set([]);
  }

  private open(): void {
    this.clearTimers();
    this.status.set(this.status() === 'closed' || this.status() === 'idle' ? 'connecting' : 'reconnecting');

    const url = `${environment.wsUrl}?token=${encodeURIComponent(this.token!)}&panel=${this.panel}`;
    const socket = new WebSocket(url);
    this.socket = socket;

    socket.onopen = () => {
      this.status.set('connected');
      this.reconnectDelay = environment.wsReconnectDelay;
      if (this.pendingContext) this.sendContext(this.pendingContext);
      this.startHeartbeat();
    };

    socket.onmessage = (event) => this.handleMessage(event.data);

    socket.onerror = () => {
      // `onclose` always follows, so reconnection is handled there.
    };

    socket.onclose = (event) => {
      this.clearTimers();
      this.connectionId.set(null);
      if (this.manualClose) {
        this.status.set('closed');
        return;
      }
      // 4401 = the hub rejected our credentials; retrying with the same token
      // would just loop, so wait for the app to hand over a fresh one.
      if (event.code === 4401) {
        this.status.set('closed');
        return;
      }
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    this.status.set('reconnecting');
    this.reconnectTimer = setTimeout(() => {
      if (this.token) this.open();
    }, this.reconnectDelay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, environment.wsMaxReconnectDelay);
  }

  private startHeartbeat(): void {
    this.heartbeatTimer = setInterval(() => this.send({ type: 'ping' }), 25000);
  }

  private clearTimers(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    this.reconnectTimer = null;
    this.heartbeatTimer = null;
  }

  // -----------------------------------------------------------------
  // Messaging
  // -----------------------------------------------------------------
  private handleMessage(raw: string): void {
    let message: ServerMessage;
    try {
      message = JSON.parse(raw) as ServerMessage;
    } catch {
      return;
    }

    switch (message.type) {
      case 'connected': {
        const payload = message.payload as ConnectedPayload;
        this.connectionId.set(payload.connectionId);
        this.subscribedChannels.set(payload.channels);
        break;
      }
      case 'subscribed':
      case 'unsubscribed': {
        const payload = message.payload as { active: string[] };
        this.subscribedChannels.set(payload.active ?? []);
        break;
      }
      case 'event':
        this.recentEvents.update((events) => [message, ...events].slice(0, 25));
        break;
      default:
        break;
    }

    this.messages$.next(message);
  }

  private send(payload: unknown): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(payload));
    return true;
  }

  /** Join extra channels. The hub rejects any the user is not entitled to. */
  subscribe(channels: string[]): void {
    this.send({ type: 'subscribe', channels });
  }

  unsubscribe(channels: string[]): void {
    this.send({ type: 'unsubscribe', channels });
  }

  /**
   * Report what the UI is showing. The hub keeps this alongside the connection
   * so the backend can see which screens are open.
   */
  setContext(context: UiContext): void {
    this.pendingContext = context;
    this.sendContext(context);
  }

  private sendContext(context: UiContext): void {
    this.send({ type: 'ui.context', payload: context });
  }

  // -----------------------------------------------------------------
  // Consumption
  // -----------------------------------------------------------------
  /** Every inbound frame. */
  get stream$(): Observable<ServerMessage> {
    return this.messages$.asObservable();
  }

  /** One domain event, e.g. `on('attendance.checked_in')`. */
  on<T = unknown>(event: DomainEventName): Observable<ServerMessage<T>> {
    return this.messages$.pipe(
      filter((message): message is ServerMessage<T> =>
        message.type === 'event' && message.event === event),
    );
  }

  /** Several domain events at once. */
  onAny<T = unknown>(events: DomainEventName[]): Observable<ServerMessage<T>> {
    return this.messages$.pipe(
      filter((message): message is ServerMessage<T> =>
        message.type === 'event' && !!message.event && events.includes(message.event)),
    );
  }

  clearRecentEvents(): void {
    this.recentEvents.set([]);
  }
}
