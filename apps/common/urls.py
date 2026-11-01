from django.urls import path

from .health import LivenessView, ReadinessView, ServiceHealthView

urlpatterns = [
    path("live", LivenessView.as_view(), name="health-live"),
    path("ready", ReadinessView.as_view(), name="health-ready"),
    path("services", ServiceHealthView.as_view(), name="health-services"),
]
