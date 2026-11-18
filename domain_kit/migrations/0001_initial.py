from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DomainModuleSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enable_master_data", models.BooleanField(default=True)),
                ("enable_persons", models.BooleanField(default=True)),
                ("enable_addresses", models.BooleanField(default=True)),
                ("enable_assets", models.BooleanField(default=True)),
                ("enable_contracts", models.BooleanField(default=True)),
                ("enable_inventory", models.BooleanField(default=True)),
                ("enable_accounts", models.BooleanField(default=True)),
                ("enable_documents", models.BooleanField(default=True)),
                ("enable_global_search", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("purpose", models.CharField(db_index=True, default="general", max_length=32)),
                ("code", models.CharField(blank=True, default="", max_length=40)),
                ("value", models.CharField(blank=True, default="", max_length=80)),
                ("color_state", models.PositiveSmallIntegerField(default=1)),
                ("custom_color", models.CharField(blank=True, default="", max_length=16)),
                ("icon", models.CharField(blank=True, default="bi-tag", max_length=64)),
                ("position", models.PositiveIntegerField(db_index=True, default=10)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["purpose", "position", "name"]},
        ),
        migrations.CreateModel(
            name="Unit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60)),
                ("symbol", models.CharField(max_length=20)),
                ("dimension", models.CharField(default="count", max_length=24)),
                ("decimals", models.PositiveSmallIntegerField(default=2)),
                ("position", models.PositiveIntegerField(db_index=True, default=10)),
            ],
            options={"ordering": ["position", "name"]},
        ),
        migrations.CreateModel(
            name="Status",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60)),
                ("scope", models.CharField(db_index=True, default="global", max_length=32)),
                ("color_state", models.PositiveSmallIntegerField(default=1)),
                ("icon", models.CharField(blank=True, default="bi-circle-fill", max_length=64)),
                ("position", models.PositiveIntegerField(db_index=True, default=10)),
                ("is_final", models.BooleanField(default=False)),
            ],
            options={"ordering": ["position", "id"]},
        ),
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                ("color_state", models.PositiveSmallIntegerField(default=1)),
                ("position", models.PositiveIntegerField(db_index=True, default=10)),
                ("description", models.CharField(blank=True, default="", max_length=200)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="roles",
                        to="domain_kit.category",
                    ),
                ),
            ],
            options={"ordering": ["position", "name"]},
        ),
        migrations.CreateModel(
            name="Person",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_name", models.CharField(max_length=80)),
                ("last_name", models.CharField(blank=True, default="", max_length=80)),
                ("display_name", models.CharField(blank=True, default="", max_length=140)),
                ("email", models.CharField(blank=True, default="", max_length=140)),
                ("phone", models.CharField(blank=True, default="", max_length=60)),
                ("mobile", models.CharField(blank=True, default="", max_length=60)),
                ("company", models.CharField(blank=True, default="", max_length=120)),
                ("department", models.CharField(blank=True, default="", max_length=100)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="persons",
                        to="domain_kit.category",
                    ),
                ),
                (
                    "responsible_person",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subordinates",
                        to="domain_kit.person",
                    ),
                ),
                (
                    "status",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="persons",
                        to="domain_kit.status",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="domain_kit_persons",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("roles", models.ManyToManyField(blank=True, related_name="persons", to="domain_kit.role")),
            ],
            options={"ordering": ["last_name", "first_name", "id"]},
        ),
        migrations.CreateModel(
            name="Address",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(default="Hauptadresse", max_length=80)),
                ("street", models.CharField(max_length=140)),
                ("postal_code", models.CharField(blank=True, default="", max_length=24)),
                ("city", models.CharField(max_length=80)),
                ("country", models.CharField(default="Deutschland", max_length=60)),
                ("is_primary", models.BooleanField(default=True)),
                ("notes", models.CharField(blank=True, default="", max_length=200)),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="addresses",
                        to="domain_kit.category",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="addresses",
                        to="domain_kit.person",
                    ),
                ),
            ],
            options={"ordering": ["-is_primary", "city", "street"]},
        ),
        migrations.CreateModel(
            name="AssetItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("asset_type", models.CharField(db_index=True, default="inventory", max_length=24)),
                ("title", models.CharField(max_length=140)),
                ("identifier", models.CharField(blank=True, default="", max_length=80)),
                ("quantity", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("billing_interval", models.CharField(blank=True, default="", max_length=32)),
                ("serial_number", models.CharField(blank=True, default="", max_length=80)),
                ("institution", models.CharField(blank=True, default="", max_length=120)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "address",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assets",
                        to="domain_kit.address",
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assets",
                        to="domain_kit.category",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assets",
                        to="domain_kit.person",
                    ),
                ),
                (
                    "status",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assets",
                        to="domain_kit.status",
                    ),
                ),
                (
                    "unit",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assets",
                        to="domain_kit.unit",
                    ),
                ),
            ],
            options={"ordering": ["asset_type", "title"]},
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=160)),
                ("file_name", models.CharField(blank=True, default="", max_length=180)),
                ("file_url", models.CharField(blank=True, default="", max_length=255)),
                ("topic", models.CharField(db_index=True, default="general", max_length=24)),
                ("amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                ("document_date", models.DateField(blank=True, null=True)),
                ("tags", models.CharField(blank=True, default="", max_length=160)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "asset",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="documents",
                        to="domain_kit.assetitem",
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="documents",
                        to="domain_kit.category",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="documents",
                        to="domain_kit.person",
                    ),
                ),
                (
                    "status",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="documents",
                        to="domain_kit.status",
                    ),
                ),
                (
                    "unit",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="documents",
                        to="domain_kit.unit",
                    ),
                ),
            ],
            options={"ordering": ["-document_date", "-created_at", "id"]},
        ),
        migrations.CreateModel(
            name="DomainGroupPermission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("module_key", models.CharField(db_index=True, max_length=32)),
                ("access_level", models.CharField(default="read", max_length=16)),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="domain_kit_permissions",
                        to="auth.group",
                    ),
                ),
            ],
            options={"ordering": ["group__name", "module_key"], "unique_together": {("group", "module_key")}},
        ),
    ]
