import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Auth } from '../../../core/services/auth';
import { Layout } from '../../../core/services/layout';
import { Icon } from '../../icon/icon';
import { visibleNav } from '../nav-config';

/** Sidebar: brand, capability-filtered nav, user chip. Collapses to a rail. */
@Component({
  selector: 'app-sidebar',
  imports: [RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
})
export class Sidebar {
  /** Longest matching nav path, resolved once by the shell. */
  readonly activePath = input<string | null>(null);

  protected readonly auth = inject(Auth);
  protected readonly layout = inject(Layout);

  protected readonly sections = computed(() => visibleNav(this.auth.permissions()));

  /** Flags have not arrived yet - render skeleton rows, do not guess. */
  protected readonly loading = computed(() => this.auth.permissions() === null);

  protected readonly initials = computed(() => {
    const user = this.auth.user();
    if (!user) return '?';
    return `${user.first_name?.[0] ?? ''}${user.last_name?.[0] ?? ''}`.toUpperCase() || 'U';
  });

  protected readonly roleLabel = computed(() => {
    const user = this.auth.user();
    return user?.designation || user?.role?.replace('_', ' ') || '';
  });

  protected readonly skeletonRows = [1, 2, 3, 4];
}
