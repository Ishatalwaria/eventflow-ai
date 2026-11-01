from django.urls import path

from .views import IncidentSummaryCreateView, IncidentSummaryDetailView, IncidentSummaryListView

urlpatterns = [
    path("incidents", IncidentSummaryListView.as_view(), name="incident-summary-list"),
    path(
        "incidents/<uuid:incident_id>",
        IncidentSummaryDetailView.as_view(),
        name="incident-summary-detail",
    ),
    path(
        "workflows/<uuid:workflow_id>/incident-summary",
        IncidentSummaryCreateView.as_view(),
        name="incident-summary-create",
    ),
]
