from drf_spectacular.extensions import OpenApiAuthenticationExtension


class APIClientAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.common.authentication.APIClientAuthentication"
    name = "ClientBearer"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "CLIENT_UUID.SECRET",
        }


def add_api_error_envelopes(result, **_kwargs):
    """Document the common runtime error body without duplicating it per view."""
    components = result.setdefault("components", {}).setdefault("schemas", {})
    components["APIErrorEnvelope"] = {
        "type": "object",
        "required": ["error"],
        "properties": {
            "error": {
                "type": "object",
                "required": ["code", "message", "request_id", "details"],
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "request_id": {"type": "string", "nullable": True},
                    "details": {},
                },
            }
        },
    }
    response = {
        "description": "API error response using the common error envelope.",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/APIErrorEnvelope"}}
        },
    }
    for path, path_item in result.get("paths", {}).items():
        if not (path.startswith("/api/v1/") or path == "/health/services"):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            operation["responses"].setdefault("default", response)
    return result
