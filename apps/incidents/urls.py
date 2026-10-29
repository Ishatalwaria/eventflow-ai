from django.urls import path

from .views import IncidentSummaryCreateView

urlpatterns = [
    path(
        "workflows/<uuid:workflow_id>/incident-summary",
        IncidentSummaryCreateView.as_view(),
        name="incident-summary-create",
    ),
]
