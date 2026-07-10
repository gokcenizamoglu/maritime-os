"""
Import every domain's `listeners.py` here so their `@on(...)` decorators
run and populate the dispatcher's registry exactly once at process
startup.

WIRING: this is called from `events/apps.py` -> `EventsConfig.ready()`,
NOT from `settings.py` or a management command — `AppConfig.ready()` is
the documented, race-free hook Django provides for exactly this kind of
"import my signal/event handlers once" registration, and it runs only
after the whole app registry is populated, so importing other domains'
`listeners.py` here can never race app loading or cause a circular
import. To activate it, add `events` (or `events.apps.EventsConfig`) to
`INSTALLED_APPS`; that is the ONLY wiring step.

IDEMPOTENCY: `register_all_listeners()` guards itself with the
module-level `_listeners_registered` flag below, so calling it more than
once (a second app wiring it, a test harness, a reload) registers the
handlers exactly once — no double-firing. The flag is set only AFTER the
imports succeed, so if a listener module fails to import, the failure is
NOT swallowed: the flag stays False and the ImportError propagates out of
`ready()`, which Django surfaces as a hard startup error rather than a
silently unregistered listener that would just never fire.
"""

# Set to True only after all listener modules import successfully. Kept
# module-level (not on the dispatcher) so registration status is a fact
# about THIS bootstrap, independent of the dispatcher's registry.
_listeners_registered = False


def register_all_listeners() -> None:
    global _listeners_registered
    if _listeners_registered:
        return

    import activity.listeners  # noqa: F401
    import checklists.listeners  # noqa: F401
    import rules.listeners  # noqa: F401
    # workflow currently has no cross-domain listeners of its own — its
    # orchestration (sync_step_statuses) runs synchronously inside
    # workflow.services itself, not in response to another domain's
    # event. Add `import workflow.listeners` above (before the flag is
    # set) the day workflow needs to react to something outside its own
    # domain (e.g. an external organization's response via an
    # integrations app).

    _listeners_registered = True
