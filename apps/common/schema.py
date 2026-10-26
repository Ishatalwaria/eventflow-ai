from drf_spectacular.extensions import OpenApiAuthenticationExtension


class APIClientBearerScheme(OpenApiAuthenticationExtension):
    target_class = "apps.common.authentication.APIClientAuthentication"
    name = "ClientBearer"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "client-uuid.client-secret",
        }
