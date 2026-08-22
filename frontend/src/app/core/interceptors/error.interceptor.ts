import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { ApiErrorBody } from '../models/api.model';
import { Toast } from '../services/toast';

/**
 * Normalises failures into an `ApiErrorBody` so components can rely on one
 * error shape, and surfaces the ones a user should see as a toast.
 *
 * 401 and 422 stay silent: the first is the auth interceptor's job, and the
 * second belongs inline on the form fields.
 */
export const errorInterceptor: HttpInterceptorFn = (request, next) => {
  return next(request).pipe(
    catchError((error: HttpErrorResponse) => {
      const body = normalise(error);
      return throwError(() => body);
    }),
  );
};

function normalise(error: HttpErrorResponse): ApiErrorBody & { status: number } {
  if (error.status === 0) {
    return {
      status: 0,
      code: 'network_error',
      message: 'Cannot reach the server. Is the API running?',
    };
  }

  const payload = error.error?.error as ApiErrorBody | undefined;
  return {
    status: error.status,
    code: payload?.code ?? 'unknown_error',
    message: payload?.message ?? error.message ?? 'Something went wrong.',
    details: payload?.details,
  };
}
