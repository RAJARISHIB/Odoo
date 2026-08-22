import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { Toast } from '../../core/services/toast';

/** Renders the toast queue. Mounted once, in the app root. */
@Component({
  selector: 'app-toast-host',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="toast-host">
      @for (message of toast.messages(); track message.id) {
        <div class="toast" [class]="message.kind">
          <span class="spacer">{{ message.text }}</span>
          <button type="button" (click)="toast.dismiss(message.id)" aria-label="Dismiss">&times;</button>
        </div>
      }
    </div>
  `,
})
export class ToastHost {
  protected readonly toast = inject(Toast);
}
