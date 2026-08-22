import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs';

import { Auth } from '../../core/services/auth';
import { RealtimeIndicator } from '../../shared/realtime-indicator/realtime-indicator';

interface NavItem {
  label: string;
  path: string;
  icon: string;
}

/**
 * Employee panel frame.
 *
 * Open to every signed-in user. Admins can reach it too - the sidebar offers a
 * link back to the admin panel when the role allows it.
 */
@Component({
  selector: 'app-user-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, RealtimeIndicator],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './user-shell.html',
  styleUrl: '../../shared/panel-shell.scss',
})
export class UserShell {
  private readonly router = inject(Router);
  protected readonly auth = inject(Auth);

  protected readonly navItems: NavItem[] = [
    { label: 'Dashboard', path: '/app/dashboard', icon: '▦' },
    { label: 'My attendance', path: '/app/attendance', icon: '⏱' },
    { label: 'Calendar & Leave', path: '/app/calendar', icon: '📅' },
    { label: 'Profile', path: '/app/profile', icon: '☺' },
  ];

  protected readonly title = signal(this.titleForUrl(this.router.url));

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
    return this.navItems.find((item) => url.startsWith(item.path))?.label ?? 'Portal';
  }
}
