__all__ = [
    "configure_models",
    "get_event_store",
    "Event",
    "get_outbox",
    "Repository",
    "Aggregate",
]

from typing import Callable, Type

from sqlalchemy.orm import Session

from event_sourcery.aggregate import Aggregate
from event_sourcery.event_store import EventStore
from event_sourcery.interfaces.event import Event as EventProtocol
from event_sourcery.interfaces.subscriber import Subscriber
from event_sourcery.outbox import Outbox
from event_sourcery.repository import Repository
from event_sourcery_pydantic.event import Event
from event_sourcery_pydantic.serde import PydanticSerde
from event_sourcery_sqlalchemy.models import configure_models
from event_sourcery_sqlalchemy.sqlalchemy_event_store import SqlAlchemyStorageStrategy


def get_event_store(
    session: Session,
    subscriptions: dict[Type[EventProtocol], list[Subscriber]] | None = None,
) -> EventStore:
    return EventStore(
        serde=PydanticSerde(),
        storage_strategy=SqlAlchemyStorageStrategy(session),
        event_base_class=Event,
        subscriptions=subscriptions,
    )


def get_outbox(session: Session, publisher: Callable[[EventProtocol], None]) -> Outbox:
    return Outbox(
        serde=PydanticSerde(),
        storage_strategy=SqlAlchemyStorageStrategy(session),
        event_base_class=Event,
        publisher=publisher,
    )
