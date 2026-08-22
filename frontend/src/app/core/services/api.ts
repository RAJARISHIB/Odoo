import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { ApiResponse, EMPTY_PAGE_META, Page } from '../models/api.model';
import { environment } from '../../../environments/environment';

export type QueryParams = Record<string, string | number | boolean | null | undefined>;

/**
 * Thin HTTP layer over the Django API.
 *
 * Every feature service goes through here so the envelope is unwrapped in one
 * place: callers receive `data`, never `{ success, data }`.
 */
@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiUrl;

  get<T>(path: string, params?: QueryParams): Observable<T> {
    return this.http
      .get<ApiResponse<T>>(this.url(path), { params: this.params(params) })
      .pipe(map((response) => response.data));
  }

  /** GET a list endpoint, keeping the pagination metadata alongside the items. */
  getPage<T>(path: string, params?: QueryParams): Observable<Page<T>> {
    return this.http
      .get<ApiResponse<T[]>>(this.url(path), { params: this.params(params) })
      .pipe(
        map((response) => ({
          items: response.data ?? [],
          meta: { ...EMPTY_PAGE_META, ...(response.meta ?? {}) },
        })),
      );
  }

  post<T>(path: string, body?: unknown): Observable<T> {
    return this.http.post<ApiResponse<T>>(this.url(path), body ?? {}).pipe(map((r) => r.data));
  }

  patch<T>(path: string, body: unknown): Observable<T> {
    return this.http.patch<ApiResponse<T>>(this.url(path), body).pipe(map((r) => r.data));
  }

  put<T>(path: string, body: unknown): Observable<T> {
    return this.http.put<ApiResponse<T>>(this.url(path), body).pipe(map((r) => r.data));
  }

  delete<T>(path: string): Observable<T> {
    return this.http.delete<ApiResponse<T>>(this.url(path)).pipe(map((r) => r.data));
  }

  /** Full envelope, for the few calls that need `message` as well as `data`. */
  postRaw<T>(path: string, body?: unknown): Observable<ApiResponse<T>> {
    return this.http.post<ApiResponse<T>>(this.url(path), body ?? {});
  }

  private url(path: string): string {
    return `${this.baseUrl}/${path.replace(/^\//, '')}`;
  }

  private params(params?: QueryParams): HttpParams {
    let httpParams = new HttpParams();
    for (const [key, value] of Object.entries(params ?? {})) {
      if (value === null || value === undefined || value === '') continue;
      httpParams = httpParams.set(key, String(value));
    }
    return httpParams;
  }
}
