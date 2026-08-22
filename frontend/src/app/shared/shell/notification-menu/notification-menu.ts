import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { Router } from '@angular/router';

import { DomainEventName, ServerMessage } from '../../../core/models/realtime.model';
import { Realtime } from '../../../core/services/realtime';
import { Icon } from '../../icon/icon';
import type { IconName } from '../../icon/icons';

interface Notification {
  id: string;
  icon: IconName;
  tone: 'success' | 'warning' | 'danger' | 'info' | 'primary';
  title: string;
  detail: string;
  at: string | null;
  /** Where clicking the row takes you, or null when there is nowhere useful. */
  link: string | null;
}

/**
 * How each domain event is described and where it leads.
 *
 * A table rather than a chain of conditionals: every event the hub can emit is
 * listed exactly once, so adding one to `DomainEventName` and forgetting it
 * here shows up as a missing key rather than as a silently generic row.
 */
const EVENTS: Record<
  DomainEventName,
  { icon: IconName; tone: Notification['tone']; verb: string; link: string | null }
> = {
  'attendance.checked_in': { icon: 'login', tone: 'success', verb: 'checked in', link: '/attendance/team' },
  'attendance.checked_out': { icon: 'logout', tone: 'info', verb: 'checked out', link: '/attendance/team' },
  'attendance.updated': { icon: 'clock', tone: 'info', verb: 'attendance updated', link: '/attendance/team' },
  'user.created': { icon: 'people', tone: 'success', verb: 'joined the organization', link: '/settings/people' },
  'user.updated': { icon: 'profile', tone: 'info', verb: 'profile updated', link: '/settings/people' },
  'user.status_changed': { icon: 'profile', tone: 'warning', verb: 'account status changed', link: '/settings/people' },
  'organization.updated': { icon: 'building', tone: 'info', verb: 'organization settings changed', link: '/settings/organization' },
  notification: { icon: 'bell', tone: 'primary', verb: 'sent you a notification', link: null },
  'system.announcement': { icon: 'bell', tone: 'primary', verb: 'posted an announcement', link: null },
  'leave.request_created': { icon: 'calendar', tone: 'warning', verb: 'requested leave', link: '/time-off/requests' },
  'leave.request_updated': { icon: 'check', tone: 'success', verb: 'leave request updated', link: '/time-off/requests' },
  'leave.type_updated': { icon: 'settings', tone: 'info', verb: 'leave types changed', link: '/settings/leave-policy' },
  'leave.allocation_updated': { icon: 'settings', tone: 'info', verb: 'leave allocation changed', link: '/settings/leave-policy' },
  'leave.balance_updated': { icon: 'plane', tone: 'info', verb: 'leave balance changed', link: '/time-off' },
  'holiday.updated': { icon: 'calendar', tone: 'info', verb: 'holidays changed', link: '/settings/holidays' },
};

/**
 * The notification bell and its panel.
 *
 * Same hand-built manners as the account menu next to it — aria-haspopup and
 * aria-expanded, Escape, outside click, focus returned to the trigger — for
 * the same reason: the app carries no CDK, and a menu is less code than the
 * dependency would be.
 *
 * The list is whatever the websocket has delivered this session. There is no
 * notifications endpoint, so nothing survives a reload; the panel says so
 * rather than pretending an empty list means nothing happened.
 */
@Component({
  selector: 'app-notification-menu',
  imports: [DatePipe, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '(document:click)': 'onDocumentClick($event)',
    '(keydown.escape)': 'close(true)',
  },
  templateUrl: './notification-menu.html',
  styleUrl: './notification-menu.scss',
})
export class NotificationMenu {
  private readonly realtime = inject(Realtime);
  private readonly router = inject(Router);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected readonly open = signal(false);
  protected readonly unread = this.realtime.unread;

  protected readonly items = computed<Notification[]>(() =>
    this.realtime.recentEvents().map((message) => this.describe(message)),
  );

  protected toggle(event: MouseEvent): void {
    event.stopPropagation();
    const next = !this.open();
    this.open.set(next);
    // Opening is the read receipt: the badge clears, the list stays.
    if (next) this.realtime.markAllRead();
  }

  protected close(restoreFocus = false): void {
    if (!this.open()) return;
    this.open.set(false);
    if (restoreFocus) {
      this.host.nativeElement.querySelector<HTMLButtonElement>('.tool')?.focus();
    }
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (!this.open()) return;
    if (!this.host.nativeElement.contains(event.target as Node)) this.close();
  }

  protected go(item: Notification): void {
    if (!item.link) return;
    this.close();
    this.router.navigateByUrl(item.link);
  }

  protected clear(): void {
    this.realtime.clearRecentEvents();
    this.close();
  }

  private describe(message: ServerMessage): Notification {
    const spec = message.event ? EVENTS[message.event] : undefined;
    const payload = message.payload as {
      user?: { name?: string; full_name?: string };
      employee?: { name?: string };
      attendance?: { status?: string; total_hours?: number };
      organization?: { name?: string };
      leave_request?: { start_date?: string; end_date?: string; status?: string };
    } | null;

    const who =
      payload?.user?.name ??
      payload?.user?.full_name ??
      payload?.employee?.name ??
      payload?.organization?.name ??
      'Someone';

    return {
      id: message.id,
      icon: spec?.icon ?? 'bell',
      tone: spec?.tone ?? 'info',
      title: `${who} ${spec?.verb ?? 'sent an update'}`,
      detail: this.detailFor(message, payload),
      at: message.emittedAt ?? message.serverTime ?? null,
      link: spec?.link ?? null,
    };
  }

  private detailFor(
    message: ServerMessage,
    payload: { attendance?: { total_hours?: number }; leave_request?: { start_date?: string; end_date?: string } } | null,
  ): string {
    if (message.event?.startsWith('attendance.') && payload?.attendance?.total_hours) {
      return `${payload.attendance.total_hours}h logged today`;
    }
    const leave = payload?.leave_request;
    if (leave?.start_date) {
      return leave.end_date && leave.end_date !== leave.start_date
        ? `${leave.start_date} → ${leave.end_date}`
        : leave.start_date;
    }
    return message.channel ?? '';
  }
}
