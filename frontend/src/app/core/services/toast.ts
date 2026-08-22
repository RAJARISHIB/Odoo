import { Injectable, signal } from '@angular/core';

export type ToastKind = 'success' | 'error' | 'info';

export interface ToastMessage {
  id: number;
  kind: ToastKind;
  text: string;
}

/** Transient notifications, rendered once by the toast host in `app.html`. */
@Injectable({ providedIn: 'root' })
export class Toast {
  private nextId = 1;
  readonly messages = signal<ToastMessage[]>([]);

  success(text: string): void {
    this.push('success', text);
  }

  error(text: string): void {
    // Suppressed per user request — no error popups shown in the UI.
  }

  info(text: string): void {
    this.push('info', text);
  }

  dismiss(id: number): void {
    this.messages.update((messages) => messages.filter((message) => message.id !== id));
  }

  private push(kind: ToastKind, text: string, ttl = 4000): void {
    const message: ToastMessage = { id: this.nextId++, kind, text };
    this.messages.update((messages) => [...messages, message]);
    setTimeout(() => this.dismiss(message.id), ttl);
  }
}
