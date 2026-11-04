"""Payment provider abstraction with a deterministic local simulator."""

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from django.db import IntegrityError, transaction

from apps.processing.errors import PermanentProcessingError, TransientProcessingError

from .models import PaymentIntent


@dataclass(frozen=True)
class PaymentResult:
    status: str
    provider_ref: str
    failure_code: str = ""


class PaymentProvider(Protocol):
    def authorize(
        self, *, amount_minor: int, currency: str, payment_method_token: str, idempotency_key: str
    ) -> PaymentResult: ...


class LocalPaymentSimulator:
    """Deterministic simulator. Not a real payment processor."""

    def authorize(self, *, amount_minor, currency, payment_method_token, idempotency_key):
        token = (payment_method_token or "ok_card").strip().lower()
        provider_ref = f"sim_{idempotency_key[:24]}"
        if token.startswith("fail_") or token == "fail":
            return PaymentResult(
                status=PaymentIntent.Status.REJECTED,
                provider_ref=provider_ref,
                failure_code="PAYMENT_DECLINED",
            )
        if token.startswith("timeout_") or token == "timeout":
            return PaymentResult(
                status=PaymentIntent.Status.TIMED_OUT,
                provider_ref=provider_ref,
                failure_code="PAYMENT_TIMEOUT",
            )
        if amount_minor <= 0:
            return PaymentResult(
                status=PaymentIntent.Status.REJECTED,
                provider_ref=provider_ref,
                failure_code="INVALID_AMOUNT",
            )
        return PaymentResult(
            status=PaymentIntent.Status.AUTHORIZED,
            provider_ref=provider_ref or f"sim_{uuid4().hex[:16]}",
        )


@transaction.atomic
def authorize_payment(
    *,
    order,
    workflow,
    idempotency_key,
    provider: PaymentProvider | None = None,
):
    existing = PaymentIntent.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        if existing.status == PaymentIntent.Status.REJECTED:
            raise PermanentProcessingError(
                existing.failure_code or "PAYMENT_DECLINED",
                "Payment authorization was rejected by the simulator.",
            )
        if existing.status == PaymentIntent.Status.TIMED_OUT:
            raise TransientProcessingError(
                existing.failure_code or "PAYMENT_TIMEOUT",
                "Payment authorization timed out.",
            )
        return existing

    provider = provider or LocalPaymentSimulator()
    result = provider.authorize(
        amount_minor=order.total_minor_units,
        currency=order.currency,
        payment_method_token=order.payment_method_token,
        idempotency_key=idempotency_key,
    )
    try:
        intent = PaymentIntent.objects.create(
            order=order,
            workflow=workflow,
            amount_minor=order.total_minor_units,
            currency=order.currency,
            status=result.status,
            provider="local_simulator",
            provider_ref=result.provider_ref,
            failure_code=result.failure_code,
            idempotency_key=idempotency_key,
        )
    except IntegrityError:
        return PaymentIntent.objects.get(idempotency_key=idempotency_key)

    if intent.status == PaymentIntent.Status.REJECTED:
        raise PermanentProcessingError(
            intent.failure_code or "PAYMENT_DECLINED",
            "Payment authorization was rejected by the simulator.",
        )
    if intent.status == PaymentIntent.Status.TIMED_OUT:
        raise TransientProcessingError(
            intent.failure_code or "PAYMENT_TIMEOUT",
            "Payment authorization timed out.",
        )
    return intent
