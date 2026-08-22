import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';
import { map } from 'rxjs/operators';

import {
  ADMIN_ROLES,
  AuthenticatedSession,
  AuthTokens,
  LoginResponse,
  MfaEnrollConfirm,
  MfaEnrollStart,
  Organization,
  Permissions,
  Session,
  SessionResponse,
  User,
} from '../models/user.model';
import { Api } from './api';
import { ApiResponse } from '../models/api.model';
import { Realtime } from './realtime';
import { TokenStorage } from './token-storage';
import { environment } from '../../../environments/environment';

/**
 * Session state for the whole app.
 *
 * Holds the signed-in user as a signal (templates read it directly), owns the
 * login/logout lifecycle, and starts or stops the websocket connection so the
 * socket's life matches the session's.
 */
@Injectable({ providedIn: 'root' })
export class Auth {
  private readonly api = inject(Api);
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly storage = inject(TokenStorage);
  private readonly realtime = inject(Realtime);

  private readonly userSignal = signal<User | null>(this.storage.user);
  private readonly organizationSignal = signal<Organization | null>(null);
  private readonly permissionsSignal = signal<Permissions | null>(null);
  /**
   * Set only while a sign-in is waiting on the second MFA factor: holds the
   * narrow `mfa_pending_token` from `login()`, which is not a real session
   * and is never persisted to storage - see `verifyMfa`.
   */
  private readonly mfaPendingTokenSignal = signal<string | null>(null);

  readonly user = this.userSignal.asReadonly();
  readonly organization = this.organizationSignal.asReadonly();
  readonly permissions = this.permissionsSignal.asReadonly();
  readonly mfaPending = computed(() => !!this.mfaPendingTokenSignal());

  readonly isAuthenticated = computed(() => !!this.userSignal() && !!this.storage.accessToken);
  /**
   * True while the user is still on a system-generated password.  Employees are
   * created by an admin, sign in with an issued password, and must replace it.
   */
  readonly mustChangePassword = computed(
    () => this.permissionsSignal()?.must_change_password ?? this.userSignal()?.must_change_password ?? false,
  );
  readonly isAdmin = computed(() => {
    const user = this.userSignal();
    return !!user && ADMIN_ROLES.includes(user.role);
  });
  readonly panel = computed(() => (this.isAdmin() ? 'admin' : 'user'));
  /** Where every user lands after signing in - one landing page for everybody. */
  readonly homeRoute = computed(() => '/employees');

  // -----------------------------------------------------------------
  // Session lifecycle
  // -----------------------------------------------------------------
  /**
   * Sign in with a login ID (OIJODO20220001) or an email address - the form has
   * one field for both, and the API decides which it received.
   */
  login(identifier: string, password: string): Observable<LoginResponse> {
    return this.api.post<LoginResponse>('auth/login', { identifier, password }).pipe(
      tap((result) => {
        if (result.mfa_required) {
          this.mfaPendingTokenSignal.set(result.mfa_pending_token ?? null);
          return;
        }
        this.mfaPendingTokenSignal.set(null);
        this.startSession(result.tokens!, result.user!);
      }),
    );
  }

  /** Second login step for an MFA-enabled account - a TOTP or recovery code. */
  verifyMfa(code: string): Observable<LoginResponse> {
    const pendingToken = this.mfaPendingTokenSignal();
    if (!pendingToken) throw new Error('No MFA challenge in progress.');

    return this.api
      .post<LoginResponse>('auth/mfa/verify', { mfa_pending_token: pendingToken, code })
      .pipe(
        tap((result) => {
          this.mfaPendingTokenSignal.set(null);
          this.startSession(result.tokens!, result.user!);
        }),
      );
  }

  /** Abandon an in-progress MFA challenge, e.g. "back to sign in". */
  cancelMfaChallenge(): void {
    this.mfaPendingTokenSignal.set(null);
  }

  /**
   * Bootstrap signup: creates the organization and its first super admin, who
   * receives a generated login ID like everybody else.
   *
   * Posted as multipart when a logo was chosen, plain JSON otherwise.
   */
  register(payload: RegistrationPayload, logo?: File | null): Observable<AuthenticatedSession> {
    const request = logo
      ? this.api.postForm<AuthenticatedSession>('auth/register', toFormData(payload, logo))
      : this.api.post<AuthenticatedSession>('auth/register', payload);

    return request.pipe(tap((result) => this.startSession(result.tokens, result.user)));
  }

  /** Re-read the session from the server - used by the app initialiser. */
  loadSession(): Observable<SessionResponse> {
    return this.api.get<SessionResponse>('auth/me').pipe(
      tap((session) => {
        this.userSignal.set(session.user);
        this.organizationSignal.set(session.organization);
        this.permissionsSignal.set(session.permissions);
        this.storage.saveUser(session.user);
        this.realtime.connect(this.storage.accessToken!, session.user.panel);
      }),
    );
  }

  logout(navigate = true): void {
    const refreshToken = this.storage.refreshToken;
    if (refreshToken) {
      // Fire and forget: the local session ends either way.
      this.api.post('auth/logout', { refresh_token: refreshToken }).subscribe({
        error: () => undefined,
      });
    }
    this.endSession();
    if (navigate) this.router.navigate(['/auth/login']);
  }

