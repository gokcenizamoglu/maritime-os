from django.db.models.signals import post_save
from django.dispatch import receiver

from tenants.models import Tenant


@receiver(post_save, sender=Tenant)
def provision_roles_for_new_tenant(sender, instance, created, raw, **kwargs):
    if created and not raw:
        from authorization.services import provision_default_roles

        provision_default_roles(instance)
