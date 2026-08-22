import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Api, QueryParams } from './api';
import { Department, Organization, User, UserStats } from '../models/user.model';
import { Page } from '../models/api.model';

/** Employee directory + profile calls (admin panel and self-service). */
@Injectable({ providedIn: 'root' })
export class Users {
  private readonly api = inject(Api);

  list(params: QueryParams = {}): Observable<Page<User>> {
    return this.api.getPage<User>('users', params);
  }

  get(id: string): Observable<User> {
    return this.api.get<User>(`users/${id}`);
  }

  create(payload: Partial<User> & { email: string; first_name: string; password?: string }): Observable<User> {
    return this.api.post<User>('users', payload);
  }

  update(id: string, payload: Partial<User>): Observable<User> {
    return this.api.patch<User>(`users/${id}`, payload);
  }

  remove(id: string): Observable<unknown> {
    return this.api.delete(`users/${id}`);
  }

  resetPassword(id: string, newPassword?: string): Observable<{ temporary_password: string }> {
    return this.api.post<{ temporary_password: string }>(`users/${id}/reset-password`, {
      new_password: newPassword,
    });
  }

  stats(): Observable<UserStats> {
    return this.api.get<UserStats>('users/stats');
  }

  // -- self-service ------------------------------------------------------
  profile(): Observable<User> {
    return this.api.get<User>('profile');
  }

  updateProfile(payload: Partial<User>): Observable<User> {
    return this.api.patch<User>('profile', payload);
  }
}

/** Organization profile and departments. */
@Injectable({ providedIn: 'root' })
export class Organizations {
  private readonly api = inject(Api);

  current(): Observable<Organization> {
    return this.api.get<Organization>('organization');
  }

  update(payload: Partial<Organization>): Observable<Organization> {
    return this.api.patch<Organization>('organization', payload);
  }

  overview(): Observable<{ organization: Organization; departments: DepartmentHeadcount[] }> {
    return this.api.get('organization/overview');
  }

  departments(params: QueryParams = {}): Observable<Page<Department>> {
    return this.api.getPage<Department>('departments', params);
  }

  createDepartment(payload: Partial<Department>): Observable<Department> {
    return this.api.post<Department>('departments', payload);
  }

  updateDepartment(id: string, payload: Partial<Department>): Observable<Department> {
    return this.api.patch<Department>(`departments/${id}`, payload);
  }

  removeDepartment(id: string): Observable<unknown> {
    return this.api.delete(`departments/${id}`);
  }
}

export interface DepartmentHeadcount {
  department_id: string;
  name: string;
  headcount: number;
}
