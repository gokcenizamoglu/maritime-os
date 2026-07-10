"""
The `events` app owns the domain-event dispatcher, so it is also the app
responsible for guaranteeing every domain's listeners are registered
before any event can be emitted.

`ready()` is Django's one race-free, exactly-once startup hook: the app
registry calls it a single time per app, only after ALL apps in
INSTALLED_APPS have finished loading their models. That ordering is why
importing other domains' `listeners.py` from here is safe — nothing they
import can be half-loaded yet, so there is no circular-import window.

The `register_all_listeners()` import is done INSIDE `ready()`, not at
module top level, so merely importing `events.apps` (which Django does
early, while building the app registry) has no side effect and pulls in
no other domain.
"""
from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = "events"

    def ready(self) -> None:
        # Idempotent (see events/bootstrap.py): safe even if another app
        # or a test harness also calls it.
        from events.bootstrap import register_all_listeners

        register_all_listeners()
