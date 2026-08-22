import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';

import { Attendance } from '../../../core/services/attendance';
import { Realtime } from '../../../core/services/realtime';
import { Toast } from '../../../core/services/toast';
import { Icon } from '../../icon/icon';

/**
 * Check in / check out, in the topbar systray.
 *
 * The status dot is the wireframe's red-to-green marker: red while the day has
 * no open session, green and pulsing once checked in.
 */
@Component({
  selector: 'app-punch-widget',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './punch-widget.html',
  styleUrl: './punch-widget.scss',
})
export class PunchWidget {
  private readonly attendance = inject(Attendance);
  private readonly toast = inject(Toast);
  private readonly realtime = inject(Realtime);

  protected readonly checkedIn = signal(false);
  protected readonly since = signal<string | null>(null);
  protected readonly busy = signal(false);
  protected readonly loaded = signal(false);
  /** Ticks every second so the elapsed readout stays live. */
  private readonly now = signal(Date.now());

  protected readonly sinceLabel = computed(() => {
    const iso = this.since();
    return iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : null;
  });

  protected readonly elapsed = computed(() => {
    const iso = this.since();
    if (!iso) return null;
    const seconds = Math.max(0, Math.floor((this.now() - new Date(iso).getTime()) / 1000));
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':');
  });

  constructor() {
    this.refresh();

    const timer = setInterval(() => this.now.set(Date.now()), 1000);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  protected punch(): void {
    if (this.busy()) return;
    this.busy.set(true);

    const wasIn = this.checkedIn();
    const request = wasIn ? this.attendance.checkOut() : this.attendance.checkIn();

    request.subscribe({
      next: () => {
        this.busy.set(false);
        this.toast.success(wasIn ? 'Checked out. Have a good evening.' : 'Checked in. Have a good day.');
        this.refresh();
      },
      error: () => this.busy.set(false),
    });
  }

  private refresh(): void {
    this.attendance.status().subscribe({
      next: (state) => {
        const open = state.sessions?.find((session) => session.is_open) ?? null;
        this.checkedIn.set(state.is_checked_in);
        this.since.set(open?.check_in ?? null);
        this.now.set(Date.now());
        this.loaded.set(true);
      },
      error: () => this.loaded.set(true),
    });
  }
}
