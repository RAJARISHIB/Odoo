import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Layout } from '../../../core/services/layout';
import { Realtime } from '../../../core/services/realtime';
import { Icon } from '../../icon/icon';
import { RealtimeIndicator } from '../../realtime-indicator/realtime-indicator';
import { ThemeToggle } from '../theme-toggle/theme-toggle';
import { UserMenu } from '../user-menu/user-menu';
import { PunchWidget } from '../punch-widget/punch-widget';

export interface Crumb {
  label: string;
  path: string;
}

/** Topbar: nav toggle, breadcrumbs, search, notifications, theme, account. */
@Component({
  selector: 'app-topbar',
  imports: [RouterLink, Icon, RealtimeIndicator, ThemeToggle, UserMenu, PunchWidget],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './topbar.html',
  styleUrl: './topbar.scss',
})
export class Topbar {
  readonly crumbs = input<Crumb[]>([]);

  protected readonly layout = inject(Layout);
  private readonly realtime = inject(Realtime);

  /** The realtime `notification` channel exists; this is its first UI surface. */
  protected readonly eventCount = computed(() => this.realtime.recentEvents().length);

  protected readonly last = computed(() => this.crumbs().at(-1) ?? null);
  protected readonly trail = computed(() => this.crumbs().slice(0, -1));
}
