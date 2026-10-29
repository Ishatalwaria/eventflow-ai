import logging
import time

from django.conf import settings
from django.db import transaction

from apps.workflows.models import Workflow

from .evidence import build_workflow_evidence
from .models import IncidentSummary
from .providers.base import PermanentProviderError, TransientProviderError
from .providers.mock import DeterministicMockProvider
from .summary_schema import SummaryValidationError, validate_summary

logger = logging.getLogger(__name__)
PROMPT_VERSION = "incident-explanation-v1"


def get_provider():
    if settings.INCIDENT_LLM_PROVIDER == "mock":
        return DeterministicMockProvider()
    if settings.INCIDENT_LLM_PROVIDER == "openai":
        from .providers.openai import OpenAIResponsesProvider

        return OpenAIResponsesProvider()
    if settings.INCIDENT_LLM_PROVIDER == "gemini":
        from .providers.gemini import GeminiProvider

        return GeminiProvider()
    raise PermanentProviderError("Incident provider is not configured.")


def create_incident_summary(workflow: Workflow, requested_by, provider=None):
    evidence = build_workflow_evidence(workflow)
    provider = provider or get_provider()
    started = time.monotonic()
    result = None
    for attempt in range(settings.INCIDENT_LLM_MAX_ATTEMPTS):
        try:
            result = provider.generate(evidence)
            break
        except TransientProviderError as exc:
            # GeminiProvider already performs one model failover after a timeout. Retrying the
            # same primary/fallback sequence here would repeat two slow requests unchanged.
            if exc.error_code == "GEMINI_TIMEOUT":
                logger.warning(
                    "Incident provider timeout after model failover workflow_id=%s",
                    workflow.pk,
                )
                raise
            if attempt + 1 >= settings.INCIDENT_LLM_MAX_ATTEMPTS:
                logger.warning(
                    "Incident provider retries exhausted workflow_id=%s provider_error=%s",
                    workflow.pk,
                    exc.error_code,
                )
                raise
            time.sleep(min(settings.INCIDENT_LLM_RETRY_DELAY_SECONDS * (2**attempt), 2.0))
    if result is None:
        raise TransientProviderError(
            "Incident provider did not return a result.", error_code="PROVIDER_NO_RESULT"
        )
    try:
        summary = validate_summary(result.content, evidence)
    except SummaryValidationError:
        logger.warning("Rejected invalid incident summary workflow_id=%s", workflow.pk)
        raise PermanentProviderError(
            "Incident provider returned an invalid summary.", error_code="SUMMARY_SCHEMA_INVALID"
        ) from None
    with transaction.atomic():
        record = IncidentSummary.objects.create(
            workflow=workflow,
            requested_by=requested_by,
            evidence_hash=evidence["evidence_hash"],
            evidence=evidence,
            summary=summary,
            prompt_version=PROMPT_VERSION,
            provider=result.provider,
            model=result.model,
            latency_ms=max(result.latency_ms, int((time.monotonic() - started) * 1000)),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
    return record
