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

  /** Hours banked today across every closed session. */
  protected readonly todayHours = signal(0);
  /** When the last completed session ended, for the "since" line. */
  protected readonly lastOut = signal<string | null>(null);

  /**
   * The day has a finished session but none open — the user checked in earlier
   * and has checked out again.
   *
   * Worth its own state because "Not checked in / Start your day" is actively
   * wrong here: it reads as though the day has not begun, when in fact it is
   * done, and it invites a second check-in the user did not mean to make.
   */
  protected readonly doneForNow = computed(() => !this.checkedIn() && this.lastOut() !== null);

  /** "Check in" once a day is already banked would misdescribe the action. */
  protected readonly buttonLabel = computed(() => {
    if (this.checkedIn()) return 'Check out';
    return this.doneForNow() ? 'Check in again' : 'Check in';
  });

  protected readonly sinceLabel = computed(() => this.clock(this.since()));
  protected readonly lastOutLabel = computed(() => this.clock(this.lastOut()));

  /** Banked time as `7h 45m`, which reads better than a decimal at a glance. */
  protected readonly todayLabel = computed(() => {
    const hours = this.todayHours();
    const whole = Math.floor(hours);
    const minutes = Math.round((hours - whole) * 60);
    return whole ? `${whole}h ${String(minutes).padStart(2, '0')}m` : `${minutes}m`;
  });

  private clock(iso: string | null): string | null {
    return iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : null;
  }

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
        const sessions = state.sessions ?? [];
        const open = sessions.find((session) => session.is_open) ?? null;
        // Last *completed* session, so a reopened day still reports the right
        // finish time rather than the first check-out of the morning.
        const closed = sessions.filter((session) => !session.is_open && session.check_out);

        this.checkedIn.set(state.is_checked_in);
        this.since.set(open?.check_in ?? null);
        this.lastOut.set(closed.at(-1)?.check_out ?? null);
        this.todayHours.set(state.total_hours ?? 0);
        this.now.set(Date.now());
        this.loaded.set(true);
      },
      error: () => this.loaded.set(true),
    });
  }
}
