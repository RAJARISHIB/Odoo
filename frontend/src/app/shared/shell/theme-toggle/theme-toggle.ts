import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { Theme, ThemeChoice } from '../../../core/services/theme';
import { Icon } from '../../icon/icon';
import type { IconName } from '../../icon/icons';

/**
 * Three-segment control, not a two-state switch: `system` has to stay
 * reachable, otherwise a user who once pinned a theme can never hand the
 * decision back to their OS.
 */
@Component({
  selector: 'app-theme-toggle',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="theme-toggle" role="radiogroup" aria-label="Colour theme">
      @for (option of options; track option.value) {
        <button
          type="button"
          role="radio"
          [attr.aria-checked]="theme.choice() === option.value"
          [class.is-on]="theme.choice() === option.value"
          [title]="option.label"
          (click)="theme.set(option.value)"
        >
          <app-icon [name]="option.icon" />
          <span class="sr-only">{{ option.label }}</span>
        </button>
      }
    </div>
  `,
  styles: `
    .theme-toggle {
      display: flex;
      align-items: center;
      gap: 2px;
      padding: 3px;
      border: 1px solid var(--border);
      border-radius: var(--radius-full);
      background: var(--bg);
    }

    button {
      width: 26px;
      height: 26px;
      display: grid;
      place-items: center;
      border: none;
      border-radius: var(--radius-full);
      background: transparent;
      color: var(--text-subtle);
      cursor: pointer;
      padding: 0;
      --icon-size: 14px;
      transition:
        background var(--dur-fast) var(--ease-out),
        color var(--dur-fast) var(--ease-out);
    }

    button:hover {
      color: var(--text);
    }

    button.is-on {
      background: var(--surface);
      color: var(--primary);
      box-shadow: var(--shadow-xs);
    }
  `,
})
export class ThemeToggle {
  protected readonly theme = inject(Theme);

  protected readonly options: { value: ThemeChoice; icon: IconName; label: string }[] = [
    { value: 'light', icon: 'sun', label: 'Light' },
    { value: 'dark', icon: 'moon', label: 'Dark' },
    { value: 'system', icon: 'monitor', label: 'Match system' },
  ];
}
