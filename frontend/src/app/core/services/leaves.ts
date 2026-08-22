import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Api, QueryParams } from './api';
import {
  CalendarFeed,
  CreateLeavePayload,
  Holiday,
  LeaveBalance,
  LeaveRequest,
} from '../models/leaves.model';
import { Page } from '../models/api.model';

@Injectable({ providedIn: 'root' })
export class Leaves {
  private readonly api = inject(Api);

  getCalendar(params: QueryParams = {}): Observable<CalendarFeed> {
    return this.api.get<CalendarFeed>('leaves/calendar', params);
  }

  getHolidays(params: QueryParams = {}): Observable<Holiday[]> {
    return this.api.get<Holiday[]>('leaves/holidays', params);
  }

  getBalance(params: QueryParams = {}): Observable<LeaveBalance> {
    return this.api.get<LeaveBalance>('leaves/balance', params);
  }

  getMyRequests(params: QueryParams = {}): Observable<Page<LeaveRequest>> {
    return this.api.getPage<LeaveRequest>('leaves/requests', params);
  }

  applyLeave(payload: CreateLeavePayload): Observable<LeaveRequest> {
    return this.api.post<LeaveRequest>('leaves/requests', payload);
  }

  cancelLeave(requestId: string): Observable<LeaveRequest> {
    return this.api.post<LeaveRequest>(`leaves/requests/${requestId}/cancel`);
  }
}
