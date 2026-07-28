"""Service-layer rules for tenant service offerings."""

from django.db import transaction

from catalog.models import TenantServiceOffering


class OfferingValidationError(ValueError):
    pass


def validate_offering_configuration(
    *, tenant, service_type, flag=None, flag_relationship=None,
    status=None, valid_from=None, valid_until=None,
) -> None:
    if flag_relationship is not None:
        if flag_relationship.tenant_id != tenant.id:
            raise OfferingValidationError("Flag relationship does not belong to the acting tenant.")
        if flag is None or flag_relationship.flag_id != flag.id:
            raise OfferingValidationError("Offering flag must match its flag relationship.")

    has_flag = flag is not None
    has_relationship = flag_relationship is not None
    scope = service_type.flag_scope
    if scope == service_type.FlagScope.REQUIRED and not (has_flag and has_relationship):
        raise OfferingValidationError("This service requires a flag and an active relationship.")
    if scope == service_type.FlagScope.NOT_APPLICABLE and (has_flag or has_relationship):
        raise OfferingValidationError("This service cannot be associated with a flag.")
    if scope == service_type.FlagScope.OPTIONAL and has_flag != has_relationship:
        raise OfferingValidationError(
            "Optional flag services need both a flag and relationship, or neither."
        )
    if valid_from and valid_until and valid_until < valid_from:
        raise OfferingValidationError("valid_until cannot be earlier than valid_from.")
    if status == TenantServiceOffering.Status.ACTIVE:
        if flag is not None and not flag.is_active:
            raise OfferingValidationError("An active offering cannot use an inactive flag.")
        if flag_relationship is not None and not flag_relationship.is_available_for_new_requests():
            raise OfferingValidationError("An active offering needs an active, valid flag relationship.")


@transaction.atomic
def save_offering(*, tenant, data, instance=None) -> TenantServiceOffering:
    service_type = data.get("service_type", instance.service_type if instance else None)
    flag = data.get("flag", instance.flag if instance else None)
    relationship = data.get(
        "flag_relationship", instance.flag_relationship if instance else None,
    )
    validate_offering_configuration(
        tenant=tenant,
        service_type=service_type,
        flag=flag,
        flag_relationship=relationship,
        status=data.get("status", instance.status if instance else None),
        valid_from=data.get("valid_from", instance.valid_from if instance else None),
        valid_until=data.get("valid_until", instance.valid_until if instance else None),
    )
    if instance is None:
        if not data.get("display_name"):
            data["display_name"] = service_type.name
        return TenantServiceOffering.objects.create(tenant=tenant, **data)
    if instance.tenant_id != tenant.id:
        raise OfferingValidationError("Offering does not belong to the acting tenant.")
    identity_fields = {"service_type", "flag", "flag_relationship"}
    if any(key in data for key in identity_fields) and instance.service_requests.exists():
        if any(
            key in data and getattr(instance, f"{key}_id") != getattr(data[key], "id", data[key])
            for key in identity_fields
        ):
            raise OfferingValidationError(
                "An offering referenced by ServiceRequests cannot change its identity."
            )
    for key, value in data.items():
        setattr(instance, key, value)
    instance.save()
    return instance
