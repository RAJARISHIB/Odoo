import { Injectable, inject } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterStateSnapshot, TitleStrategy } from '@angular/router';

/**
 * Appends the product name to every route's title, so a browser tab reads
 * "Employees · Humlynk" instead of a bare "Employees" with no brand at all -
 * the default strategy just sets `document.title` to the route's `title`.
 */
@Injectable({ providedIn: 'root' })
export class BrandTitleStrategy extends TitleStrategy {
  private readonly title = inject(Title);

  override updateTitle(snapshot: RouterStateSnapshot): void {
    const routeTitle = this.buildTitle(snapshot);
    this.title.setTitle(routeTitle ? `${routeTitle} · Humlynk` : 'Humlynk');
  }
}
