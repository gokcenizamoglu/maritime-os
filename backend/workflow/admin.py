from django import forms
from django.contrib import admin

from checklists.models import ChecklistTemplate
from config.admin_utils import NoBulkDeleteMixin, ReadOnlyModelAdmin, concrete_field_names
from workflow.models import (
    PROTECTED_VERSION_STATUSES,
    OperationTemplate,
    OperationTemplateVersion,
    WorkflowStepDependency,
    WorkflowStepInstance,
    WorkflowStepTemplate,
)


class OperationTemplateForm(forms.ModelForm):
    class Meta:
        model = OperationTemplate
        fields = "__all__"

    def clean_service_offering(self):
        offering = self.cleaned_data["service_offering"]
        if (
            self.instance.pk
            and self.instance.service_offering_id != offering.id
            and self.instance.versions.exists()
        ):
            raise forms.ValidationError(
                "A template with versions cannot move to another service offering."
            )
        return offering


class OperationTemplateVersionForm(forms.ModelForm):
    class Meta:
        model = OperationTemplateVersion
        fields = "__all__"

    def clean_operation_template(self):
        template = self.cleaned_data["operation_template"]
        if self.instance.pk:
            original = OperationTemplateVersion.objects.get(pk=self.instance.pk)
            if original.operation_template_id != template.id:
                raise forms.ValidationError("A draft version cannot move between templates.")
        return template


class DraftDefinitionForm(forms.ModelForm):
    def clean_operation_template_version(self):
        version = self.cleaned_data.get("operation_template_version")
        if version is None and not self.instance.pk:
            raise forms.ValidationError(
                "New definitions must belong to a draft operation template version."
            )
        if version and version.status != OperationTemplateVersion.Status.DRAFT:
            raise forms.ValidationError(
                "Only draft operation template definitions can be changed."
            )
        if self.instance.pk:
            original = type(self.instance).objects.get(pk=self.instance.pk)
            if original.operation_template_version_id != getattr(version, "id", None):
                raise forms.ValidationError(
                    "A definition cannot move between operation template versions."
                )
        return version


class ChecklistTemplateForm(DraftDefinitionForm):
    class Meta:
        model = ChecklistTemplate
        fields = "__all__"


class WorkflowStepTemplateForm(DraftDefinitionForm):
    class Meta:
        model = WorkflowStepTemplate
        fields = "__all__"


class WorkflowStepDependencyForm(forms.ModelForm):
    class Meta:
        model = WorkflowStepDependency
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("from_workflowsteptemplate")
        target = cleaned.get("to_workflowsteptemplate")
        if not source or not target:
            return cleaned
        if source.id == target.id:
            raise forms.ValidationError("A workflow step cannot depend on itself.")
        if source.operation_template_version_id != target.operation_template_version_id:
            raise forms.ValidationError(
                "Workflow dependencies must stay within one operation template version."
            )
        version = source.operation_template_version
        if version and version.status != OperationTemplateVersion.Status.DRAFT:
            raise forms.ValidationError("Published workflow dependencies are immutable.")
        return cleaned


