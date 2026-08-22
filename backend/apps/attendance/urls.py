"""Attendance routes, split by panel.

`urlpatterns`       -> /api/v1/attendance/...        (employee, user panel)
`admin_urlpatterns` -> /api/v1/admin/attendance/...  (admin panel)
"""
from django.urls import path

from apps.attendance import views

urlpatterns = [
    path("attendance/status", views.attendance_status, name="attendance-status"),
    path("attendance/check-in", views.check_in, name="attendance-check-in"),
    path("attendance/check-out", views.check_out, name="attendance-check-out"),
    path("attendance/me", views.my_attendance, name="attendance-me"),
    path("attendance/me/summary", views.my_summary, name="attendance-me-summary"),
]

admin_urlpatterns = [
    path("attendance", views.admin_attendance_collection, name="admin-attendance-collection"),
    path("attendance/overview", views.admin_attendance_overview, name="admin-attendance-overview"),
    path("attendance/<str:record_id>", views.admin_attendance_detail, name="admin-attendance-detail"),
    path("attendance/users/<str:user_id>/summary", views.admin_user_summary, name="admin-attendance-user-summary"),
]
