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
  /**
   * How many of those have arrived since the user last opened the panel.
   *
   * A counter rather than a set of seen ids: the list is capped at 25 and the
   * only question the badge answers is "is there anything new", so tracking
   * identity would buy nothing and would have to be pruned alongside the list.
   */
  readonly unread = signal(0);

  constructor() {
    // Two things mean "the remaining backoff is now pointless": the OS saying
    // the network is back, and the tab being brought forward after the browser
    // froze its background timers. Neither listener is ever removed — this
    // service is `providedIn: 'root'` and lives as long as the document.
    window.addEventListener('online', () => this.retryNow());
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') this.retryNow();
    });
  }

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

  /**
   * Retry now instead of waiting out the current rung of the ladder.
   *
   * The backoff exists to stop a dead network being hammered, but once the
   * machine tells us the network is back, the remaining wait is pure dead time
   * — and at the 30s ceiling that is up to half a minute of a stale board.
   * Reconnecting on a real signal also resets the ladder, so the next genuine
   * drop starts from 5s again rather than inheriting a long delay.
   */
  private retryNow(): void {
    if (!this.token || this.manualClose) return;
    if (this.status() === 'connected' || this.status() === 'connecting') return;
    this.reconnectDelay = environment.wsReconnectDelay;
    this.open();
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
        this.remember(message);
        break;
      default:
        break;
    }

    this.messages$.next(message);
  }

  /** Identity keys for what is in `recentEvents`, newest first, same length. */
  private recentKeys: string[] = [];

  /**
   * Add one event to the recent list, unless it is a re-delivery.
   *
   * `stream$` is deliberately left alone: a subscriber that filters by channel
   * still needs to see every delivery. Only the stored list dedupes.
   */
  private remember(message: ServerMessage): void {
    const key = this.identityOf(message);

    // Decided before either write: updating one signal from inside another
    // signal's update callback is a nested write, and the unread counter must
    // not advance when the list rejects the message as a duplicate.
    if (this.recentKeys.includes(key)) return;

    this.recentKeys = [key, ...this.recentKeys].slice(0, 25);
    this.recentEvents.update((events) => [message, ...events].slice(0, 25));
    this.unread.update((n) => n + 1);
  }

  /**
   * What makes two frames the same notification.
   *
   * The hub delivers one domain event once per channel the recipient is
   * subscribed to, so an admin checking themselves in receives it on both
   * `user:<their id>` and `org:<org>:panel:admin` and would see it twice.
   *
   * Nothing in the envelope identifies the event: the hub mints a fresh `id`
   * per channel, `serverTime` is per-delivery, and Django publishes each
   * channel separately so even `emittedAt` differs by tens of milliseconds.
   * The payload does not — both copies are serialised from the same record and
   * carry its database-written `updated_at` — so the payload itself is the
   * identity. Hashing it rather than naming a field per event type keeps this
   * correct for events that do not exist yet.
   */
  private identityOf(message: ServerMessage): string {
    return [message.event, message.actorId ?? '', JSON.stringify(message.payload ?? null)].join('|');
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
    this.recentKeys = [];
    this.unread.set(0);
  }

  /** Called when the notification panel opens - the badge, not the list. */
  markAllRead(): void {
    this.unread.set(0);
  }
}
