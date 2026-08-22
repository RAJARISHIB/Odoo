import { Component, inject } from '@angular/core';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';

import { Auth } from './core/services/auth';
import { Realtime } from './core/services/realtime';
import { Theme } from './core/services/theme';
import { ToastHost } from './shared/toast-host/toast-host';

/**
 * App root: a router outlet plus the toast host.
 *
 * It also reports every navigation to the websocket hub as UI context, so the
 * backend can see which panel and screen each connected client is on.
 */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet, ToastHost],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly router = inject(Router);
  private readonly realtime = inject(Realtime);
  private readonly auth = inject(Auth);
  /** Injected here so the theme applies on boot, including on the auth pages
      where the topbar (and its toggle) never renders. */
  private readonly theme = inject(Theme);

  constructor() {
    this.router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event) => {
        if (!this.auth.isAuthenticated()) return;
        this.realtime.setContext({
          panel: this.auth.panel(),
          route: event.urlAfterRedirects,
          view: event.urlAfterRedirects.split('/').filter(Boolean).pop() ?? 'root',
        });
      });
  }
}