  changePassword(currentPassword: string, newPassword: string): Observable<unknown> {
    return this.api.post('auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }

  // -----------------------------------------------------------------
  // Self-service password reset / email verification
  // -----------------------------------------------------------------
  /** Always resolves the same way whether or not the account exists. */
  forgotPassword(identifier: string): Observable<unknown> {
    return this.api.post('auth/forgot-password', { identifier });
  }

  resetPassword(token: string, newPassword: string): Observable<unknown> {
    return this.api.post('auth/reset-password', { token, new_password: newPassword });
  }

  verifyEmail(token: string): Observable<unknown> {
    return this.api.post('auth/verify-email', { token });
  }

  resendVerification(): Observable<unknown> {
    return this.api.post('auth/resend-verification');
  }

  // -----------------------------------------------------------------
  // MFA (self-service security settings)
  // -----------------------------------------------------------------
  mfaEnrollStart(): Observable<MfaEnrollStart> {
    return this.api.post<MfaEnrollStart>('security/mfa/enroll/start');
  }

  mfaEnrollConfirm(code: string): Observable<MfaEnrollConfirm> {
    return this.api
      .post<MfaEnrollConfirm>('security/mfa/enroll/confirm', { code })
      .pipe(tap(() => this.refreshCurrentUser()));
  }

  mfaDisable(currentPassword: string, code: string): Observable<unknown> {
    return this.api
      .post('security/mfa/disable', { current_password: currentPassword, code })
      .pipe(tap(() => this.refreshCurrentUser()));
  }

  mfaRegenerateRecoveryCodes(currentPassword: string, code: string): Observable<MfaEnrollConfirm> {
    return this.api.post<MfaEnrollConfirm>('security/mfa/recovery-codes/regenerate', {
      current_password: currentPassword,
      code,
    });
  }

  /** Re-pulls `/auth/me` so `user()`/`permissions()` reflect a change made
   * out from under the cached session (MFA enabled/disabled, ...). */
  private refreshCurrentUser(): void {
    this.loadSession().subscribe({ error: () => undefined });
  }

  // -----------------------------------------------------------------
  // Active sessions ("signed-in devices")
  // -----------------------------------------------------------------
  listSessions(): Observable<Session[]> {
    return this.api.get<Session[]>('auth/sessions');
  }

  /** Sign out one specific *other* device - distinct from `logout()`, which
   * only ever acts on the caller's own current session or all of them. */
  revokeSession(sessionId: string): Observable<unknown> {
    return this.api.delete(`auth/sessions/${sessionId}`);
  }

  /** The signed-in user's login ID, for display. */
  readonly loginId = computed(() => this.userSignal()?.login_id ?? null);

  // -----------------------------------------------------------------
  // Tokens
  // -----------------------------------------------------------------
  /**
   * Exchange the refresh token for a new pair.
   *
   * Called by the auth interceptor on a 401. It uses `HttpClient` directly so
   * the request skips the interceptor and cannot recurse.
   */
  refreshTokens(): Observable<AuthTokens> {
    const refreshToken = this.storage.refreshToken;
    if (!refreshToken) throw new Error('No refresh token available.');

    return this.http
      .post<ApiResponse<AuthenticatedSession>>(`${environment.apiUrl}/auth/refresh`, {
        refresh_token: refreshToken,
      })
      .pipe(
        map((response) => response.data),
        tap((result) => {
          this.storage.save(result.tokens, result.user);
          this.userSignal.set(result.user);
          this.realtime.connect(result.tokens.access_token, result.user.panel);
        }),
        map((result) => result.tokens),
      );
  }

  get accessToken(): string | null {
    return this.storage.accessToken;
  }

  updateCurrentUser(user: User): void {
    this.userSignal.set(user);
    this.storage.saveUser(user);
  }

  // -----------------------------------------------------------------
  // Internals
  // -----------------------------------------------------------------
  private startSession(tokens: AuthTokens, user: User): void {
    this.storage.save(tokens, user);
    this.userSignal.set(user);
    this.realtime.connect(tokens.access_token, user.panel);
    // Login returns the user only; `/auth/me` fills in the organization and
    // permission flags the shells and guards read.
    this.loadSession().subscribe({ error: () => undefined });
  }

  private endSession(): void {
    this.storage.clear();
    this.userSignal.set(null);
    this.organizationSignal.set(null);
    this.permissionsSignal.set(null);
    this.realtime.disconnect();
  }
}


export interface RegistrationPayload {
  organization_name: string;
  name: string;
  email: string;
  phone?: string;
  password: string;
  confirm_password?: string;
}

/** Flatten a payload plus the logo file into multipart form data. */
function toFormData(payload: RegistrationPayload, logo: File): FormData {
  const form = new FormData();
  for (const [key, value] of Object.entries(payload)) {
    if (value !== null && value !== undefined && value !== '') form.append(key, String(value));
  }
  form.append('logo', logo, logo.name);
  return form;
}
