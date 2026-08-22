import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Auth } from '../../core/services/auth';

@Component({
  selector: 'app-not-found',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page center" style="padding-top: 12vh">
      <h1 style="font-size: 46px">404</h1>
      <p class="muted">That page does not exist.</p>
      <a class="btn" [routerLink]="home()">Back to the portal</a>
    </div>
  `,
})
export class NotFound {
  private readonly auth = inject(Auth);

  protected home(): string {
    return this.auth.isAuthenticated() ? this.auth.homeRoute() : '/auth/login';
  }
}
