"""Payroll URL routes split into employee and admin surfaces."""
from django.urls import path

from apps.payroll import views

urlpatterns = [
    # Employee self-service
    path("payroll/me", views.my_payroll, name="my-payroll"),
    path("payroll/me/documents", views.my_payroll_documents, name="my-payroll-documents"),
    path("payroll/documents/<str:document_id>/download", views.download_payroll_document, name="download-payroll-document"),
]

admin_urlpatterns = [
    # Admin role templates
    path("payroll/templates", views.admin_role_templates, name="admin-payroll-templates"),
    path("payroll/templates/<str:template_id>", views.admin_role_template_detail, name="admin-payroll-template-detail"),
    path("payroll/preview", views.admin_preview_calculation, name="admin-payroll-preview"),

    # Admin employee payroll assignments
    path("payroll/employees", views.admin_employee_payrolls, name="admin-employee-payrolls"),
    path("payroll/employees/<str:user_id>", views.admin_employee_payroll_detail, name="admin-employee-payroll-detail"),

    # Admin payroll documents
    path("payroll/documents", views.admin_payroll_documents, name="admin-payroll-documents"),
    path("payroll/documents/<str:document_id>", views.admin_payroll_document_detail, name="admin-payroll-document-detail"),
]
