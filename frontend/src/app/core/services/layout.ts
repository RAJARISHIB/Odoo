import { Injectable, signal } from '@angular/core';

/**
 * Below this the sidebar becomes a slide-over drawer.
 * Mirrored as `$compact` in src/styles/_shell.scss - CSS @media cannot read a
 * custom property, so the number lives in two places on purpose.
 */
export const COMPACT_QUERY = '(max-width: 880px)';

const STORAGE_KEY = 'hrms.sidebar.collapsed';

/** Sidebar collapse and mobile drawer state. */
@Injectable({ providedIn: 'root' })
export class Layout {
  /** Desktop: 64px icon rail vs the full 248px sidebar. Persisted. */
  readonly collapsed = signal(readStored());

  /** Compact: slide-over drawer. Never persisted - always closed on load. */
  readonly drawerOpen = signal(false);

  /**
   * Held in a field on purpose. A MediaQueryList with no strong reference is
   * eligible for garbage collection, and collecting it silently drops its
   * listeners - the breakpoint then never updates and the drawer never engages.
   */
  private readonly query = matchMedia(COMPACT_QUERY);

  /** True below the compact breakpoint. */
  readonly isCompact = signal(this.query.matches);

  constructor() {
    this.query.addEventListener('change', (event) => {
      this.isCompact.set(event.matches);
      // Resizing back up must not leave a scrim stuck over the page.
      if (!event.matches) this.setDrawer(false);
    });
  }

  /** One button, two meanings - the topbar hamburger does the right thing. */
  toggle(): void {
    if (this.isCompact()) this.setDrawer(!this.drawerOpen());
    else this.setCollapsed(!this.collapsed());
  }

  setCollapsed(value: boolean): void {
    this.collapsed.set(value);
    try {
      localStorage.setItem(STORAGE_KEY, value ? '1' : '0');
    } catch {
      // Storage disabled: the rail still collapses, it just will not persist.
    }
  }

  setDrawer(open: boolean): void {
    this.drawerOpen.set(open);
    document.body.classList.toggle('drawer-open', open);
  }

  closeDrawer(): void {
    if (this.drawerOpen()) this.setDrawer(false);
  }
}

function readStored(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}
