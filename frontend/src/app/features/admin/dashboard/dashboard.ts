import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe, KeyValuePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { Attendance } from '../../../core/services/attendance';
import { DailyOverview } from '../../../core/models/attendance.model';
import { DepartmentHeadcount, Organizations, Users } from '../../../core/services/users';
import { Realtime } from '../../../core/services/realtime';
import { ServerMessage } from '../../../core/models/realtime.model';
import { UserStats } from '../../../core/models/user.model';

interface FeedEntry {
  id: string;
  text: string;
  detail: string;
  at: string;
  tone: string;
}

/**
 * Admin landing screen: today's attendance snapshot, headcount and a live feed
 * fed by the websocket hub - no polling.
 */
@Component({
  selector: 'app-admin-dashboard',
  imports: [DatePipe, KeyValuePipe, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard.html',
  styles: [
    `
      .feed {
        list-style: none;
        margin: 0;
        padding: 0;
      }
      .feed li {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 11px 18px;
        border-bottom: 1px solid var(--border);
      }
      .feed li:last-child {
        border-bottom: none;
      }
      .breakdown {
        display: grid;
        gap: 8px;
      }
    `,
  ],
})
export class AdminDashboard {
  private readonly attendance = inject(Attendance);
  private readonly users = inject(Users);
  private readonly organizations = inject(Organizations);
  private readonly realtime = inject(Realtime);

  protected readonly overview = signal<DailyOverview | null>(null);
  protected readonly stats = signal<UserStats | null>(null);
  protected readonly departments = signal<DepartmentHeadcount[]>([]);
  protected readonly feed = signal<FeedEntry[]>([]);
  protected readonly loading = signal(true);

  constructor() {
    this.load();

    // Any attendance movement refreshes the counters and prepends to the feed.
    this.realtime
      .onAny(['attendance.checked_in', 'attendance.checked_out', 'attendance.updated'])
      .pipe(takeUntilDestroyed())
      .subscribe((message) => {
        this.pushToFeed(message);
        this.refreshOverview();
      });

    this.realtime
      .onAny(['user.created', 'user.status_changed'])
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.users.stats().subscribe((stats) => this.stats.set(stats)));
  }

  protected reload(): void {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.attendance.adminOverview().subscribe({
      next: (overview) => {
        this.overview.set(overview);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
    this.users.stats().subscribe((stats) => this.stats.set(stats));
    this.organizations
      .overview()
      .subscribe((result) => this.departments.set(result.departments ?? []));
  }

  private refreshOverview(): void {
    this.attendance.adminOverview().subscribe((overview) => this.overview.set(overview));
  }

  private pushToFeed(message: ServerMessage): void {
    const payload = message.payload as {
      user?: { name?: string };
      attendance?: { status?: string; total_hours?: number };
    };

    const verb =
      message.event === 'attendance.checked_in'
        ? 'checked in'
        : message.event === 'attendance.checked_out'
          ? 'checked out'
          : 'attendance updated';

    const entry: FeedEntry = {
      id: message.id,
      text: `${payload.user?.name ?? 'Someone'} ${verb}`,
      detail: payload.attendance?.total_hours ? `${payload.attendance.total_hours} h today` : '',
      at: message.emittedAt ?? new Date().toISOString(),
      tone: message.event === 'attendance.checked_in' ? 'success' : 'info',
    };

    this.feed.update((entries) => [entry, ...entries].slice(0, 12));
  }
}
