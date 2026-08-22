"""Leave routes.

`urlpatterns`       -> /api/v1/...              (employee panel, unchanged)
`admin_urlpatterns` -> /api/v1/admin/leaves/...  (admin leave module, new)
"""
from django.urls import path

from apps.leaves import views

urlpatterns = [
    path("leaves/calendar", views.calendar, name="leaves-calendar"),
    path("leaves/holidays", views.holidays, name="leaves-holidays"),
    path("leaves/balance", views.balance, name="leaves-balance"),
    path("leaves/requests", views.requests, name="leaves-requests"),
    path("leaves/requests/<str:request_id>/cancel", views.cancel_request, name="leaves-cancel-request"),

    # Admin leave module - shared reads / role-checked writes, kept off the
    # /admin/ prefix only where an employee also needs read access.
    path("leaves/types", views.leave_type_collection, name="leaves-type-collection"),
    path("leaves/types/<str:type_id>", views.leave_type_detail, name="leaves-type-detail"),
    path("leaves/types/<str:type_id>/activate", views.leave_type_activate, name="leaves-type-activate"),
    path("leaves/types/<str:type_id>/deactivate", views.leave_type_deactivate, name="leaves-type-deactivate"),
]

admin_urlpatterns = [
    path("leaves/holidays", views.holiday_admin_collection, name="admin-leaves-holiday-collection"),
    path("leaves/holidays/<str:holiday_id>", views.holiday_admin_detail, name="admin-leaves-holiday-detail"),

    path("leaves/requests", views.admin_leave_request_collection, name="admin-leaves-request-collection"),
    path("leaves/requests/<str:request_id>", views.admin_leave_request_detail, name="admin-leaves-request-detail"),
    path("leaves/requests/<str:request_id>/approve", views.admin_leave_request_approve, name="admin-leaves-request-approve"),
    path("leaves/requests/<str:request_id>/reject", views.admin_leave_request_reject, name="admin-leaves-request-reject"),

    path("leaves/allocation-rules", views.allocation_rule_collection, name="admin-leaves-allocation-rule-collection"),
    path("leaves/allocation-rules/generate", views.allocation_generate, name="admin-leaves-allocation-generate"),
    path("leaves/allocation-rules/<str:rule_id>", views.allocation_rule_detail, name="admin-leaves-allocation-rule-detail"),

    path("leaves/adjustments", views.adjustment_collection, name="admin-leaves-adjustment-collection"),

    path("leaves/balances", views.admin_leave_balances, name="admin-leaves-balances"),
    path("leaves/dashboard", views.admin_leave_dashboard, name="admin-leaves-dashboard"),
    path("leaves/employees/<str:user_id>/summary", views.admin_leave_employee_summary, name="admin-leaves-employee-summary"),
]
