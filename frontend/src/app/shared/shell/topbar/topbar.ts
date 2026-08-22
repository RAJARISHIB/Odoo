import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Layout } from '../../../core/services/layout';
import { GlobalSearch } from '../global-search/global-search';
import { Icon } from '../../icon/icon';
import { NotificationMenu } from '../notification-menu/notification-menu';
import { ThemeToggle } from '../theme-toggle/theme-toggle';
import { UserMenu } from '../user-menu/user-menu';
import { PunchWidget } from '../punch-widget/punch-widget';

export interface Crumb {
  label: string;
  path: string;
}

/** Topbar: nav toggle, breadcrumbs, global search, notifications, theme, account. */
@Component({
  selector: 'app-topbar',
  imports: [RouterLink, Icon, GlobalSearch, NotificationMenu, ThemeToggle, UserMenu, PunchWidget],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './topbar.html',
  styleUrl: './topbar.scss',
})
export class Topbar {
  readonly crumbs = input<Crumb[]>([]);

  protected readonly layout = inject(Layout);

  protected readonly last = computed(() => this.crumbs().at(-1) ?? null);
  protected readonly trail = computed(() => this.crumbs().slice(0, -1));
}
