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
        DomainModuleSettings.get_solo().apply_profile("all")
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

    def test_multi_upload_inline_view_person_photo_and_address_edit(self):
        import tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        from domain_kit.models import Address
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            with self.settings(MEDIA_ROOT=tmpdir):
                f1 = SimpleUploadedFile("eins.txt", b"Erste Datei", content_type="text/plain")
                f2 = SimpleUploadedFile("zwei.txt", b"Zweite Datei", content_type="text/plain")
                resp = self.client.post(
                    "/domain/documents/",
                    {"action": "create_doc", "topic": "general", "file": [f1, f2]},
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                )
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["count"], 2)
                doc_id = resp.json()["ids"][0]
                view_resp = self.client.get(f"/domain/documents/{doc_id}/view/")
                self.assertEqual(view_resp.status_code, 200)
                self.assertIn("inline", view_resp.get("Content-Disposition", ""))
                self.assertEqual(view_resp.get("X-Frame-Options"), "SAMEORIGIN")
                view_resp.close()

                csv_file = SimpleUploadedFile("tabelle.csv", b"Name;Wert\nTest;42\n", content_type="text/csv")
                r_csv = self.client.post(
                    "/domain/documents/",
                    {"action": "create_doc", "topic": "general", "file": csv_file},
                    HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                )
                prev_resp = self.client.get(f"/domain/documents/{r_csv.json()['id']}/preview/")
                self.assertEqual(prev_resp.status_code, 200)
                self.assertIn("<table", prev_resp.json()["html"])
                self.assertIn("42", prev_resp.json()["html"])

                photo = SimpleUploadedFile("avatar.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
                self.client.post(
                    "/domain/persons/",
                    {
                        "action": "create_person",
                        "salutation": "Frau",
                        "title_prefix": "Dr.",
                        "first_name": "Erika",
                        "last_name": "Muster",
                        "job_title": "Leitung",
                        "photo": photo,
                    },
                )
                p = Person.objects.get(first_name="Erika")
                self.assertEqual(p.title_prefix, "Dr.")
                photo_resp = self.client.get(f"/domain/persons/{p.id}/photo/")
                self.assertEqual(photo_resp.status_code, 200)
                photo_resp.close()

                self.client.post(
                    "/domain/persons/",
                    {
                        "action": "create_address",
                        "person_id": str(p.id),
                        "label": "Büro",
                        "street": "Hauptstr. 1",
                        "city": "Berlin",
                    },
                )
                addr = Address.objects.get(person=p)
                self.client.post(
                    "/domain/persons/",
                    {
                        "action": "update_address",
                        "pk": str(addr.id),
                        "person_id": str(p.id),
                        "label": "Büro",
                        "street": "Hauptstr. 1",
                        "address_addition": "2. OG",
                        "city": "Berlin",
                        "state": "Berlin",
                        "phone": "030-1234",
                    },
                )
                addr.refresh_from_db()
                self.assertEqual(addr.address_addition, "2. OG")
                self.assertEqual(addr.phone, "030-1234")

    def test_modular_profiles_and_view_redirects(self):
        self.client.force_login(self.admin)
        solo = DomainModuleSettings.get_solo()

        # Apply profile 'documents'
        solo.apply_profile("documents")
        self.assertTrue(solo.enable_documents)
        self.assertTrue(solo.enable_global_search)
        self.assertFalse(solo.enable_persons)
        self.assertFalse(solo.enable_assets)

        # Accessing disabled persons view redirects
        resp = self.client.get("/domain/persons/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/domain/settings/", resp.headers.get("Location", ""))

        # Apply profile via POST in settings view
        post_resp = self.client.post("/domain/settings/", {"action": "save_modules", "apply_profile": "persons"})
        self.assertEqual(post_resp.status_code, 302)
        solo.refresh_from_db()
        self.assertTrue(solo.enable_persons)
        self.assertFalse(solo.enable_assets)
        self.assertFalse(solo.enable_documents)

        # Persons is now accessible (200), assets redirects (302)
        self.assertEqual(self.client.get("/domain/persons/").status_code, 200)
        self.assertEqual(self.client.get("/domain/assets/").status_code, 302)


    def test_global_search_renders_master_data_addresses_custom_provider_and_scope_filter(self):
        from domain_kit.models import Address
        from domain_kit.search_engine import _extract_snippet

        self.client.force_login(self.admin)
        p = Person.objects.create(first_name="Clara", last_name="Test")
        Address.objects.create(person=p, label="Privat", street="Lindenallee 42", postal_code="70173", city="Stuttgart")

        # 1. Master data category & address MUST render in HTML (previously dropped!)
        r_cat = self.client.get("/domain/search/?q=Mitarbeiter")
        self.assertEqual(r_cat.status_code, 200)
        html_cat = r_cat.content.decode("utf-8")
        self.assertIn("Stammdaten", html_cat)
        self.assertIn("Mitarbeiter", html_cat)

        r_addr = self.client.get("/domain/search/?q=Lindenallee")
        self.assertEqual(r_addr.status_code, 200)
        self.assertIn("Lindenallee 42", r_addr.content.decode("utf-8"))

        # 2. Custom provider via DOMAIN_SEARCH_PROVIDERS & scope filter
        def fake_app_provider(req, q):
            hits = []
            if q and "hafer" in q.lower():
                hits.append({
                    "title": "Haferflocken mit Beeren",
                    "subtitle": "380 kcal",
                    "snippet": "Frühstück-Vorlage",
                    "badge": "Mahlzeit",
                    "url": "/meals/",
                    "url_label": "Zu Mahlzeiten",
                })
            return [{"key": "app_meals", "label": "Mahlzeiten", "icon": "bi-egg-fried", "hits": hits}]

        from unittest.mock import patch
        with self.settings(DOMAIN_SEARCH_PROVIDERS=["tests.test_domain_kit.fake_provider"]), \
             patch("domain_kit.search_engine.import_string", return_value=fake_app_provider):
            r_prov = self.client.get("/domain/search/?q=Hafer&scope=app_meals")
            self.assertEqual(r_prov.status_code, 200)
            body = r_prov.content.decode("utf-8")
            self.assertIn("Haferflocken mit Beeren", body)
            self.assertIn("Mahlzeiten", body)

        # 3. Authenticated user in unrelated group (not explicitly blocked) can still access Global Search
        other_grp = Group.objects.create(name="Benutzer")
        plain_user = User.objects.create_user(username="plain_u", password="pw")
        plain_user.groups.add(other_grp)
        self.client.force_login(plain_user)
        r_plain = self.client.get("/domain/search/?q=Test")
        self.assertEqual(r_plain.status_code, 200)

        self.assertIn("Treffer", _extract_snippet("Das ist ein langer Treffer Text zum Prüfen", "Treffer"))

    def test_member_self_service_editorial_and_auto_group_rows(self):
        from domain_kit.models import Address, DomainGroupPermission, Person
        from domain_kit.services import ensure_group_permission_rows, has_editorial_access

        # 1. Seeded groups include Redakteur, Mitglied / Portal, Buchhaltung / Kassierer, Leitung / Vorstand
        red_grp = Group.objects.get(name="Redakteur")
        mem_grp = Group.objects.get(name="Mitglied / Portal")
        self.assertEqual(DomainGroupPermission.objects.get(group=red_grp, module_key="documents").access_level, "write")
        self.assertEqual(DomainGroupPermission.objects.get(group=red_grp, module_key="master_data").access_level, "none")
        self.assertEqual(DomainGroupPermission.objects.get(group=mem_grp, module_key="persons").access_level, "none")

        # 2. Manual group gets 'none' initialized automatically
        custom_grp = Group.objects.create(name="Testgruppe")
        ensure_group_permission_rows()
        self.assertEqual(DomainGroupPermission.objects.get(group=custom_grp, module_key="persons").access_level, "none")

        # 3. Redakteur has editorial access without is_staff
        red_user = User.objects.create_user(username="redakteur_u", password="pw", is_staff=False)
        red_user.groups.add(red_grp)
        self.assertTrue(has_editorial_access(red_user))

        # 4. Member self-service (/domain/me/)
        mem_user = User.objects.create_user(username="mitglied_u", password="pw", is_staff=False)
        mem_user.groups.add(mem_grp)
        other_person = Person.objects.create(first_name="Fremd", last_name="Person")
        other_addr = Address.objects.create(person=other_person, label="Fremd", street="Fremdstr. 1", city="Berlin")
        own_person = Person.objects.create(first_name="Max", last_name="Mitglied", user=mem_user, email="alt@example.com")

        self.client.force_login(mem_user)
        self.assertEqual(self.client.get("/domain/persons/").status_code, 403)
        r_me = self.client.get("/domain/me/")
        self.assertEqual(r_me.status_code, 200)
        self.assertContains(r_me, "Max Mitglied")

        self.client.post("/domain/me/", {"action": "save_contact", "email": "neu@example.com", "phone": "01234", "mobile": "0170"})
        own_person.refresh_from_db()
        self.assertEqual(own_person.email, "neu@example.com")
        self.assertEqual(own_person.phone, "01234")

        self.client.post("/domain/me/", {"action": "create_address", "label": "Privat", "street": "Hauptstr. 5", "postal_code": "12345", "city": "Ulm", "country": "Deutschland"})
        self.assertTrue(own_person.addresses.filter(street="Hauptstr. 5").exists())

        # Cannot delete another person's address
        self.client.post("/domain/me/", {"action": "delete_address", "pk": other_addr.id})
        self.assertTrue(Address.objects.filter(pk=other_addr.id).exists())

    def test_no_missing_migrations(self):
        call_command("makemigrations", "domain_kit", "--check", "--dry-run", verbosity=0)

    def test_document_edit_valid_until_and_status_scope(self):
        from datetime import timedelta
        from django.utils import timezone
        from domain_kit.models import Category, Document, DomainModuleSettings, Status

        solo = DomainModuleSettings.get_solo()
        solo.enable_documents = True
        solo.save()
        self.client.force_login(self.admin)

        st = Status.objects.create(name="Geprüft", scope="document", position=15)
        cat = Category.objects.create(name="Bescheid", purpose="document")
        soon = (timezone.localdate() + timedelta(days=10)).isoformat()

        r_create = self.client.post("/domain/documents/", {
            "action": "create_doc",
            "title": "Zuwendungsbescheid",
            "topic": "general",
            "category_id": str(cat.id),
            "status_id": str(st.id),
            "valid_until": soon,
            "tags": "2026, wichtig",
            "notes": "Erstnotiz",
        })
        self.assertEqual(r_create.status_code, 302)
        doc = Document.objects.get(title="Zuwendungsbescheid")
        self.assertEqual(doc.category_id, cat.id)
        self.assertEqual(doc.status_id, st.id)
        self.assertTrue(doc.expires_soon)
        self.assertFalse(doc.is_expired)

        r_get = self.client.get("/domain/documents/")
        self.assertContains(r_get, "Läuft bald ab")
        self.assertContains(r_get, f'id="docEditModal-{doc.id}"')
        self.assertContains(r_get, cat.badge_style)

        r_flt = self.client.get(f"/domain/documents/?category={cat.id}&status={st.id}")
        self.assertContains(r_flt, "Zuwendungsbescheid")
        r_flt_empty = self.client.get("/domain/documents/?category=999999")
        self.assertNotContains(r_flt_empty, "Zuwendungsbescheid")

        r_st = self.client.get("/domain/settings/?tab=statuses&scope=document")
        self.assertContains(r_st, "Geprüft")

        r_edit = self.client.post("/domain/documents/", {
            "action": "update_doc",
            "pk": str(doc.id),
            "title": "Zuwendungsbescheid Neu",
            "topic": "contract",
            "category_id": str(cat.id),
            "status_id": str(st.id),
            "valid_until": (timezone.localdate() - timedelta(days=1)).isoformat(),
            "notes": "Aktualisiert",
        })
        self.assertEqual(r_edit.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.title, "Zuwendungsbescheid Neu")
        self.assertEqual(doc.topic, "contract")
        self.assertTrue(doc.is_expired)


if __name__ == "__main__":
    from django.test.runner import DiscoverRunner
    call_command("migrate", verbosity=0)
    runner = DiscoverRunner(verbosity=2)
    sys.exit(bool(runner.run_tests(["tests.test_domain_kit"])))
