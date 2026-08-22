import { Injectable, computed, signal } from '@angular/core';

export type ThemeChoice = 'light' | 'dark' | 'system';

/** Must match the literal in the inline bootstrap script in src/index.html. */
const STORAGE_KEY = 'hrms.theme';

/**
 * Colour theme with three states.
 *
 * `system` removes `data-theme` entirely and lets the media query in
 * `_tokens-color.scss` decide; `light` and `dark` pin the attribute so the
 * choice wins over the OS setting in both directions.
 *
 * Reading `matchMedia` and `localStorage` in the constructor is safe here -
 * `main.ts` bootstraps in the browser with no platform-server. Under SSR both
 * would throw and each needs an `isPlatformBrowser` guard.
 */
@Injectable({ providedIn: 'root' })
export class Theme {
  private readonly query = matchMedia('(prefers-color-scheme: dark)');
  private readonly systemDark = signal(this.query.matches);

  readonly choice = signal<ThemeChoice>(readStored());

  /** What is actually painted right now - drives the toggle's pressed state. */
  readonly resolved = computed<'light' | 'dark'>(() => {
    const choice = this.choice();
    return choice === 'system' ? (this.systemDark() ? 'dark' : 'light') : choice;
  });

  constructor() {
    // Signals notify the scheduler directly, which is why this works with no
    // zone to catch the native event. Never mirror these into plain fields.
    this.query.addEventListener('change', (event) => this.systemDark.set(event.matches));
    this.apply(this.choice());
  }

  set(choice: ThemeChoice): void {
    this.choice.set(choice);
    this.apply(choice);
  }

  private apply(choice: ThemeChoice): void {
    const el = document.documentElement;
    if (choice === 'system') el.removeAttribute('data-theme');
    else el.setAttribute('data-theme', choice);

    // Keeps native scrollbars, form widgets and the canvas in step with tokens.
    el.style.colorScheme = choice === 'system' ? 'light dark' : choice;

    try {
      localStorage.setItem(STORAGE_KEY, choice);
    } catch {
      // Private browsing with storage disabled: the theme still applies for
      // this session, it just will not survive a reload.
    }
  }
}

function readStored(): ThemeChoice {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === 'light' || stored === 'dark' ? stored : 'system';
  } catch {
    return 'system';
  }
}
