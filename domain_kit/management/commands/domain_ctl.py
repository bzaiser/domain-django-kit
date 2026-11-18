from django.core.management.base import BaseCommand

from domain_kit.extractors import extract_text_from_file
from domain_kit.models import Document
from domain_kit.services import purge_module_data, seed_domain_defaults


class Command(BaseCommand):
    help = "Steuert domain-django-kit: Standard-Stammdaten & Gruppen laden, Dokumente re-indizieren oder Moduldaten bereinigen."

    def add_arguments(self, parser):
        parser.add_argument("--seed-defaults", action="store_true", help="Lädt Standard-Einheiten, Status, Kategorien, Rollen & Gruppen.")
        parser.add_argument("--reindex-docs", action="store_true", help="Extrahiert Text aus vorhandenen Dokumenten neu für die Globale Suche.")
        parser.add_argument("--purge", help="Löscht alle Daten eines Moduls (persons, addresses, contracts, inventory, accounts, assets, documents, master_data).")

    def handle(self, *args, **options):
        if options.get("seed_defaults"):
            stats = seed_domain_defaults()
            self.stdout.write(self.style.SUCCESS(f"Standarddaten geladen: {stats}"))
        if options.get("reindex_docs"):
            updated = 0
            for doc in Document.objects.exclude(file="").iterator():
                try:
                    with doc.file.open("rb") as fh:
                        doc.extracted_text = extract_text_from_file(fh, doc.file_name or doc.file.name)
                        doc.save(update_fields=["extracted_text"])
                        updated += 1
                except Exception:
                    continue
            self.stdout.write(self.style.SUCCESS(f"{updated} Dokument(e) neu indiziert."))
        if options.get("purge"):
            deleted = purge_module_data(options["purge"])
            self.stdout.write(self.style.WARNING(f"Modul '{options['purge']}' bereinigt ({deleted} Einträge gelöscht)."))
