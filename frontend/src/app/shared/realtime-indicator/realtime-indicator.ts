import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { Realtime } from '../../core/services/realtime';

/** Live websocket state - the header dot that shows the hub is connected. */
@Component({
  selector: 'app-realtime-indicator',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="badge" [class]="tone()" [title]="'Websocket: ' + status()">
      <span class="dot"></span>{{ label() }}
    </span>
  `,
  styles: [
    `
      .dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: currentColor;
        display: inline-block;
      }
      .badge.success .dot {
        animation: pulse 2s infinite;
      }
      @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.35; }
      }
    `,
  ],
})
export class RealtimeIndicator {
  private readonly realtime = inject(Realtime);

  protected readonly status = this.realtime.status;

  protected readonly label = computed(
    () =>
      ({
        idle: 'Offline',
        connecting: 'Connecting',
        connected: 'Live',
        reconnecting: 'Reconnecting',
        closed: 'Offline',
      })[this.status()],
  );

  protected readonly tone = computed(
    () =>
      ({
        idle: '',
        connecting: 'warning',
        connected: 'success',
        reconnecting: 'warning',
        closed: 'danger',
      })[this.status()],
  );
}
