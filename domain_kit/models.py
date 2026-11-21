from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models

MODULE_CHOICES = [
    ("master_data", "Stammdaten (Kategorien, Einheiten, Status, Rollen)"),
    ("persons", "Personen & Rollen"),
    ("addresses", "Adressen & Standorte"),
    ("assets", "Assets (Hauptseite)"),
    ("contracts", "Assets: Verträge"),
    ("inventory", "Assets: Inventar"),
    ("accounts", "Assets: Konten"),
    ("documents", "Dokumente & Dateiablage"),
    ("global_search", "Globale Suche"),
]

ACCESS_CHOICES = [
    ("none", "Ausgeblendet"),
    ("read", "Nur Lesen"),
    ("write", "Lesen & Schreiben"),
]

PURPOSE_CHOICES = [
    ("person", "Person / Rolle"),
    ("address", "Adresse / Standort"),
    ("asset", "Asset (Allgemein)"),
    ("contract", "Vertrag"),
    ("inventory", "Inventar"),
    ("account", "Konto"),
    ("document", "Dokument"),
    ("list", "Listen & Vorlagen"),
    ("general", "Allgemein"),
]


class DomainModuleSettings(models.Model):
    enable_master_data = models.BooleanField(default=True)
    enable_persons = models.BooleanField(default=True)
    enable_addresses = models.BooleanField(default=True)
    enable_assets = models.BooleanField(default=True)
    enable_contracts = models.BooleanField(default=True)
    enable_inventory = models.BooleanField(default=True)
    enable_accounts = models.BooleanField(default=True)
    enable_documents = models.BooleanField(default=True)
    enable_global_search = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def is_module_enabled(self, module_key: str) -> bool:
        field_name = f"enable_{module_key}"
        return bool(getattr(self, field_name, True))

    def apply_profile(self, profile: str):
        p = str(profile or "all").lower().strip()
        if p == "persons":
            self.enable_persons = True
            self.enable_addresses = True
            self.enable_global_search = True
            self.enable_assets = False
            self.enable_contracts = False
            self.enable_inventory = False
            self.enable_accounts = False
            self.enable_documents = False
            self.enable_master_data = False
        elif p == "documents":
            self.enable_documents = True
            self.enable_global_search = True
            self.enable_persons = False
            self.enable_addresses = False
            self.enable_assets = False
            self.enable_contracts = False
            self.enable_inventory = False
            self.enable_accounts = False
            self.enable_master_data = False
        elif p == "assets":
            self.enable_assets = True
            self.enable_inventory = True
            self.enable_contracts = True
            self.enable_global_search = True
            self.enable_persons = False
            self.enable_addresses = False
            self.enable_documents = False
            self.enable_accounts = False
            self.enable_master_data = False
        elif p == "master_data":
            self.enable_master_data = True
            self.enable_persons = False
            self.enable_addresses = False
            self.enable_assets = False
            self.enable_contracts = False
            self.enable_inventory = False
            self.enable_accounts = False
            self.enable_documents = False
            self.enable_global_search = False
        elif "," in p or any(k in p for k in ("master_data", "persons", "documents", "assets", "global_search")):
            mods = [x.strip() for x in p.split(",")]
            self.enable_master_data = "master_data" in mods
            self.enable_persons = "persons" in mods
            self.enable_addresses = "persons" in mods or "addresses" in mods
            self.enable_documents = "documents" in mods
            self.enable_assets = "assets" in mods
            self.enable_inventory = "assets" in mods or "inventory" in mods
            self.enable_contracts = "assets" in mods or "contracts" in mods
            self.enable_accounts = "assets" in mods or "accounts" in mods
            self.enable_global_search = "global_search" in mods
        else:  # "all"
            self.enable_master_data = True
            self.enable_persons = True
            self.enable_addresses = True
            self.enable_assets = True
            self.enable_contracts = True
            self.enable_inventory = True
            self.enable_accounts = True
            self.enable_documents = True
            self.enable_global_search = True
        self.save()
        return self


class DomainGroupPermission(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="domain_kit_permissions")
    module_key = models.CharField(max_length=32, choices=MODULE_CHOICES, db_index=True)
    access_level = models.CharField(max_length=16, choices=ACCESS_CHOICES, default="read")

    class Meta:
        unique_together = [("group", "module_key")]
        ordering = ["group__name", "module_key"]

    def __str__(self):
        return f"{self.group.name} -> {self.module_key}: {self.access_level}"


