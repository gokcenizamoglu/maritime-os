"""
Wires `rules.services.evaluate_rules` up to every event type a Rule is
allowed to trigger on. Kept as a loop over
`events.types.RULE_TRIGGERABLE_EVENT_TYPES` rather than one
`@on(...)`-decorated function per event, so adding a new triggerable
event type is a one-line addition to that list — this file doesn't
change.
"""
from events.dispatcher import on
from events.types import RULE_TRIGGERABLE_EVENT_TYPES
from rules.services import evaluate_rules

for _event_name in RULE_TRIGGERABLE_EVENT_TYPES:
    on(_event_name)(evaluate_rules)
