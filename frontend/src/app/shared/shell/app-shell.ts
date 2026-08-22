import { ChangeDetectionStrategy, Component, computed, effect, inject, untracked } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';

import { Layout } from '../../core/services/layout';
import { NAV } from './nav-config';
import { Sidebar } from './sidebar/sidebar';
import { Topbar, Crumb } from './topbar/topbar';

/**
 * The one shell. Replaces the two ~90% identical panel shells: there is no
 * admin panel any more, only capability-gated nav items and inline actions.
 */
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, Sidebar, Topbar],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app-shell.html',
  styleUrl: './app-shell.scss',
})
export class AppShell {
  protected readonly layout = inject(Layout);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  /** Current URL as a signal - drives both the crumbs and the active nav row. */
  private readonly currentUrl = toSignal(
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  protected readonly crumbs = computed<Crumb[]>(() => {
    this.currentUrl(); // dependency: recompute once per navigation
    const trail: Crumb[] = [];
    let route: ActivatedRoute | null = this.route;

    while (route) {
      const snapshot = route.snapshot;
      // Crumbs come from `data.breadcrumb` ONLY, never from `title`. A parent
      // and its index child both carry a title, so falling back to it would
      // print every section name twice.
      const label = snapshot.data['breadcrumb'] as string | undefined;
      if (label) {
        const path = '/' + snapshot.pathFromRoot.flatMap((r) => r.url.map((s) => s.path)).join('/');
        // A grouping route has no component, so Angular's default `emptyOnly`
        // inheritance copies its `data` onto the index child - and an index
        // child adds no URL segment. Without this guard every section renders
        // its own name twice.
        if (trail.at(-1)?.path !== path) trail.push({ label, path });
      }
      route = route.firstChild;
    }
    return trail;
  });

  /**
   * Exactly one winner, by longest matching prefix.
   *
   * This is why it is not `routerLinkActive`: two elements carrying the same
   * `view-transition-name` abort the entire transition and silently kill every
   * animation on the page. A prefix match can hit two links the moment a
   * sub-route exists (/attendance and /attendance/team), so the winner has to
   * be resolved once, here.
   */
  protected readonly activePath = computed(() => {
    // Strip query and fragment: `/settings/people?new=1` must still light up
    // the People row, and without this the pill vanishes on any link that
    // carries a parameter.
    const url = this.currentUrl().split(/[?#]/)[0];
    return (
      NAV.flatMap((section) => section.items)
        .filter((item) => url === item.path || url.startsWith(item.path + '/'))
        .sort((a, b) => b.path.length - a.path.length)[0]?.path ?? null
    );
  });

  constructor() {
    // Navigating always dismisses the drawer; reuses the existing URL stream
    // rather than opening a second subscription.
    //
    // `untracked` is load-bearing: closeDrawer() reads drawerOpen() internally,
    // so without it the effect takes a dependency on the very signal it writes.
    // Opening the drawer would re-run this effect and close it again - the
    // drawer could never open at all.
    effect(() => {
      this.currentUrl();
      untracked(() => this.layout.closeDrawer());
    });
  }
}
