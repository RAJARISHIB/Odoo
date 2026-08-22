"""Routes for the organization profile and its departments."""
from django.urls import path

from apps.organization import views

urlpatterns = [
    path("organization", views.organization, name="organization"),
    path("organization/logo", views.organization_logo, name="organization-logo"),
    path("organization/overview", views.organization_overview, name="organization-overview"),
    path("departments", views.department_collection, name="department-collection"),
    path("departments/<str:department_id>", views.department_detail, name="department-detail"),
]
