"""Leave routes for employee panel."""
from django.urls import path

from apps.leaves import views

urlpatterns = [
    path("leaves/calendar", views.calendar, name="leaves-calendar"),
    path("leaves/holidays", views.holidays, name="leaves-holidays"),
    path("leaves/balance", views.balance, name="leaves-balance"),
    path("leaves/requests", views.requests, name="leaves-requests"),
    path("leaves/requests/<str:request_id>/cancel", views.cancel_request, name="leaves-cancel-request"),
]
