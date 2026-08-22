import { ChangeDetectionStrategy, Component, input } from '@angular/core';

let nextId = 0;

/**
 * The Humlynk mark: two figures joined by a connecting curve - "people" and
 * "connection" merged into an H. Monochrome via `currentColor`, like the rest
 * of the icon system (`shared/icon/icon.ts`), so it drops onto any background
 * - white on the deep-teal auth pane, `--primary` in a header - without a
 * colour input of its own.
 *
 * `loading` swaps in a looping pulse-and-flow animation for moments where the
 * mark itself is the thing on screen: an auth submit, the boot splash. It is
 * deliberately not a general-purpose spinner - tables and buttons elsewhere
 * already have a plainer one for routine waits.
 *
 * Each instance needs its own gradient id: two logos can be mounted at once
 * (the auth-pane mark plus a submit button's loading mark), and SVG resolves
 * `url(#id)` to whichever element with that id appears first in the document,
 * so a shared id would make the second instance render the first one's stroke.
 */
@Component({
  selector: 'app-logo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '[style.--logo-size.px]': 'size()',
    '[class.is-loading]': 'loading()',
  },
  templateUrl: './logo.html',
  styleUrl: './logo.scss',
})
export class Logo {
  readonly size = input(28);
  readonly loading = input(false);

  protected readonly gradId = `humlynk-flow-${nextId++}`;
}
