from django.test import override_settings

from apps.processing.adapters.kafka import _kafka_security_config


@override_settings(
    KAFKA_SECURITY_PROTOCOL="SASL_SSL",
    KAFKA_SASL_MECHANISM="SCRAM-SHA-512",
    KAFKA_SASL_USERNAME="integration-user",
    KAFKA_SASL_PASSWORD="integration-password",
    KAFKA_SSL_CA_LOCATION="/run/secrets/kafka-ca.pem",
)
def test_kafka_adapter_receives_tls_and_sasl_settings():
    assert _kafka_security_config() == {
        "security.protocol": "SASL_SSL",
        "sasl.mechanism": "SCRAM-SHA-512",
        "sasl.username": "integration-user",
        "sasl.password": "integration-password",
        "ssl.ca.location": "/run/secrets/kafka-ca.pem",
    }


@override_settings(KAFKA_SECURITY_PROTOCOL="SSL", KAFKA_SSL_CA_LOCATION="")
def test_tls_without_sasl_does_not_add_sasl_credentials():
    assert _kafka_security_config() == {"security.protocol": "SSL"}
