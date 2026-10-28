from typing import Protocol


class KafkaRecord(Protocol):
    value: bytes
    key: bytes | None
    topic: str
    partition: int
    offset: int


class KafkaPublisher(Protocol):
    def publish(self, *, topic: str, key: bytes, value: bytes, timeout: float) -> None: ...

    def close(self) -> None: ...


class KafkaEventConsumer(Protocol):
    def poll(self, timeout: float) -> KafkaRecord | None: ...

    def commit(self, record: KafkaRecord) -> None: ...

    def close(self) -> None: ...


class RabbitTaskPublisher(Protocol):
    def publish_task(self, task: dict) -> None: ...

    def publish_retry(self, task: dict, retry_index: int) -> None: ...

    def publish_dead_letter(self, task: dict, *, error_code: str, detail: str) -> None: ...

    def publish_invalid_payload(self, *, message_id: str, body: bytes, error_code: str) -> None: ...

    def close(self) -> None: ...


class RabbitDelivery(Protocol):
    body: bytes

    def ack(self) -> None: ...

    def reject_without_requeue(self) -> None: ...


class RabbitTaskConsumer(Protocol):
    def consume(self, handler, *, should_stop) -> None: ...

    def close(self) -> None: ...
