from dataclasses import dataclass


@dataclass(frozen=True)
class StageDef:
    name: str
    compensate: str | None = None


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_type: str
    trigger_event: str
    stages: tuple[StageDef, ...]
    compensate_on_permanent_failure: bool = True

    @property
    def first_stage(self) -> str:
        return self.stages[0].name

    def stage_names(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self.stages)

    def next_stage(self, stage: str) -> str | None:
        names = self.stage_names()
        try:
            index = names.index(stage)
        except ValueError:
            return None
        if index + 1 >= len(names):
            return None
        return names[index + 1]

    def compensate_stage_for(self, stage: str) -> str | None:
        for item in self.stages:
            if item.name == stage:
                return item.compensate
        return None

    def compensation_chain(self, failed_stage: str) -> tuple[str, ...]:
        """Return compensate stages for completed forwards before failed_stage, LIFO."""
        names = self.stage_names()
        try:
            failed_index = names.index(failed_stage)
        except ValueError:
            return ()
        chain = []
        for stage in reversed(self.stages[:failed_index]):
            if stage.compensate:
                chain.append(stage.compensate)
        return tuple(chain)


ORDER_FULFILLMENT = WorkflowDefinition(
    workflow_type="order_fulfillment",
    trigger_event="order.created",
    stages=(
        StageDef("validate_order"),
        StageDef("reserve_inventory", compensate="release_inventory"),
        StageDef("authorize_payment"),
        StageDef("confirm_order"),
        StageDef("prepare_shipment"),
        StageDef("notify"),
    ),
)

INVENTORY_REPLENISHMENT = WorkflowDefinition(
    workflow_type="inventory_replenishment",
    trigger_event="inventory.replenishment.requested",
    stages=(
        StageDef("validate_replenishment"),
        StageDef("approve_replenishment"),
        StageDef("apply_stock"),
        StageDef("complete_replenishment"),
    ),
    compensate_on_permanent_failure=False,
)

PAYMENT_RECOVERY = WorkflowDefinition(
    workflow_type="payment_recovery",
    trigger_event="payment.recovery.requested",
    stages=(
        StageDef("load_failed_payment"),
        StageDef("retry_authorize_payment"),
        StageDef("finalize_recovery"),
    ),
    compensate_on_permanent_failure=True,
)

WORKFLOW_DEFINITIONS: dict[str, WorkflowDefinition] = {
    ORDER_FULFILLMENT.workflow_type: ORDER_FULFILLMENT,
    INVENTORY_REPLENISHMENT.workflow_type: INVENTORY_REPLENISHMENT,
    PAYMENT_RECOVERY.workflow_type: PAYMENT_RECOVERY,
}

EVENT_TO_WORKFLOW = {
    definition.trigger_event: definition.workflow_type
    for definition in WORKFLOW_DEFINITIONS.values()
}


def get_definition(workflow_type: str) -> WorkflowDefinition:
    try:
        return WORKFLOW_DEFINITIONS[workflow_type]
    except KeyError as exc:
        raise KeyError(f"Unknown workflow type: {workflow_type}") from exc


def workflow_type_for_event(event_type: str) -> str:
    try:
        return EVENT_TO_WORKFLOW[event_type]
    except KeyError as exc:
        raise KeyError(f"No workflow mapped for event type: {event_type}") from exc
