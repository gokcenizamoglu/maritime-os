"""
Tests for the rule engine metadata contract.

Scope, deliberately narrow: this file verifies GET /api/rules/metadata/
(rules/views.py::RuleViewSet.rule_metadata) and the data it's built
from (rules/facts.py::EVENT_FACT_FIELDS). It does NOT touch rule
evaluation, condition matching, or action execution — see
rules/services.py for that (untouched by this endpoint and by these
tests).

Every expected value here is READ from the same constants the endpoint
itself reads from (RULE_TRIGGERABLE_EVENT_TYPES, ACTIONS,
ACTION_REQUIRED_CONFIG_KEYS, OPERATORS, EVENT_FACT_FIELDS) rather than
re-typed as literals — the point of this suite is "does the endpoint
faithfully reflect the engine's vocabulary," which a hardcoded
duplicate list would defeat: it could drift from the real constants and
still pass.
"""
from authorization.test_helpers import grant_all_capabilities
from django.test import SimpleTestCase
from events.types import RULE_TRIGGERABLE_EVENT_TYPES
from rest_framework import status
from rest_framework.test import APITestCase
from rules.actions import ACTION_REQUIRED_CONFIG_KEYS, ACTIONS
from rules.conditions import OPERATORS
from rules.facts import EVENT_FACT_FIELDS
from tenants.models import Tenant
from users.models import User

METADATA_URL = "/api/rules/metadata/"


class RuleMetadataEndpointTests(APITestCase):
    """HTTP-level checks against the live endpoint (DB-backed: needs a
    real Tenant + User to exercise IsTenantMember)."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="Liva Marine", slug="liva-marine")
        cls.user = User.objects.create(username="ops-user", tenant=cls.tenant)
        grant_all_capabilities(cls.user)

    def test_authenticated_tenant_member_gets_200(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(METADATA_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unauthenticated_user_is_rejected(self):
        response = self.client.get(METADATA_URL)
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_every_triggerable_event_type_is_present(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(METADATA_URL)
        response_event_values = {event["value"] for event in response.data["events"]}
        self.assertEqual(response_event_values, set(RULE_TRIGGERABLE_EVENT_TYPES))

    def test_every_action_is_present(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(METADATA_URL)
        response_action_types = {action["action_type"] for action in response.data["actions"]}
        self.assertEqual(response_action_types, set(ACTIONS))

    def test_required_config_fields_come_from_action_required_config_keys(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(METADATA_URL)
        for action in response.data["actions"]:
            expected = sorted(ACTION_REQUIRED_CONFIG_KEYS[action["action_type"]])
            self.assertEqual(action["required_config_fields"], expected)

    def test_operators_match_rule_engine_operator_source(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(METADATA_URL)
        self.assertEqual(response.data["operators"], sorted(OPERATORS))

    def test_each_event_has_the_contract_keys(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(METADATA_URL)
        for event in response.data["events"]:
            self.assertEqual(set(event.keys()), {"value", "label", "available_facts"})

    def test_each_action_has_the_contract_keys(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(METADATA_URL)
        for action in response.data["actions"]:
            self.assertEqual(set(action.keys()), {"action_type", "label", "required_config_fields"})


class EventFactFieldsConsistencyTests(SimpleTestCase):
    """
    Pure data-integrity checks on rules/facts.py::EVENT_FACT_FIELDS —
    no DB, no HTTP. These catch the exact failure mode the metadata
    endpoint depends on not happening: EVENT_FACT_FIELDS is a hand
    maintained mirror of what each fact resolver actually returns (see
    that dict's docstring), so it can silently drift when a resolver or
    RULE_TRIGGERABLE_EVENT_TYPES changes without the mirror being
    updated.
    """

    databases = set()

    def test_every_triggerable_event_type_has_an_entry(self):
        missing = set(RULE_TRIGGERABLE_EVENT_TYPES) - set(EVENT_FACT_FIELDS)
        self.assertEqual(missing, set(), f"EVENT_FACT_FIELDS is missing entries for: {sorted(missing)}")

    def test_no_unknown_event_type_in_event_fact_fields(self):
        unknown = set(EVENT_FACT_FIELDS) - set(RULE_TRIGGERABLE_EVENT_TYPES)
        self.assertEqual(unknown, set(), f"EVENT_FACT_FIELDS has entries for non-triggerable events: {sorted(unknown)}")

    def test_available_facts_have_no_duplicates(self):
        for event_name, fields in EVENT_FACT_FIELDS.items():
            with self.subTest(event=event_name):
                self.assertEqual(
                    len(fields), len(set(fields)),
                    f"EVENT_FACT_FIELDS['{event_name}'] contains duplicate field names: {fields}",
                )
