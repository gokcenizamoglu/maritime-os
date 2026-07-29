from django.contrib import admin


if "delete_selected" in admin.site.actions:
    admin.site.disable_action("delete_selected")


def concrete_field_names(model):
    return tuple(field.name for field in model._meta.fields if not field.primary_key)


class NoBulkDeleteMixin:
    """Keep object-aware delete rules from being bypassed by a bulk action."""

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


class ReadOnlyModelAdmin(NoBulkDeleteMixin, admin.ModelAdmin):
    """A detail view for operational records that must change via services."""

    def get_readonly_fields(self, request, obj=None):
        return concrete_field_names(self.model)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyTabularInline(admin.TabularInline):
    extra = 0
    can_delete = False
    show_change_link = True

    def get_readonly_fields(self, request, obj=None):
        return concrete_field_names(self.model)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
