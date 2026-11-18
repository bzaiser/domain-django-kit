import os
import sys

import django
from django.conf import settings
from django.core.management import call_command
from django.test import Client, TestCase

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS_DIR = os.path.join(os.path.dirname(BASE_DIR), "django-design-studio")
for p in (BASE_DIR, DS_DIR):
    if p not in sys.path and os.path.isdir(p):
        sys.path.insert(0, p)

if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY="test-domain-kit",
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            "django.contrib.messages",
            "django.contrib.staticfiles",
            "design_studio",
            "domain_kit",
        ],
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
        ],
        ROOT_URLCONF="tests.test_domain_kit",
        TEMPLATES=[{
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "APP_DIRS": True,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                    "design_studio.context_processors.theme_context",
                    "domain_kit.context_processors.domain_context",
                ],
            },
        }],
        STATIC_URL="/static/",
    )
    django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import include, path
from domain_kit.models import AssetItem, Category, Document, DomainModuleSettings, Person, Status, Unit
from domain_kit.services import get_module_access, purge_module_data, seed_domain_defaults

User = get_user_model()

urlpatterns = [
    path("design-studio/", include("design_studio.urls")),
    path("domain/", include("domain_kit.urls")),
]


class DomainKitTests(TestCase):
    def setUp(self):
        seed_domain_defaults()
        self.admin = User.objects.create_user(username="hr_admin", password="pw", is_staff=True)
        self.guest = User.objects.create_user(username="guest_u", password="pw")
        self.guest.groups.add(Group.objects.get(name="Gast"))
        self.emp = User.objects.create_user(username="emp_u", password="pw")
        self.emp.groups.add(Group.objects.get(name="Mitarbeiter"))
        self.client = Client()

    def test_master_data_status_position_ordering_and_purpose_filtering(self):
        statuses = list(Status.objects.values_list("name", flat=True))
        # Must follow position (Offen=10, Begonnen=20, ..., Zu klein=90, Archiviert=100), not alphabetical
        self.assertEqual(statuses[0], "Offen")
        self.assertEqual(statuses[1], "Begonnen")
        self.assertIn("Zu groß", statuses)
        self.assertIn("Zu klein", statuses)

        person_cats = list(Category.for_purpose("person").values_list("name", flat=True))
        self.assertIn("Mitarbeiter", person_cats)
        self.assertIn("Gast", person_cats)
        self.assertIn("Personalverantwortlicher", person_cats)
        self.assertNotIn("Girokonto", person_cats)

        symbols = list(Unit.objects.values_list("symbol", flat=True))
        for sym in ("Stk.", "€", "m", "Std.", "l", "m²"):
            self.assertIn(sym, symbols)

    def test_group_permission_matrix_and_module_toggle_and_purge(self):
        self.assertEqual(get_module_access(self.guest, "persons"), "read")
        self.assertEqual(get_module_access(self.guest, "accounts"), "none")
        self.assertEqual(get_module_access(self.emp, "inventory"), "write")
        self.assertEqual(get_module_access(self.emp, "persons"), "read")

        # Guest cannot POST to persons
        self.client.force_login(self.guest)
        forbidden = self.client.post("/domain/persons/", {"action": "create_person", "first_name": "Nope"})
        self.assertEqual(forbidden.status_code, 403)

        # Guest with assets=read, inventory=read, contracts=none, accounts=none
        AssetItem.objects.create(asset_type="account", title="Geheimes Konto", quantity="9999.00")
        AssetItem.objects.create(asset_type="inventory", title="Öffentlicher Drucker", quantity="200.00")
        ov_html = self.client.get("/domain/assets/?tab=overview").content.decode("utf-8")
        self.assertIn("Öffentlicher Drucker", ov_html)
        self.assertNotIn("Geheimes Konto", ov_html)
        self.assertEqual(self.client.get("/domain/assets/?tab=account").status_code, 403)

        # Disable persons globally
        solo = DomainModuleSettings.get_solo()
        solo.enable_persons = False
        solo.save()
        self.assertEqual(get_module_access(self.admin, "persons"), "none")

    def test_persons_assets_documents_and_global_search_pages(self):
        self.client.force_login(self.admin)

        # 1. Create Person + Address
        self.client.post(
            "/domain/persons/",
            {"action": "create_person", "first_name": "Max", "last_name": "Muster", "company": "NAS GmbH"},
        )
        p = Person.objects.get(first_name="Max")
        self.client.post(
            "/domain/persons/",
            {"action": "create_address", "person_id": p.id, "label": "Büro", "street": "Hauptstr. 1", "city": "Berlin"},
        )
        self.assertEqual(self.client.get("/domain/persons/?tab=persons").status_code, 200)
        self.assertEqual(self.client.get("/domain/persons/?tab=addresses").status_code, 200)

        # 2. Create Contract, Inventory, Account & Document
        eur = Unit.objects.get(symbol="€")
        for atype, title, val in (
            ("contract", "Glasfaser Vertrag", "59.90"),
            ("inventory", "Synology NAS DS923+", "650.00"),
            ("account", "Geschäftskonto", "12500.00"),
        ):
            self.client.post(
                "/domain/assets/",
                {
                    "action": "create_asset",
                    "asset_type": atype,
                    "title": title,
                    "quantity": val,
                    "unit_id": eur.id,
                    "person_id": p.id,
                },
            )
        self.assertEqual(AssetItem.objects.count(), 3)
        self.assertEqual(self.client.get("/domain/assets/?tab=overview").status_code, 200)
        self.assertEqual(self.client.get("/domain/assets/?tab=contract").status_code, 200)
        self.assertEqual(self.client.get("/domain/assets/?tab=inventory").status_code, 200)
        self.assertEqual(self.client.get("/domain/assets/?tab=account").status_code, 200)

        # 3. Document & Global Search
        self.client.post(
            "/domain/documents/",
            {"action": "create_doc", "title": "Rechnung Synology", "topic": "inventory", "amount": "650.00", "unit_id": eur.id},
        )
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(self.client.get("/domain/documents/").status_code, 200)

        search_resp = self.client.get("/domain/search/?q=Synology")
        self.assertEqual(search_resp.status_code, 200)
        html = search_resp.content.decode("utf-8")
        self.assertIn("Synology NAS DS923+", html)
        self.assertIn("Rechnung Synology", html)

        # 4. Purge inventory
        purge_module_data("inventory")
        self.assertEqual(AssetItem.objects.filter(asset_type="inventory").count(), 0)
        self.assertEqual(AssetItem.objects.filter(asset_type="contract").count(), 1)

    def test_initial_django_groups_custom_group_and_color_picker(self):
        from domain_kit.models import Role

        for gname in ("Gast", "Mitarbeiter", "Personalverantwortlicher"):
            self.assertTrue(Group.objects.filter(name=gname).exists())

        self.client.force_login(self.admin)
        self.client.post("/domain/settings/", {"action": "create_group", "group_name": "Buchhaltung"})
        self.assertTrue(Group.objects.filter(name="Buchhaltung").exists())

        settings_html = self.client.get("/domain/settings/?tab=modules").content.decode("utf-8")
        self.assertIn("Gruppe: Buchhaltung", settings_html)
        self.assertIn("ds-tabs", settings_html)
        self.assertIn("ds-tab-panel", settings_html)

        self.client.post(
            "/domain/settings/",
            {
                "action": "create_category",
                "name": "Sonderkategorie",
                "purpose": "general",
                "color_state": "3",
                "use_custom_color": "on",
                "custom_color": "#FF5500",
            },
        )
        cat = Category.objects.get(name="Sonderkategorie")
        self.assertEqual(cat.custom_color, "#FF5500")
        self.assertEqual(cat.badge_style, "background: #FF5500;")

        self.client.post(
            "/domain/settings/",
            {"action": "create_role", "name": "Projektleiter", "color_state": "8"},
        )
        role = Role.objects.get(name="Projektleiter")
        self.assertEqual(role.badge_style, "background: var(--theme-state-8, var(--app-primary));")

        # Non-superuser staff cannot purge; superuser needs explicit confirmation
        forbidden_purge = self.client.post("/domain/settings/", {"action": "purge_module", "module_key": "categories"})
        self.assertEqual(forbidden_purge.status_code, 403)
        super_u = User.objects.create_superuser(username="root_adm", password="pw", email="r@example.com")
        self.client.force_login(super_u)
        self.client.post("/domain/settings/", {"action": "purge_module", "module_key": "master_data"})
        self.assertTrue(Category.objects.filter(name="Sonderkategorie").exists())
        self.client.post(
            "/domain/settings/",
            {"action": "purge_module", "module_key": "master_data", "confirm_purge": "master_data"},
        )
        self.assertFalse(Category.objects.filter(name="Sonderkategorie").exists())

    def test_document_real_file_upload_ajax_and_download(self):
        import tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile

        with tempfile.TemporaryDirectory() as media_tmp:
            with self.settings(MEDIA_ROOT=media_tmp):
                self.client.force_login(self.admin)
                f = SimpleUploadedFile("vertrag.pdf", b"%PDF-1.4 test content", content_type="application/pdf")
                resp = self.client.post(
                    "/domain/documents/",
                    {"action": "create_doc", "title": "", "topic": "contract", "file": f},
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                )
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertEqual(data["status"], "ok")
                self.assertEqual(data["title"], "vertrag.pdf")
                self.assertEqual(data["file_name"], "vertrag.pdf")

                dl = self.client.get(f"/domain/documents/{data['id']}/download/")
                self.assertEqual(dl.status_code, 200)
                self.assertEqual(b"".join(dl.streaming_content), b"%PDF-1.4 test content")

    def test_docx_and_txt_fulltext_extraction_and_global_search(self):
        import io
        import tempfile
        import zipfile
        from django.core.files.uploadedfile import SimpleUploadedFile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>GeheimerWartungsCode99</w:t></w:r></w:p></w:body></w:document>',
            )

        with tempfile.TemporaryDirectory() as media_tmp:
            with self.settings(MEDIA_ROOT=media_tmp):
                self.client.force_login(self.admin)
                docx_file = SimpleUploadedFile("protokoll.docx", buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                resp = self.client.post(
                    "/domain/documents/",
                    {"action": "create_doc", "title": "Wartungsprotokoll", "topic": "general", "file": docx_file},
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                )
                self.assertEqual(resp.status_code, 200)
                doc = Document.objects.get(pk=resp.json()["id"])
                self.assertIn("GeheimerWartungsCode99", doc.extracted_text)

                search_html = self.client.get("/domain/search/?q=GeheimerWartungsCode99").content.decode("utf-8")
                self.assertIn("Wartungsprotokoll", search_html)


if __name__ == "__main__":
    from django.test.runner import DiscoverRunner
    call_command("migrate", verbosity=0)
    runner = DiscoverRunner(verbosity=2)
    sys.exit(bool(runner.run_tests(["tests.test_domain_kit"])))
