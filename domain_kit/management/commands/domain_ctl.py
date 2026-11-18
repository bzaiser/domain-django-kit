from django.core.management.base import BaseCommand

from domain_kit.services import purge_module_data, seed_domain_defaults


class Command(BaseCommand):
    help = "Steuert domain-django-kit: Standard-Stammdaten & Gruppen laden oder Moduldaten bereinigen."

    def add_arguments(self, parser):
        parser.add_argument("--seed-defaults", action="store_true", help="Lädt Standard-Einheiten, Status, Kategorien, Rollen & Gruppen.")
        parser.add_argument("--purge", help="Löscht alle Daten eines Moduls (persons, addresses, contracts, inventory, accounts, assets, documents, master_data).")

    def handle(self, *args, **options):
        if options.get("seed_defaults"):
            stats = seed_domain_defaults()
            self.stdout.write(self.style.SUCCESS(f"Standarddaten geladen: {stats}"))
        if options.get("purge"):
            deleted = purge_module_data(options["purge"])
            self.stdout.write(self.style.WARNING(f"Modul '{options['purge']}' bereinigt ({deleted} Einträge gelöscht)."))
