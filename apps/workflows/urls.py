from django.urls import path

from .views import WorkflowDetailView, WorkflowListView

urlpatterns = [
    path("workflows", WorkflowListView.as_view(), name="workflow-list"),
    path("workflows/<uuid:workflow_id>", WorkflowDetailView.as_view(), name="workflow-detail"),
]
