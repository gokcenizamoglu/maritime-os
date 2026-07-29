from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import resolve, reverse

from activity.models import ActivityLog
from authorization.models import (
    Capability,
    RoleCapability,
    TenantRole,
    UserRoleAssignment,
)
from catalog import services as catalog_services
from catalog.models import (
    DocumentType,
    Flag,
    OrganizationType,
    ServiceType,
    TenantServiceOffering,
)
from checklists.models import ChecklistItem, ChecklistTemplate
from customers.models import Customer
from organizations.models import Organization, TenantFlagRelationship
from service_requests.models import ServiceRequest
from tenants.models import Tenant
from vessels.models import Vessel
from workflow.models import (
    OperationTemplate,
    OperationTemplateVersion,
    WorkflowStepInstance,
    WorkflowStepTemplate,
)
from workflow.services import archive_version, publish_version, retire_version


class AdminFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.tenant = Tenant.objects.create(name="Alpha Marine", slug="alpha")
        cls.other_tenant = Tenant.objects.create(name="Beta Marine", slug="beta")
        cls.superuser = User.objects.create_superuser(
            username="platform-admin",
            email="platform@example.test",
            password="test-platform-password",
        )
        cls.staff = User.objects.create_user(
            username="limited-staff",
            password="test-staff-password",
            tenant=cls.tenant,
            is_staff=True,
        )
        cls.non_staff = User.objects.create_user(
            username="tenant-user",
            password="test-user-password",
            tenant=cls.tenant,
        )

        cls.customer = Customer.objects.create(tenant=cls.tenant, name="Alpha Shipping")
        cls.other_customer = Customer.objects.create(
            tenant=cls.other_tenant, name="Beta Shipping",
        )
        cls.vessel = Vessel.objects.create(
            tenant=cls.tenant,
            customer=cls.customer,
            name="North Star",
            imo_number="IMO-ADMIN-1",
        )
        cls.flag = Flag.objects.create(name="Admin Flag", code="AF")
        cls.service_type = ServiceType.objects.create(
            name="Admin Service",
            code="admin-service",
            flag_scope=ServiceType.FlagScope.REQUIRED,
        )
        cls.document_type = DocumentType.objects.create(
            name="Admin Document",
            code="admin-document",
        )
        cls.organization_type = OrganizationType.objects.create(
            name="Admin Registry",
            code="admin-registry",
        )
        cls.partner = Organization.objects.create(
            tenant=cls.tenant,
            organization_type=cls.organization_type,
            name="Alpha Partner",
        )
        cls.other_partner = Organization.objects.create(
            tenant=cls.other_tenant,
            organization_type=cls.organization_type,
            name="Beta Partner",
        )
        cls.relationship = TenantFlagRelationship.objects.create(
            tenant=cls.tenant,
            flag=cls.flag,
            relationship_type=TenantFlagRelationship.RelationshipType.PARTNER,
            partner_organization=cls.partner,
            status=TenantFlagRelationship.Status.ACTIVE,
        )
        cls.other_relationship = TenantFlagRelationship.objects.create(
            tenant=cls.other_tenant,
            flag=cls.flag,
            relationship_type=TenantFlagRelationship.RelationshipType.PARTNER,
            partner_organization=cls.other_partner,
            status=TenantFlagRelationship.Status.ACTIVE,
        )
        cls.offering = TenantServiceOffering.objects.create(
            tenant=cls.tenant,
            service_type=cls.service_type,
            flag=cls.flag,
            flag_relationship=cls.relationship,
            display_name="Alpha Flag Service",
            status=TenantServiceOffering.Status.ACTIVE,
            accepts_new_requests=True,
        )
        cls.template = OperationTemplate.objects.create(
            service_offering=cls.offering,
            name="Published Admin Template",
            code="published-admin-template",
            is_default=True,
        )
        cls.published_version = OperationTemplateVersion.objects.create(
            operation_template=cls.template,
            version_number=1,
            created_by=cls.non_staff,
        )
        cls.published_checklist = ChecklistTemplate.objects.create(
            operation_template_version=cls.published_version,
            code="published-document",
            document_type=cls.document_type,
        )
        cls.published_step = WorkflowStepTemplate.objects.create(
            operation_template_version=cls.published_version,
            code="published-step",
            name="Published Step",
        )
        cls.published_prerequisite = WorkflowStepTemplate.objects.create(
            operation_template_version=cls.published_version,
            code="published-prerequisite",
            name="Published Prerequisite",
        )
        cls.published_version = publish_version(
            tenant=cls.tenant,
            version=cls.published_version,
            published_by=cls.non_staff,
        )

        cls.draft_template = OperationTemplate.objects.create(
            service_offering=cls.offering,
            name="Draft Admin Template",
            code="draft-admin-template",
        )
        cls.draft_version = OperationTemplateVersion.objects.create(
            operation_template=cls.draft_template,
            version_number=1,
            created_by=cls.non_staff,
        )
        cls.draft_step = WorkflowStepTemplate.objects.create(
            operation_template_version=cls.draft_version,
            code="draft-step",
            name="Draft Step",
        )

        cls.service_request = ServiceRequest.objects.create(
            tenant=cls.tenant,
            customer=cls.customer,
            vessel=cls.vessel,
            service_type=cls.service_type,
            flag=cls.flag,
            service_offering=cls.offering,
            operation_template_version=cls.published_version,
            created_by=cls.non_staff,
            reference_code="AL-ADMIN-0001",
        )
        cls.checklist_item = ChecklistItem.objects.create(
            service_request=cls.service_request,
            document_type=cls.document_type,
            source_template=cls.published_checklist,
        )
        cls.workflow_instance = WorkflowStepInstance.objects.create(
            service_request=cls.service_request,
            step_template=cls.published_step,
        )
        cls.activity = ActivityLog.objects.create(
            tenant=cls.tenant,
            service_request=cls.service_request,
            actor_type="system",
            verb="admin.fixture",
            entity_type="ServiceRequest",
            entity_id=str(cls.service_request.id),
        )


