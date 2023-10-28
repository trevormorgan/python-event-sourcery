from functools import singledispatchmethod
from typing import Callable, Sequence, cast

from event_sourcery.event_store.event import (
    Event,
    EventRegistry,
    Metadata,
    RawEvent,
    Serde,
)
from event_sourcery.event_store.interfaces import OutboxStorageStrategy, StorageStrategy
from event_sourcery.event_store.stream_id import StreamId
from event_sourcery.event_store.versioning import (
    NO_VERSIONING,
    ExplicitVersioning,
    Versioning,
)


class EventStore:
    def __init__(
        self,
        storage_strategy: StorageStrategy,
        outbox_storage_strategy: OutboxStorageStrategy,
        event_registry: EventRegistry,
    ) -> None:
        self._serde = Serde()
        self._storage_strategy = storage_strategy
        self._outbox_storage_strategy = outbox_storage_strategy
        self._event_registry = event_registry

    def run_outbox(
        self,
        publisher: Callable[[Metadata, StreamId], None],
        limit: int = 100,
    ) -> None:
        stream = self._outbox_storage_strategy.outbox_entries(limit=limit)
        for entry in stream:
            with entry as raw_event_dict:
                event_type = self._event_registry.type_for_name(raw_event_dict["name"])
                event = self._serde.deserialize(
                    event=raw_event_dict,
                    event_type=event_type,
                )
                publisher(event, raw_event_dict["stream_id"])

    def load_stream(
        self,
        stream_id: StreamId,
        start: int | None = None,
        stop: int | None = None,
    ) -> Sequence[Metadata]:
        events = self._storage_strategy.fetch_events(stream_id, start=start, stop=stop)
        return self._deserialize_events(events)

    @singledispatchmethod
    def append(
        self,
        first: Metadata,
        *events: Metadata,
        stream_id: StreamId,
        expected_version: int | Versioning = 0,
    ) -> None:
        self._append(
            stream_id=stream_id,
            events=(first,) + events,
            expected_version=expected_version,
        )

    @append.register
    def _append_events(
        self,
        *events: Event,
        stream_id: StreamId,
        expected_version: int | Versioning = 0,
    ) -> None:
        wrapped_events = self._wrap_events(expected_version, events)
        self.append(
            *wrapped_events,
            stream_id=stream_id,
            expected_version=expected_version,
        )

    @singledispatchmethod
    def _wrap_events(
        self,
        expected_version: int,
        events: Sequence[Event],
    ) -> Sequence[Metadata]:
        return [
            Metadata.wrap(event=event, version=version)
            for version, event in enumerate(events, start=expected_version + 1)
        ]

    @_wrap_events.register
    def _wrap_events_versioning(
        self, expected_version: Versioning, events: Sequence[Event]
    ) -> Sequence[Metadata]:
        return [Metadata.wrap(event=event, version=None) for event in events]

    @singledispatchmethod
    def publish(
        self,
        first: Metadata,
        *events: Metadata,
        stream_id: StreamId,
        expected_version: int | Versioning = 0,
    ) -> None:
        serialized_events = self._append(
            stream_id=stream_id,
            events=(first,) + events,
            expected_version=expected_version,
        )
        self._outbox_storage_strategy.put_into_outbox(serialized_events)

    def _append(
        self,
        stream_id: StreamId,
        events: Sequence[Metadata],
        expected_version: int | Versioning,
    ) -> list[RawEvent]:
        new_version = events[-1].version
        versioning: Versioning
        if expected_version is not NO_VERSIONING:
            versioning = ExplicitVersioning(
                expected_version=cast(int, expected_version),
                initial_version=cast(int, new_version),
            )
        else:
            versioning = NO_VERSIONING

        self._storage_strategy.ensure_stream(
            stream_id=stream_id,
            versioning=versioning,
        )
        serialized_events = self._serialize_events(events, stream_id)
        self._storage_strategy.insert_events(serialized_events)
        return serialized_events

    def delete_stream(self, stream_id: StreamId) -> None:
        self._storage_strategy.delete_stream(stream_id)

    def save_snapshot(self, stream_id: StreamId, snapshot: Metadata) -> None:
        serialized = self._serde.serialize(
            event=snapshot,
            stream_id=stream_id,
            name=self._event_registry.name_for_type(type(snapshot.event)),
        )
        self._storage_strategy.save_snapshot(serialized)

    def _deserialize_events(self, events: list[RawEvent]) -> list[Metadata]:
        return [
            self._serde.deserialize(
                event=event,
                event_type=self._event_registry.type_for_name(event["name"]),
            )
            for event in events
        ]

    def _serialize_events(
        self,
        events: Sequence[Metadata],
        stream_id: StreamId,
    ) -> list[RawEvent]:
        return [
            self._serde.serialize(
                event=event,
                stream_id=stream_id,
                name=self._event_registry.name_for_type(type(event.event)),
            )
            for event in events
        ]