class Category(models.Model):
    name = models.CharField(max_length=100)
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES, default="general", db_index=True)
    code = models.CharField(max_length=40, blank=True, default="")
    value = models.CharField(max_length=80, blank=True, default="")
    color_state = models.PositiveSmallIntegerField(default=1)
    custom_color = models.CharField(max_length=16, blank=True, default="")
    icon = models.CharField(max_length=64, blank=True, default="bi-tag")
    position = models.PositiveIntegerField(default=10, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["purpose", "position", "name"]

    @classmethod
    def for_purpose(cls, *purposes: str):
        return cls.objects.filter(is_active=True, purpose__in=purposes).order_by("position", "name")

    @property
    def badge_style(self) -> str:
        if self.custom_color:
            return f"background: {self.custom_color};"
        return f"background: var(--theme-state-{self.color_state}, var(--app-primary));"

    def __str__(self):
        return f"{self.name} ({self.purpose})"


class Unit(models.Model):
    DIMENSION_CHOICES = [
        ("count", "Anzahl / Stück"),
        ("currency", "Währung"),
        ("length", "Länge"),
        ("time", "Zeit"),
        ("volume", "Volumen"),
        ("area", "Fläche"),
        ("weight", "Gewicht"),
        ("other", "Sonstiges"),
    ]
    name = models.CharField(max_length=60)
    symbol = models.CharField(max_length=20)
    dimension = models.CharField(max_length=24, choices=DIMENSION_CHOICES, default="count")
    decimals = models.PositiveSmallIntegerField(default=2)
    position = models.PositiveIntegerField(default=10, db_index=True)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class Status(models.Model):
    name = models.CharField(max_length=60)
    scope = models.CharField(max_length=32, default="global", db_index=True)
    color_state = models.PositiveSmallIntegerField(default=1)
    custom_color = models.CharField(max_length=16, blank=True, default="")
    icon = models.CharField(max_length=64, blank=True, default="bi-circle-fill")
    position = models.PositiveIntegerField(default=10, db_index=True)
    is_final = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "id"]

    @classmethod
    def for_scope(cls, *scopes: str):
        check = list(scopes) + ["global"]
        return cls.objects.filter(scope__in=check).order_by("position", "id")

    @property
    def badge_style(self) -> str:
        if self.custom_color:
            return f"background: {self.custom_color};"
        return f"background: var(--theme-state-{self.color_state}, var(--app-primary));"

    def __str__(self):
        return f"{self.position}: {self.name}"


class Role(models.Model):
    name = models.CharField(max_length=80, unique=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="roles")
    color_state = models.PositiveSmallIntegerField(default=1)
    custom_color = models.CharField(max_length=16, blank=True, default="")
    position = models.PositiveIntegerField(default=10, db_index=True)
    description = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["position", "name"]

    @property
    def badge_style(self) -> str:
        if self.custom_color:
            return f"background: {self.custom_color};"
        return f"background: var(--theme-state-{self.color_state}, var(--app-primary));"

    def __str__(self):
        return self.name


class Person(models.Model):
    salutation = models.CharField(max_length=30, blank=True, default="")
    title_prefix = models.CharField(max_length=40, blank=True, default="")
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True, default="")
    display_name = models.CharField(max_length=140, blank=True, default="")
    email = models.CharField(max_length=140, blank=True, default="")
    phone = models.CharField(max_length=60, blank=True, default="")
    mobile = models.CharField(max_length=60, blank=True, default="")
    company = models.CharField(max_length=120, blank=True, default="")
    department = models.CharField(max_length=100, blank=True, default="")
    job_title = models.CharField(max_length=100, blank=True, default="")
    birth_date = models.DateField(null=True, blank=True)
    website = models.URLField(blank=True, default="")
    tax_id = models.CharField(max_length=60, blank=True, default="")
    photo = models.FileField(upload_to="domain_kit/persons/%Y/%m/", blank=True, null=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="persons")
    status = models.ForeignKey(Status, null=True, blank=True, on_delete=models.SET_NULL, related_name="persons")
    roles = models.ManyToManyField(Role, blank=True, related_name="persons")
    responsible_person = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="subordinates",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="domain_kit_persons",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["last_name", "first_name", "id"]

    @property
    def full_name(self) -> str:
        if self.display_name:
            return self.display_name
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.full_name


class Address(models.Model):
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=80, default="Hauptadresse")
    street = models.CharField(max_length=140)
    address_addition = models.CharField(max_length=140, blank=True, default="")
    postal_code = models.CharField(max_length=24, blank=True, default="")
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80, blank=True, default="")
    country = models.CharField(max_length=60, default="Deutschland")
    phone = models.CharField(max_length=60, blank=True, default="")
    email = models.CharField(max_length=140, blank=True, default="")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="addresses")
    is_primary = models.BooleanField(default=True)
    notes = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["-is_primary", "city", "street"]

    def __str__(self):
        return f"{self.label}: {self.street}, {self.postal_code} {self.city}".strip()


class AssetItem(models.Model):
    ASSET_TYPES = [
        ("contract", "Vertrag"),
        ("inventory", "Inventar"),
        ("account", "Konto"),
    ]
    asset_type = models.CharField(max_length=24, choices=ASSET_TYPES, default="inventory", db_index=True)
    title = models.CharField(max_length=140)
    identifier = models.CharField(max_length=80, blank=True, default="")
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    status = models.ForeignKey(Status, null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    address = models.ForeignKey(Address, null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    billing_interval = models.CharField(max_length=32, blank=True, default="")
    serial_number = models.CharField(max_length=80, blank=True, default="")
    institution = models.CharField(max_length=120, blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["asset_type", "title"]

    def __str__(self):
        return f"[{self.asset_type}] {self.title}"


class Document(models.Model):
    TOPIC_CHOICES = [
        ("person", "Personen & Adressen"),
        ("asset", "Assets (Allgemein)"),
        ("contract", "Verträge"),
        ("inventory", "Inventar"),
        ("account", "Konten"),
        ("general", "Allgemein"),
    ]
    title = models.CharField(max_length=160)
    file = models.FileField(upload_to="domain_kit/documents/%Y/%m/", blank=True, null=True)
    file_name = models.CharField(max_length=180, blank=True, default="")
    file_url = models.CharField(max_length=255, blank=True, default="")
    topic = models.CharField(max_length=24, choices=TOPIC_CHOICES, default="general", db_index=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    status = models.ForeignKey(Status, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    document_date = models.DateField(null=True, blank=True)
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    asset = models.ForeignKey(AssetItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    tags = models.CharField(max_length=160, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    extracted_text = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-document_date", "-created_at", "id"]

    def __str__(self):
        return f"{self.title} ({self.topic})"
