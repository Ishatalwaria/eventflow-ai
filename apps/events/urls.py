from django.urls import path

from .views import EventBatchCreateView, EventCollectionView, EventDetailView

urlpatterns = [
    path("events", EventCollectionView.as_view(), name="event-create"),
    path("events/batch", EventBatchCreateView.as_view(), name="event-batch-create"),
    path("events/<uuid:event_id>", EventDetailView.as_view(), name="event-detail"),
]
