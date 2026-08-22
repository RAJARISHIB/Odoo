import { Injectable } from '@angular/core';

import { AuthTokens, User } from '../models/user.model';

const ACCESS_KEY = 'hrms.access_token';
const REFRESH_KEY = 'hrms.refresh_token';
const USER_KEY = 'hrms.user';

/**
 * The only place that touches persistent auth storage.
 *
 * localStorage keeps the session across reloads, which is what a hackathon demo
 * wants. Swap the implementation here for cookies/sessionStorage if the threat
 * model changes - nothing else in the app reads these keys.
 */
@Injectable({ providedIn: 'root' })
export class TokenStorage {
  get accessToken(): string | null {
    return this.read(ACCESS_KEY);
  }

  get refreshToken(): string | null {
    return this.read(REFRESH_KEY);
  }

  get user(): User | null {
    const raw = this.read(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as User;
    } catch {
      return null;
    }
  }

  save(tokens: AuthTokens, user?: User): void {
    this.write(ACCESS_KEY, tokens.access_token);
    this.write(REFRESH_KEY, tokens.refresh_token);
    if (user) this.saveUser(user);
  }

  saveUser(user: User): void {
    this.write(USER_KEY, JSON.stringify(user));
  }

  clear(): void {
    [ACCESS_KEY, REFRESH_KEY, USER_KEY].forEach((key) => {
      try {
        localStorage.removeItem(key);
      } catch {
        /* storage unavailable (private mode) - nothing to clear */
      }
    });
  }

  private read(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  private write(key: string, value: string): void {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* ignore quota / private-mode failures */
    }
  }
}