class AdminAccessTests(AdminFixtureMixin, TestCase):
    def test_admin_route_resolves_and_anonymous_is_redirected_to_login(self):
        match = resolve("/admin/")
        self.assertEqual(match.url_name, "index")

        response = self.client.get("/admin/")

        self.assertRedirects(
            response,
            "/admin/login/?next=/admin/",
            fetch_redirect_response=False,
        )

    def test_non_staff_user_cannot_enter_admin(self):
        self.client.force_login(self.non_staff)

        response = self.client.get("/admin/")

        self.assertRedirects(
            response,
            "/admin/login/?next=/admin/",
            fetch_redirect_response=False,
        )

    def test_superuser_can_authenticate_through_the_admin_login_form(self):
        response = self.client.post(
            reverse("admin:login"),
            {
                "username": self.superuser.username,
                "password": "test-platform-password",
                "next": reverse("admin:index"),
            },
        )

        self.assertRedirects(
            response,
            reverse("admin:index"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            str(self.client.session["_auth_user_id"]),
            str(self.superuser.pk),
        )

    def test_staff_model_permissions_remain_enforced(self):
        permission = Permission.objects.get(
            content_type__app_label="customers",
            codename="view_customer",
        )
        self.staff.user_permissions.add(permission)
        self.client.force_login(self.staff)

        customer_response = self.client.get(
            reverse("admin:customers_customer_changelist"),
        )
        vessel_response = self.client.get(
            reverse("admin:vessels_vessel_changelist"),
        )

        self.assertEqual(customer_response.status_code, 200)
        self.assertEqual(vessel_response.status_code, 403)

    def test_superuser_can_open_critical_admin_pages_across_tenants(self):
        self.client.force_login(self.superuser)
        urls = (
            reverse("admin:index"),
            reverse("admin:users_user_changelist"),
            reverse("admin:tenants_tenant_changelist"),
            reverse("admin:catalog_tenantserviceoffering_changelist"),
            reverse("admin:workflow_operationtemplate_changelist"),
            reverse("admin:service_requests_servicerequest_changelist"),
            reverse("admin:activity_activitylog_changelist"),
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

        tenant_response = self.client.get(reverse("admin:tenants_tenant_changelist"))
        self.assertContains(tenant_response, self.tenant.name)
        self.assertContains(tenant_response, self.other_tenant.name)

    def test_critical_models_are_registered(self):
        expected_models = (
            get_user_model(),
            Tenant,
            Capability,
            TenantRole,
            RoleCapability,
            UserRoleAssignment,
            Customer,
            Vessel,
            Flag,
            ServiceType,
            TenantServiceOffering,
            OperationTemplate,
            OperationTemplateVersion,
            ChecklistTemplate,
            WorkflowStepTemplate,
            ServiceRequest,
            ChecklistItem,
            WorkflowStepInstance,
            ActivityLog,
        )

        for model in expected_models:
            with self.subTest(model=model.__name__):
                self.assertTrue(admin.site.is_registered(model))
        self.assertNotIn("delete_selected", admin.site.actions)

    def test_custom_user_admin_does_not_expose_password_hash_and_hashes_new_password(self):
        self.client.force_login(self.superuser)
        user_admin = admin.site.get_model_admin(get_user_model())
        self.assertNotIn("password", user_admin.get_list_display(None))
        self.assertNotIn("password", user_admin.search_fields)

        change_response = self.client.get(
            reverse("admin:users_user_change", args=[self.non_staff.pk]),
        )
        self.assertEqual(change_response.status_code, 200)
        self.assertNotContains(change_response, self.non_staff.password)

        add_response = self.client.post(
            reverse("admin:users_user_add"),
            {
                "username": "admin-created-user",
                "usable_password": "true",
                "password1": "admin-created-password",
                "password2": "admin-created-password",
                "tenant": self.tenant.pk,
                "role": get_user_model().Role.OPS,
            },
        )

        self.assertEqual(add_response.status_code, 302)
        user = get_user_model().objects.get(username="admin-created-user")
        self.assertNotEqual(user.password, "admin-created-password")
        self.assertTrue(user.check_password("admin-created-password"))

        password_change_response = self.client.post(
            reverse(
                "admin:auth_user_password_change",
                args=[self.non_staff.pk],
            ),
            {
                "password1": "changed-through-admin",
                "password2": "changed-through-admin",
            },
        )
        self.assertEqual(password_change_response.status_code, 302)
        self.non_staff.refresh_from_db()
        self.assertNotEqual(self.non_staff.password, "changed-through-admin")
        self.assertTrue(self.non_staff.check_password("changed-through-admin"))

    def test_new_draft_version_records_the_admin_actor_without_posted_attribution(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse("admin:workflow_operationtemplateversion_add"),
            {
                "operation_template": self.draft_template.pk,
                "version_number": 2,
                "checklist_templates-TOTAL_FORMS": 0,
                "checklist_templates-INITIAL_FORMS": 0,
                "checklist_templates-MIN_NUM_FORMS": 0,
                "checklist_templates-MAX_NUM_FORMS": 1000,
                "workflow_step_templates-TOTAL_FORMS": 0,
                "workflow_step_templates-INITIAL_FORMS": 0,
                "workflow_step_templates-MIN_NUM_FORMS": 0,
                "workflow_step_templates-MAX_NUM_FORMS": 1000,
            },
        )

        self.assertEqual(response.status_code, 302)
        version = OperationTemplateVersion.objects.get(
            operation_template=self.draft_template,
            version_number=2,
        )
        self.assertEqual(version.created_by_id, self.superuser.id)
        self.assertEqual(version.status, OperationTemplateVersion.Status.DRAFT)


class PublishedTemplateAdminTests(AdminFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.superuser)

    def test_published_parent_and_version_are_viewable_but_post_is_forbidden(self):
        cases = (
            (
                reverse("admin:workflow_operationtemplate_change", args=[self.template.pk]),
                {
                    "service_offering": self.offering.pk,
                    "name": "Tampered Parent",
                    "code": self.template.code,
                    "is_active": "on",
                    "is_default": "on",
                },
            ),
            (
                reverse(
                    "admin:workflow_operationtemplateversion_change",
                    args=[self.published_version.pk],
                ),
                {
                    "operation_template": self.template.pk,
                    "version_number": 99,
                    "created_by": self.non_staff.pk,
                },
            ),
        )

        for url, payload in cases:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
                self.assertEqual(self.client.post(url, payload).status_code, 403)

        self.template.refresh_from_db()
        self.published_version.refresh_from_db()
        self.assertEqual(self.template.name, "Published Admin Template")
        self.assertEqual(self.published_version.version_number, 1)

    def test_published_children_cannot_be_changed_deleted_or_added_by_post(self):
        checklist_change = reverse(
            "admin:checklists_checklisttemplate_change",
            args=[self.published_checklist.pk],
        )
        checklist_delete = reverse(
            "admin:checklists_checklisttemplate_delete",
            args=[self.published_checklist.pk],
        )
        workflow_change = reverse(
            "admin:workflow_workflowsteptemplate_change",
            args=[self.published_step.pk],
        )
        workflow_delete = reverse(
            "admin:workflow_workflowsteptemplate_delete",
            args=[self.published_step.pk],
        )

        self.assertEqual(self.client.post(checklist_change, {}).status_code, 403)
        self.assertEqual(self.client.get(checklist_delete).status_code, 403)
        self.assertEqual(self.client.post(workflow_change, {}).status_code, 403)
        self.assertEqual(self.client.get(workflow_delete).status_code, 403)

        checklist_count = ChecklistTemplate.objects.count()
        checklist_add = self.client.post(
            reverse("admin:checklists_checklisttemplate_add"),
            {
                "operation_template_version": self.published_version.pk,
                "code": "injected-checklist",
                "document_type": self.document_type.pk,
                "min_count": 1,
                "is_active": "on",
            },
        )
        self.assertEqual(checklist_add.status_code, 200)
        self.assertContains(
            checklist_add,
            "Only draft operation template definitions can be changed.",
        )
        self.assertEqual(ChecklistTemplate.objects.count(), checklist_count)

        workflow_count = WorkflowStepTemplate.objects.count()
        workflow_add = self.client.post(
            reverse("admin:workflow_workflowsteptemplate_add"),
            {
                "operation_template_version": self.published_version.pk,
                "code": "injected-step",
                "name": "Injected Step",
            },
        )
        self.assertEqual(workflow_add.status_code, 200)
        self.assertContains(
            workflow_add,
            "Only draft operation template definitions can be changed.",
        )
        self.assertEqual(WorkflowStepTemplate.objects.count(), workflow_count)

        dependency_add = self.client.post(
            reverse("admin:workflow_workflowstepdependency_add"),
            {
                "from_workflowsteptemplate": self.published_step.pk,
                "to_workflowsteptemplate": self.published_prerequisite.pk,
            },
        )
        self.assertEqual(dependency_add.status_code, 200)
        self.assertContains(
            dependency_add,
            "Published workflow dependencies are immutable.",
        )
        self.assertFalse(
            self.published_step.depends_on.filter(
                pk=self.published_prerequisite.pk,
            ).exists()
        )

    def test_draft_definition_remains_editable(self):
        response = self.client.post(
            reverse(
                "admin:workflow_workflowsteptemplate_change",
                args=[self.draft_step.pk],
            ),
            {
                "operation_template_version": self.draft_version.pk,
                "code": self.draft_step.code,
                "name": "Edited Draft Step",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.draft_step.refresh_from_db()
        self.assertEqual(self.draft_step.name, "Edited Draft Step")

    def test_published_version_delete_and_bulk_delete_are_unavailable(self):
        delete_response = self.client.get(
            reverse(
                "admin:workflow_operationtemplateversion_delete",
                args=[self.published_version.pk],
            ),
        )
        changelist = self.client.get(
            reverse("admin:workflow_operationtemplateversion_changelist"),
        )

        self.assertEqual(delete_response.status_code, 403)
        self.assertNotContains(changelist, 'value="delete_selected"')

    def test_retired_and_archived_versions_parents_and_children_are_locked(self):
        for target_status in (
            OperationTemplateVersion.Status.RETIRED,
            OperationTemplateVersion.Status.ARCHIVED,
        ):
            with self.subTest(status=target_status):
                template = OperationTemplate.objects.create(
                    service_offering=self.offering,
                    name=f"{target_status.title()} Template",
                    code=f"{target_status}-template",
                )
                version = OperationTemplateVersion.objects.create(
                    operation_template=template,
                    version_number=1,
                    created_by=self.non_staff,
                )
                step = WorkflowStepTemplate.objects.create(
                    operation_template_version=version,
                    code=f"{target_status}-step",
                    name=f"{target_status.title()} Step",
                )
                version = publish_version(
                    tenant=self.tenant,
                    version=version,
                    published_by=self.non_staff,
                )
                version = retire_version(tenant=self.tenant, version=version)
                if target_status == OperationTemplateVersion.Status.ARCHIVED:
                    version = archive_version(tenant=self.tenant, version=version)

                parent_url = reverse(
                    "admin:workflow_operationtemplate_change",
                    args=[template.pk],
                )
                version_url = reverse(
                    "admin:workflow_operationtemplateversion_change",
                    args=[version.pk],
                )
                step_url = reverse(
                    "admin:workflow_workflowsteptemplate_change",
                    args=[step.pk],
                )
                delete_url = reverse(
                    "admin:workflow_operationtemplateversion_delete",
                    args=[version.pk],
                )

                self.assertEqual(self.client.get(parent_url).status_code, 200)
                self.assertEqual(self.client.get(version_url).status_code, 200)
                self.assertEqual(self.client.get(step_url).status_code, 200)
                self.assertEqual(self.client.post(parent_url, {}).status_code, 403)
                self.assertEqual(self.client.post(version_url, {}).status_code, 403)
                self.assertEqual(self.client.post(step_url, {}).status_code, 403)
                self.assertEqual(self.client.get(delete_url).status_code, 403)
                version.refresh_from_db()
                self.assertEqual(version.status, target_status)

    def test_new_definitions_cannot_use_the_legacy_unversioned_path(self):
        checklist_count = ChecklistTemplate.objects.count()
        checklist_response = self.client.post(
            reverse("admin:checklists_checklisttemplate_add"),
            {
                "code": "unversioned-checklist",
                "document_type": self.document_type.pk,
                "min_count": 1,
                "is_active": "on",
            },
        )
        self.assertEqual(checklist_response.status_code, 200)
        self.assertContains(
            checklist_response,
            "New definitions must belong to a draft operation template version.",
        )
        self.assertEqual(ChecklistTemplate.objects.count(), checklist_count)

        workflow_count = WorkflowStepTemplate.objects.count()
        workflow_response = self.client.post(
            reverse("admin:workflow_workflowsteptemplate_add"),
            {
                "code": "unversioned-step",
                "name": "Unversioned Step",
            },
        )
        self.assertEqual(workflow_response.status_code, 200)
        self.assertContains(
            workflow_response,
            "New definitions must belong to a draft operation template version.",
        )
        self.assertEqual(WorkflowStepTemplate.objects.count(), workflow_count)


class TenantIntegrityAdminTests(AdminFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.superuser)

    def test_vessel_admin_rejects_cross_tenant_customer_and_accepts_same_tenant(self):
        add_url = reverse("admin:vessels_vessel_add")

        rejected = self.client.post(
            add_url,
            {
                "tenant": self.tenant.pk,
                "customer": self.other_customer.pk,
                "name": "Cross Tenant Vessel",
                "imo_number": "IMO-CROSS-TENANT",
            },
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertContains(
            rejected,
            "The vessel customer must belong to the vessel tenant.",
        )
        self.assertFalse(Vessel.objects.filter(imo_number="IMO-CROSS-TENANT").exists())

        accepted = self.client.post(
            add_url,
            {
                "tenant": self.tenant.pk,
                "customer": self.customer.pk,
                "name": "Same Tenant Vessel",
                "imo_number": "IMO-SAME-TENANT",
            },
        )
        self.assertEqual(accepted.status_code, 302)
        self.assertTrue(
            Vessel.objects.filter(
                tenant=self.tenant,
                customer=self.customer,
                imo_number="IMO-SAME-TENANT",
            ).exists()
        )

    def test_role_assignment_admin_rejects_cross_tenant_role(self):
        local_role = TenantRole.objects.create(tenant=self.tenant, name="Local Test Role")
        foreign_role = TenantRole.objects.create(
            tenant=self.other_tenant, name="Foreign Test Role",
        )
        add_url = reverse("admin:authorization_userroleassignment_add")

        rejected = self.client.post(
            add_url,
            {"user": self.non_staff.pk, "role": foreign_role.pk},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertContains(
            rejected,
            "The assigned role must belong to the user&#x27;s tenant.",
            html=True,
        )
        self.assertFalse(
            UserRoleAssignment.objects.filter(
                user=self.non_staff, role=foreign_role,
            ).exists()
        )

        accepted = self.client.post(
            add_url,
            {"user": self.non_staff.pk, "role": local_role.pk},
        )
        self.assertEqual(accepted.status_code, 302)
        self.assertTrue(
            UserRoleAssignment.objects.filter(
                user=self.non_staff, role=local_role,
            ).exists()
        )

    def test_offering_admin_rejects_cross_tenant_flag_relationship(self):
        response = self.client.post(
            reverse("admin:catalog_tenantserviceoffering_add"),
            {
                "tenant": self.tenant.pk,
                "service_type": self.service_type.pk,
                "flag": self.flag.pk,
                "flag_relationship": self.other_relationship.pk,
                "display_name": "Cross Tenant Offering",
                "status": TenantServiceOffering.Status.ACTIVE,
                "accepts_new_requests": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "The flag relationship must belong to the offering tenant.",
        )
        self.assertFalse(
            TenantServiceOffering.objects.filter(
                display_name="Cross Tenant Offering",
            ).exists()
        )

    def test_offering_admin_uses_domain_configuration_validation(self):
        response = self.client.post(
            reverse("admin:catalog_tenantserviceoffering_add"),
            {
                "tenant": self.tenant.pk,
                "service_type": self.service_type.pk,
                "display_name": "Invalid Required Flag Offering",
                "status": TenantServiceOffering.Status.ACTIVE,
                "accepts_new_requests": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This service requires a flag and an active relationship.",
        )
        self.assertFalse(
            TenantServiceOffering.objects.filter(
                display_name="Invalid Required Flag Offering",
            ).exists()
        )

    def test_protected_template_prevents_indirect_offering_identity_change(self):
        original_type = ServiceType.objects.create(
            name="Protected Admin Service",
            code="protected-admin-service",
            flag_scope=ServiceType.FlagScope.REQUIRED,
        )
        replacement_type = ServiceType.objects.create(
            name="Replacement Admin Service",
            code="replacement-admin-service",
            flag_scope=ServiceType.FlagScope.REQUIRED,
        )
        protected_offering = TenantServiceOffering.objects.create(
            tenant=self.tenant,
            service_type=original_type,
            flag=self.flag,
            flag_relationship=self.relationship,
            display_name="Protected Offering Without Requests",
            status=TenantServiceOffering.Status.ACTIVE,
            accepts_new_requests=True,
        )
        protected_template = OperationTemplate.objects.create(
            service_offering=protected_offering,
            name="Protected Offering Template",
            code="protected-offering-template",
        )
        protected_version = OperationTemplateVersion.objects.create(
            operation_template=protected_template,
            version_number=1,
            created_by=self.non_staff,
        )
        publish_version(
            tenant=self.tenant,
            version=protected_version,
            published_by=self.non_staff,
        )
        self.assertFalse(protected_offering.service_requests.exists())

        response = self.client.post(
            reverse(
                "admin:catalog_tenantserviceoffering_change",
                args=[protected_offering.pk],
            ),
            {
                "tenant": self.tenant.pk,
                "service_type": replacement_type.pk,
                "flag": self.flag.pk,
                "flag_relationship": self.relationship.pk,
                "display_name": protected_offering.display_name,
                "status": protected_offering.status,
                "accepts_new_requests": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "An offering referenced by service requests or protected template "
            "versions cannot change its identity.",
        )
        protected_offering.refresh_from_db()
        self.assertEqual(protected_offering.service_type_id, original_type.id)

        with self.assertRaisesMessage(
            catalog_services.OfferingValidationError,
            "An offering referenced by ServiceRequests or protected template "
            "versions cannot change its identity.",
        ):
            catalog_services.save_offering(
                tenant=self.tenant,
                instance=protected_offering,
                data={"service_type": replacement_type},
            )
        protected_offering.refresh_from_db()
        self.assertEqual(protected_offering.service_type_id, original_type.id)

    def test_flag_relationship_admin_rejects_cross_tenant_organization(self):
        relationship_count = TenantFlagRelationship.objects.count()
        response = self.client.post(
            reverse("admin:organizations_tenantflagrelationship_add"),
            {
                "tenant": self.tenant.pk,
                "flag": self.flag.pk,
                "relationship_type": TenantFlagRelationship.RelationshipType.PARTNER,
                "partner_organization": self.other_partner.pk,
                "status": TenantFlagRelationship.Status.INACTIVE,
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Organization does not belong to the acting tenant.",
        )
        self.assertEqual(TenantFlagRelationship.objects.count(), relationship_count)

    def test_existing_role_and_user_cannot_be_moved_across_tenants(self):
        role = TenantRole.objects.create(tenant=self.tenant, name="Assigned Role")
        UserRoleAssignment.objects.create(user=self.non_staff, role=role)

        user_response = self.client.post(
            reverse("admin:users_user_change", args=[self.non_staff.pk]),
            {
                "username": self.non_staff.username,
                "tenant": self.other_tenant.pk,
                "role": self.non_staff.role,
                "is_active": "on",
            },
        )
        self.assertEqual(user_response.status_code, 200)
        self.assertContains(
            user_response,
            "The user&#x27;s tenant must match every assigned tenant role.",
            html=True,
        )
        self.non_staff.refresh_from_db()
        self.assertEqual(self.non_staff.tenant_id, self.tenant.id)

        role_response = self.client.post(
            reverse("admin:authorization_tenantrole_change", args=[role.pk]),
            {
                "tenant": self.other_tenant.pk,
                "name": role.name,
                "description": "",
                "is_active": "on",
            },
        )
        self.assertEqual(role_response.status_code, 200)
        self.assertContains(
            role_response,
            "A role with user assignments cannot move to another tenant.",
        )
        role.refresh_from_db()
        self.assertEqual(role.tenant_id, self.tenant.id)

    def test_referenced_business_records_cannot_be_rehomed_to_another_tenant(self):
        customer_response = self.client.post(
            reverse("admin:customers_customer_change", args=[self.customer.pk]),
            {
                "tenant": self.other_tenant.pk,
                "name": self.customer.name,
                "contact_email": "",
                "contact_phone": "",
                "notes": "",
            },
        )
        self.assertEqual(customer_response.status_code, 200)
        self.assertContains(
            customer_response,
            "A customer with vessels or service requests cannot move tenants.",
        )

        vessel_response = self.client.post(
            reverse("admin:vessels_vessel_change", args=[self.vessel.pk]),
            {
                "tenant": self.other_tenant.pk,
                "customer": self.other_customer.pk,
                "name": self.vessel.name,
                "imo_number": self.vessel.imo_number,
                "vessel_type": "",
            },
        )
        self.assertEqual(vessel_response.status_code, 200)
        self.assertContains(
            vessel_response,
            "A vessel referenced by service requests cannot change tenant or customer.",
        )

        organization_response = self.client.post(
            reverse(
                "admin:organizations_organization_change",
                args=[self.partner.pk],
            ),
            {
                "tenant": self.other_tenant.pk,
                "organization_type": self.organization_type.pk,
                "name": self.partner.name,
                "contact_email": "",
                "contact_phone": "",
                "country": "",
            },
        )
        self.assertEqual(organization_response.status_code, 200)
        self.assertContains(
            organization_response,
            "A referenced organization cannot move to another tenant.",
        )

        self.customer.refresh_from_db()
        self.vessel.refresh_from_db()
        self.partner.refresh_from_db()
        self.assertEqual(self.customer.tenant_id, self.tenant.id)
        self.assertEqual(self.vessel.tenant_id, self.tenant.id)
        self.assertEqual(self.vessel.customer_id, self.customer.id)
        self.assertEqual(self.partner.tenant_id, self.tenant.id)

    def test_service_request_admin_has_no_add_or_cross_tenant_write_path(self):
        self.assertEqual(
            self.client.get(reverse("admin:service_requests_servicerequest_add")).status_code,
            403,
        )
        response = self.client.post(
            reverse(
                "admin:service_requests_servicerequest_change",
                args=[self.service_request.pk],
            ),
            {
                "tenant": self.other_tenant.pk,
                "customer": self.other_customer.pk,
                "status": ServiceRequest.Status.COMPLETED,
            },
        )
        self.assertEqual(response.status_code, 403)
        self.service_request.refresh_from_db()
        self.assertEqual(self.service_request.tenant_id, self.tenant.id)
        self.assertEqual(self.service_request.status, ServiceRequest.Status.DRAFT)


class ServiceRequestAdminTests(AdminFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.superuser)

    def test_detail_displays_read_only_checklist_and_workflow_inlines(self):
        response = self.client.get(
            reverse(
                "admin:service_requests_servicerequest_change",
                args=[self.service_request.pk],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.document_type.name)
        self.assertContains(response, self.published_step.name)
        self.assertContains(response, "checklist_items-group")
        self.assertContains(response, "workflow_steps-group")

    def test_instance_add_delete_and_status_bypass_are_forbidden(self):
        change_url = reverse(
            "admin:workflow_workflowstepinstance_change",
            args=[self.workflow_instance.pk],
        )
        self.assertEqual(self.client.get(change_url).status_code, 200)
        self.assertEqual(
            self.client.post(
                change_url,
                {
                    "service_request": self.service_request.pk,
                    "step_template": self.published_step.pk,
                    "status": WorkflowStepInstance.Status.COMPLETED,
                },
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("admin:workflow_workflowstepinstance_add")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "admin:workflow_workflowstepinstance_delete",
                    args=[self.workflow_instance.pk],
                ),
            ).status_code,
            403,
        )
        self.workflow_instance.refresh_from_db()
        self.assertEqual(
            self.workflow_instance.status,
            WorkflowStepInstance.Status.PENDING,
        )

        checklist_change = reverse(
            "admin:checklists_checklistitem_change",
            args=[self.checklist_item.pk],
        )
        self.assertEqual(
            self.client.post(
                checklist_change,
                {
                    "service_request": self.service_request.pk,
                    "document_type": self.document_type.pk,
                    "required_count": 1,
                    "is_complete": "on",
                },
            ).status_code,
            403,
        )
        self.checklist_item.refresh_from_db()
        self.assertFalse(self.checklist_item.is_complete)
