from authorization.services import sync_capabilities
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Synchronize Capability database rows from the code registry."

    def handle(self, *args, **options):
        result = sync_capabilities()
        self.stdout.write(
            f"Capabilities synced: {result['created']} created, "
            f"{result['updated']} updated, {result['deactivated']} deactivated."
        )
