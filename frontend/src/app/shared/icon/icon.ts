import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { ICONS, IconName } from './icons';

/**
 * Inline SVG icon.
 *
 * Sized in `em` off `--icon-size`, so it scales with the surrounding text by
 * default and can be pinned per use: `<app-icon name="bell" style="--icon-size: 20px" />`.
 * The 1.15em default is the optical correction that makes a 24px-grid stroke
 * icon sit right next to 14px body text.
 *
 * `stroke="currentColor"` means a rule like `.nav-row.is-active { color: … }`
 * recolours the icon with no extra selector.
 *
 * `strictTemplates` turns a typo in `name` into a compile error - a real
 * upgrade over the `icon: '▦'` strings this replaces.
 */
@Component({
  selector: 'app-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      [attr.stroke-width]="strokeWidth()"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      @for (d of paths(); track $index) {
        <path [attr.d]="d" />
      }
    </svg>
  `,
  styles: `
    :host {
      display: inline-flex;
      flex: none;
      width: 1em;
      height: 1em;
      font-size: var(--icon-size, 1.15em);
    }

    svg {
      width: 100%;
      height: 100%;
      display: block;
    }
  `,
  host: { '[attr.data-icon]': 'name()' },
})
export class Icon {
  readonly name = input.required<IconName>();
  readonly strokeWidth = input(1.75);

  protected readonly paths = computed(() => ICONS[this.name()]);
}
