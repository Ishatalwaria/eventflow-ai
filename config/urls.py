from apps.common.metrics import MetricsView
from django.contrib import admin
from django.urls import include, path, reverse_lazy
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path(
        "",
        RedirectView.as_view(url=reverse_lazy("swagger-ui"), permanent=False),
        name="api-root",
    ),
    path("admin/", admin.site.urls),
    path("health/", include("apps.common.urls")),
    path("metrics", MetricsView.as_view(), name="metrics"),
    path("api/v1/", include("apps.events.urls")),
    path("api/v1/", include("apps.workflows.urls")),
    path("api/v1/", include("apps.incidents.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
