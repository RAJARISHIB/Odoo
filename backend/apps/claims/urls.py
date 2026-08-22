"""Claims, Fines, and Requests routes split into employee and admin surfaces."""
from django.urls import path

from apps.claims import views

urlpatterns = [
    # Employee claims
    path("claims", views.claims_collection, name="claims-collection"),
    path("claims/<str:claim_id>/attachment", views.claim_attachment_download, name="claims-attachment-download"),

    # Employee fines
    path("fines", views.fines_collection, name="fines-collection"),

    # Employee requests
    path("requests", views.requests_collection, name="requests-collection"),
    path("requests/<str:request_id>/attachment", views.request_attachment_download, name="requests-attachment-download"),
]

admin_urlpatterns = [
    # Admin claims
    path("claims", views.admin_claims_collection, name="admin-claims-collection"),
    path("claims/<str:claim_id>/approve", views.admin_claim_approve, name="admin-claims-approve"),
    path("claims/<str:claim_id>/reject", views.admin_claim_reject, name="admin-claims-reject"),

    # Admin fines
    path("fines", views.admin_fines_collection, name="admin-fines-collection"),
    path("fines/<str:fine_id>", views.admin_fine_detail, name="admin-fines-detail"),

    # Admin requests
    path("requests", views.admin_requests_collection, name="admin-requests-collection"),
    path("requests/<str:request_id>/approve", views.admin_request_approve, name="admin-requests-approve"),
    path("requests/<str:request_id>/reject", views.admin_request_reject, name="admin-requests-reject"),
]
