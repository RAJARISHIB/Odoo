import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { Auth } from '../../../core/services/auth';
import { Icon } from '../../icon/icon';

/**
 * Avatar dropdown: My Profile, Log Out.
 *
 * Built by hand rather than with a CDK overlay - the app has no CDK, and a
 * menu needs less code than the dependency would cost. It does need the full
 * set of manners: aria-haspopup/expanded, Escape, outside click, and focus
 * returned to the trigger on close.
 */
@Component({
  selector: 'app-user-menu',
  imports: [RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '(document:click)': 'onDocumentClick($event)',
    '(keydown.escape)': 'close(true)',
  },
  template: `
    <button
      class="trigger"
      type="button"
      aria-haspopup="menu"
      [attr.aria-expanded]="open()"
      [title]="auth.user()?.full_name ?? 'Account'"
      (click)="toggle($event)"
    >
      @if (auth.user()?.avatar_url; as avatar) {
        <img class="avatar sm" [src]="avatar" [alt]="auth.user()?.full_name ?? ''" />
      } @else {
        <span class="avatar sm">{{ initials() }}</span>
      }
      <app-icon name="chevron" [class.rot-180]="open()" />
    </button>

    @if (open()) {
      <div class="menu" role="menu">
        <div class="menu-head">
          <strong class="truncate">{{ auth.user()?.full_name }}</strong>
          <span class="truncate">{{ auth.user()?.email }}</span>
          @if (auth.loginId(); as id) {
            <code>{{ id }}</code>
          }
        </div>

        <a class="menu-item" role="menuitem" routerLink="/me" (click)="close()">
          <app-icon name="profile" />My profile
        </a>

        <button class="menu-item danger" role="menuitem" type="button" (click)="signOut()">
          <app-icon name="logout" />Log out
        </button>
      </div>
    }
  `,
  styles: `
    :host {
      position: relative;
      display: inline-flex;
    }

    .trigger {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 8px 4px 4px;
      border: 1px solid transparent;
      border-radius: var(--radius-full);
      background: transparent;
      color: var(--text-muted);
      cursor: pointer;
      --icon-size: 14px;
      transition: background var(--dur-fast) var(--ease-out);
    }

    .trigger:hover {
      background: var(--surface-alt);
    }

    .trigger app-icon {
      transition: transform var(--dur-fast) var(--ease-out);
    }

    .menu {
      position: absolute;
      top: calc(100% + 8px);
      right: 0;
      min-width: 236px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      box-shadow: var(--shadow-lg);
      padding: 6px;
      z-index: var(--z-menu);
      animation: menu-in var(--dur-fast) var(--ease-out);
    }

    .menu-head {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 10px 12px 12px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 6px;
    }

    .menu-head strong {
      font-size: 13.5px;
      font-weight: var(--weight-semibold);
    }

    .menu-head span {
      font-size: var(--text-xs);
      color: var(--text-subtle);
    }

    .menu-head code {
      font-size: var(--text-xs);
      color: var(--text-muted);
      margin-top: 4px;
    }

    .menu-item {
      width: 100%;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 9px 12px;
      border: none;
      border-radius: var(--radius-sm);
      background: transparent;
      color: var(--text);
      font: inherit;
      font-size: 13.5px;
      text-align: left;
      cursor: pointer;
      --icon-size: 17px;
    }

    .menu-item:hover {
      background: var(--surface-alt);
      text-decoration: none;
      color: var(--text);
    }

    .menu-item.danger {
      color: var(--danger);
    }

    .menu-item.danger:hover {
      background: var(--danger-soft);
      color: var(--danger);
    }
  `,
})
export class UserMenu {
  protected readonly auth = inject(Auth);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected readonly open = signal(false);

  protected readonly initials = computed(() => {
    const user = this.auth.user();
    if (!user) return '?';
    return `${user.first_name?.[0] ?? ''}${user.last_name?.[0] ?? ''}`.toUpperCase() || 'U';
  });

  protected toggle(event: MouseEvent): void {
    event.stopPropagation();
    this.open.update((v) => !v);
  }

  protected close(restoreFocus = false): void {
    if (!this.open()) return;
    this.open.set(false);
    if (restoreFocus) {
      this.host.nativeElement.querySelector<HTMLButtonElement>('.trigger')?.focus();
    }
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (!this.open()) return;
    if (!this.host.nativeElement.contains(event.target as Node)) this.close();
  }

  protected signOut(): void {
    this.close();
    this.auth.logout();
  }
}
