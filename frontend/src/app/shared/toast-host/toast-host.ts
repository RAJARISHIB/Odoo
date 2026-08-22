import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { Icon } from '../icon/icon';
import { Toast } from '../../core/services/toast';
import type { IconName } from '../icon/icons';

/** Renders the toast queue. Mounted once, in the app root. */
@Component({
  selector: 'app-toast-host',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="toast-host">
      @for (message of toast.messages(); track message.id) {
        <!-- animate.leave is @angular/core 21, so dismissal fades instead of
             snapping without pulling in @angular/animations. -->
        <div class="toast" [class]="message.kind" animate.leave="toast-leaving" role="status">
          <app-icon class="lead" [name]="iconFor(message.kind)" />
          <span class="spacer">{{ message.text }}</span>
          <button type="button" (click)="toast.dismiss(message.id)" aria-label="Dismiss">
            <app-icon name="x" [strokeWidth]="2" />
          </button>
        </div>
      }
    </div>
  `,
  styles: `
    .lead {
      --icon-size: 17px;
      margin-top: 1px;
    }

    .toast.success .lead {
      color: var(--success);
    }

    .toast.error .lead {
      color: var(--danger);
    }

    .toast:not(.success):not(.error) .lead {
      color: var(--info);
    }

    .toast button {
      --icon-size: 15px;
      margin-top: 2px;
    }

    .toast-leaving {
      animation: toast-out var(--dur-fast) var(--ease-in) forwards;
    }
  `,
})
export class ToastHost {
  protected readonly toast = inject(Toast);

  protected iconFor(kind: string): IconName {
    if (kind === 'success') return 'check';
    if (kind === 'error') return 'warning';
    return 'info';
  }
}