class PublishedLockAdminMixin(NoBulkDeleteMixin):
    def is_locked(self, obj):
        raise NotImplementedError

    def has_change_permission(self, request, obj=None):
        if obj is not None and self.is_locked(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and self.is_locked(obj):
            return False
        return super().has_delete_permission(request, obj)


class DraftVersionInlineMixin:
    extra = 0

    @staticmethod
    def _is_locked(version):
        return version is not None and version.status != OperationTemplateVersion.Status.DRAFT

    def get_readonly_fields(self, request, obj=None):
        if self._is_locked(obj):
            return concrete_field_names(self.model)
        return super().get_readonly_fields(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj is None or self._is_locked(obj):
            return False
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if self._is_locked(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if self._is_locked(obj):
            return False
        return super().has_delete_permission(request, obj)


class ChecklistTemplateInline(DraftVersionInlineMixin, admin.TabularInline):
    model = ChecklistTemplate
    form = ChecklistTemplateForm
    fields = ("code", "document_type", "min_count", "is_active")
    raw_id_fields = ("document_type",)


class WorkflowStepTemplateInline(DraftVersionInlineMixin, admin.TabularInline):
    model = WorkflowStepTemplate
    form = WorkflowStepTemplateForm
    fields = ("code", "name", "is_external", "responsible_organization_type")
    raw_id_fields = ("responsible_organization_type",)


@admin.register(OperationTemplate)
class OperationTemplateAdmin(PublishedLockAdminMixin, admin.ModelAdmin):
    form = OperationTemplateForm
    list_display = (
        "name", "code", "tenant", "service_offering", "is_active", "is_default",
        "published_version",
    )
    list_filter = (
        "service_offering__tenant", "is_active", "is_default",
        "service_offering__service_type", "service_offering__flag",
    )
    search_fields = (
        "name", "code", "description", "service_offering__display_name",
        "service_offering__tenant__name",
    )
    ordering = ("service_offering__tenant__name", "name")
    raw_id_fields = ("service_offering",)
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("service_offering", "service_offering__tenant")
    date_hierarchy = "created_at"

    def is_locked(self, obj):
        return obj.versions.filter(status__in=PROTECTED_VERSION_STATUSES).exists()

    @admin.display(ordering="service_offering__tenant", description="Tenant")
    def tenant(self, obj):
        return obj.service_offering.tenant

    @admin.display(description="Published version")
    def published_version(self, obj):
        return obj.versions.filter(
            status=OperationTemplateVersion.Status.PUBLISHED,
        ).values_list("version_number", flat=True).first()


@admin.register(OperationTemplateVersion)
class OperationTemplateVersionAdmin(PublishedLockAdminMixin, admin.ModelAdmin):
    form = OperationTemplateVersionForm
    inlines = (ChecklistTemplateInline, WorkflowStepTemplateInline)
    list_display = (
        "operation_template", "tenant", "version_number", "status",
        "published_at", "created_by",
    )
    list_filter = ("status", "operation_template__service_offering__tenant")
    search_fields = (
        "operation_template__name", "operation_template__code",
        "operation_template__service_offering__tenant__name",
    )
    ordering = (
        "operation_template__service_offering__tenant__name",
        "operation_template__name", "-version_number",
    )
    raw_id_fields = ("operation_template",)
    readonly_fields = (
        "status", "published_at", "created_by", "published_by", "created_at", "updated_at",
    )
    list_select_related = (
        "operation_template", "operation_template__service_offering",
        "operation_template__service_offering__tenant", "created_by", "published_by",
    )

    def is_locked(self, obj):
        return obj.status in PROTECTED_VERSION_STATUSES

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(
        ordering="operation_template__service_offering__tenant",
        description="Tenant",
    )
    def tenant(self, obj):
        return obj.operation_template.service_offering.tenant


class VersionedDefinitionAdmin(PublishedLockAdminMixin, admin.ModelAdmin):
    def is_locked(self, obj):
        return (
            obj.operation_template_version_id is not None
            and obj.operation_template_version.status
            != OperationTemplateVersion.Status.DRAFT
        )


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(VersionedDefinitionAdmin):
    form = ChecklistTemplateForm
    list_display = (
        "code", "document_type", "tenant", "operation_template_version",
        "min_count", "is_active",
    )
    list_filter = (
        "operation_template_version__operation_template__service_offering__tenant",
        "is_active", "document_type",
    )
    search_fields = (
        "code", "document_type__name", "operation_template_version__operation_template__name",
    )
    raw_id_fields = (
        "operation_template_version", "service_type", "flag", "document_type",
    )
    list_select_related = (
        "operation_template_version",
        "operation_template_version__operation_template",
        "operation_template_version__operation_template__service_offering",
        "document_type",
    )

    @admin.display(description="Tenant")
    def tenant(self, obj):
        if obj.operation_template_version_id:
            return obj.operation_template_version.operation_template.service_offering.tenant
        return None


@admin.register(WorkflowStepTemplate)
class WorkflowStepTemplateAdmin(VersionedDefinitionAdmin):
    form = WorkflowStepTemplateForm
    list_display = (
        "code", "name", "tenant", "operation_template_version", "is_external",
    )
    list_filter = (
        "operation_template_version__operation_template__service_offering__tenant",
        "is_external", "responsible_organization_type",
    )
    search_fields = (
        "code", "name", "operation_template_version__operation_template__name",
    )
    raw_id_fields = (
        "operation_template_version", "service_type", "flag",
        "responsible_organization_type",
    )
    list_select_related = (
        "operation_template_version",
        "operation_template_version__operation_template",
        "operation_template_version__operation_template__service_offering",
        "responsible_organization_type",
    )

    @admin.display(description="Tenant")
    def tenant(self, obj):
        if obj.operation_template_version_id:
            return obj.operation_template_version.operation_template.service_offering.tenant
        return None


@admin.register(WorkflowStepDependency)
class WorkflowStepDependencyAdmin(NoBulkDeleteMixin, admin.ModelAdmin):
    form = WorkflowStepDependencyForm
    list_display = ("from_workflowsteptemplate", "to_workflowsteptemplate", "tenant")
    search_fields = (
        "from_workflowsteptemplate__name", "to_workflowsteptemplate__name",
    )
    raw_id_fields = ("from_workflowsteptemplate", "to_workflowsteptemplate")
    list_select_related = (
        "from_workflowsteptemplate__operation_template_version__operation_template__service_offering",
        "to_workflowsteptemplate",
    )

    def _is_locked(self, obj):
        version = obj.from_workflowsteptemplate.operation_template_version
        return version is not None and version.status != OperationTemplateVersion.Status.DRAFT

    def has_change_permission(self, request, obj=None):
        if obj is not None and self._is_locked(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and self._is_locked(obj):
            return False
        return super().has_delete_permission(request, obj)

    @admin.display(description="Tenant")
    def tenant(self, obj):
        version = obj.from_workflowsteptemplate.operation_template_version
        if version:
            return version.operation_template.service_offering.tenant
        return None


@admin.register(WorkflowStepInstance)
class WorkflowStepInstanceAdmin(ReadOnlyModelAdmin):
    list_display = (
        "service_request", "step_template", "status", "assigned_organization",
        "started_at", "completed_at",
    )
    list_filter = ("service_request__tenant", "status")
    search_fields = (
        "service_request__reference_code", "step_template__name",
        "assigned_organization__name",
    )
    ordering = ("service_request__reference_code", "step_template__name")
    raw_id_fields = ("service_request", "step_template", "assigned_organization")
    list_select_related = (
        "service_request", "service_request__tenant", "step_template",
        "assigned_organization",
    )
