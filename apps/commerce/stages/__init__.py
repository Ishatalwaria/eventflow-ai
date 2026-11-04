from .fulfillment import HANDLERS as FULFILLMENT_HANDLERS
from .recovery import HANDLERS as RECOVERY_HANDLERS
from .replenishment import HANDLERS as REPLENISHMENT_HANDLERS

STAGE_HANDLERS = {
    **FULFILLMENT_HANDLERS,
    **REPLENISHMENT_HANDLERS,
    **RECOVERY_HANDLERS,
}


def get_handler(stage: str):
    try:
        return STAGE_HANDLERS[stage]
    except KeyError as exc:
        raise KeyError(f"No handler registered for stage: {stage}") from exc
