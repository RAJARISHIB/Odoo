import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs';

import { Auth } from '../../core/services/auth';
import { Realtime } from '../../core/services/realtime';
import { RealtimeIndicator } from '../../shared/realtime-indicator/realtime-indicator';

interface NavItem {
  label: string;
  path: string;
  icon: string;
}

/**
 * Admin panel frame: sidebar, header, routed content.
 *
 * Reached only through `adminGuard`, so every child route can assume an
 * admin-panel role.
 */
@Component({
  selector: 'app-admin-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, RealtimeIndicator],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './admin-shell.html',
  styleUrl: '../../shared/panel-shell.scss',
})
export class AdminShell {
  private readonly router = inject(Router);
  protected readonly auth = inject(Auth);
  protected readonly realtime = inject(Realtime);

  protected readonly navItems: NavItem[] = [
    { label: 'Dashboard', path: '/admin/dashboard', icon: '▦' },
    { label: 'Employees', path: '/admin/employees', icon: '☺' },
    { label: 'Attendance', path: '/admin/attendance', icon: '⏱' },
    { label: 'Organization', path: '/admin/organization', icon: '⚙' },
  ];

  /** Admin leave module - kept as a separate group so the existing `navItems`
   * section above is untouched. */
  protected readonly leaveNavItems: NavItem[] = [
    { label: 'Leave requests', path: '/admin/leave/requests', icon: '✓' },
    { label: 'Leave configuration', path: '/admin/leave/configuration', icon: '☰' },
    { label: 'Holiday calendar', path: '/admin/leave/holidays', icon: '☼' },
    { label: 'Leave dashboard', path: '/admin/leave/dashboard', icon: '◔' },
  ];

  protected readonly title = signal(this.titleForUrl(this.router.url));

  /** Unread realtime events, shown as a count next to the connection badge. */
  protected readonly eventCount = computed(() => this.realtime.recentEvents().length);

  protected readonly initials = computed(() => {
    const user = this.auth.user();
    if (!user) return '?';
    return `${user.first_name?.[0] ?? ''}${user.last_name?.[0] ?? ''}`.toUpperCase() || 'U';
  });

  constructor() {
    this.router.events
      .pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe((event) => this.title.set(this.titleForUrl(event.urlAfterRedirects)));
  }

  protected signOut(): void {
    this.auth.logout();
  }

  private titleForUrl(url: string): string {
    const item = [...this.navItems, ...this.leaveNavItems].find((entry) => url.startsWith(entry.path));
    return item?.label ?? 'Admin';
  }
}
