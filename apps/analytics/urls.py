from django.urls import path

from .views import LifecycleAnalyticsView, OverviewView, TenantLifecycleAnalyticsView

urlpatterns = [
    path("overview", OverviewView.as_view(), name="tenant-overview"),
    path(
        "tenant-lifecycle",
        TenantLifecycleAnalyticsView.as_view(),
        name="tenant-lifecycle-analytics",
    ),
    path("lifecycle", LifecycleAnalyticsView.as_view(), name="lifecycle-analytics"),
]
