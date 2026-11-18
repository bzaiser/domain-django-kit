from django.contrib.auth.models import Group

from .models import (
    MODULE_CHOICES,
    Address,
    AssetItem,
    Category,
    Document,
    DomainGroupPermission,
    DomainModuleSettings,
    Person,
    Role,
    Status,
    Unit,
)

LEVEL_RANK = {"none": 0, "read": 1, "write": 2}
ALL_MODULES = [k for k, _ in MODULE_CHOICES]


def get_module_access(user, module_key: str) -> str:
    solo = DomainModuleSettings.get_solo()
    if not solo.is_module_enabled(module_key):
        return "none"
    if not user or not getattr(user, "is_authenticated", False):
        return "none"
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return "write"

    group_ids = list(user.groups.values_list("id", flat=True))
    if not group_ids:
        # If no group rules exist in DB at all yet, allow write for authenticated users
        if not DomainGroupPermission.objects.exists():
            return "write"
        return "read"

    perms = list(
        DomainGroupPermission.objects.filter(group_id__in=group_ids, module_key=module_key).values_list(
            "access_level", flat=True
        )
    )
    if not perms:
        return "none"
    best = max(perms, key=lambda lvl: LEVEL_RANK.get(lvl, 0))
    return best


def get_user_module_map(user) -> dict:
    result = {}
    for key in ALL_MODULES:
        lvl = get_module_access(user, key)
        result[key] = {
            "level": lvl,
            "can_read": LEVEL_RANK.get(lvl, 0) >= 1,
            "can_write": LEVEL_RANK.get(lvl, 0) >= 2,
        }
    return result


def seed_domain_defaults() -> dict:
    DomainModuleSettings.get_solo()

    # 1. Units
    default_units = [
        ("Stück", "Stk.", "count", 0, 10),
        ("Euro", "€", "currency", 2, 20),
        ("Stunden", "Std.", "time", 2, 30),
        ("Meter", "m", "length", 2, 40),
        ("Quadratmeter", "m²", "area", 2, 50),
        ("Liter", "l", "volume", 2, 60),
        ("Kilogramm", "kg", "weight", 2, 70),
        ("Prozent", "%", "other", 1, 80),
        ("Pauschal", "psch.", "other", 0, 90),
    ]
    for name, sym, dim, dec, pos in default_units:
        Unit.objects.get_or_create(symbol=sym, defaults={"name": name, "dimension": dim, "decimals": dec, "position": pos})

    # 2. Status (ordered by position, NOT alphabetically)
    default_statuses = [
        ("Offen", "global", 1, "bi-circle", 10, False),
        ("Begonnen", "global", 2, "bi-play-circle", 20, False),
        ("In Prüfung", "global", 3, "bi-hourglass-split", 30, False),
        ("Erledigt", "global", 4, "bi-check-circle", 40, True),
        ("Fertig", "global", 4, "bi-check2-all", 50, True),
        ("Verspätet", "global", 5, "bi-clock-history", 60, False),
        ("Fehler", "global", 6, "bi-exclamation-octagon", 70, False),
        ("Zu groß", "global", 7, "bi-arrows-angle-expand", 80, False),
        ("Zu klein", "global", 8, "bi-arrows-angle-contract", 90, False),
        ("Archiviert", "global", 1, "bi-archive", 100, True),
    ]
    for name, scope, color, icon, pos, is_final in default_statuses:
        Status.objects.get_or_create(
            name=name,
            scope=scope,
            defaults={"color_state": color, "icon": icon, "position": pos, "is_final": is_final},
        )

    # 3. Categories by purpose
    default_categories = [
        ("Mitarbeiter", "person", "EMP", "1.0", 1, "bi-person-badge", 10),
        ("Gast", "person", "GUEST", "0.0", 2, "bi-person", 20),
        ("Personalverantwortlicher", "person", "HR", "2.0", 3, "bi-person-gear", 30),
        ("Dienstleister", "person", "VENDOR", "1.0", 4, "bi-briefcase", 40),
        ("Hauptadresse", "address", "MAIN", "", 1, "bi-house", 10),
        ("Standort / Büro", "address", "SITE", "", 2, "bi-building", 20),
        ("Lager", "address", "WAREHOUSE", "", 3, "bi-boxes", 30),
        ("Mietvertrag", "contract", "RENT", "monthly", 1, "bi-house-door", 10),
        ("Wartung & Support", "contract", "MAINT", "yearly", 2, "bi-tools", 20),
        ("Software-Lizenz", "contract", "LIC", "monthly", 3, "bi-key", 30),
        ("Versicherung", "contract", "INS", "yearly", 4, "bi-shield-check", 40),
        ("IT & Server", "inventory", "IT", "", 1, "bi-hdd-stack", 10),
        ("Werkzeug & Geräte", "inventory", "TOOL", "", 2, "bi-wrench-adjustable", 20),
        ("Möbel & Ausstattung", "inventory", "FURN", "", 3, "bi-lamp", 30),
        ("Fuhrpark", "inventory", "CAR", "", 4, "bi-car-front", 40),
        ("Girokonto", "account", "GIRO", "EUR", 1, "bi-bank", 10),
        ("Tagesgeld / Rücklagen", "account", "SAVE", "EUR", 2, "bi-piggy-bank", 20),
        ("Depot / Investment", "account", "DEPOT", "EUR", 3, "bi-graph-up-arrow", 30),
        ("Rechnung", "document", "INV", "", 1, "bi-receipt", 10),
        ("Vertragsdokument", "document", "DOC_CON", "", 2, "bi-file-earmark-text", 20),
        ("Nachweis / Beleg", "document", "PROOF", "", 3, "bi-file-earmark-check", 30),
    ]
    cat_map = {}
    for name, purpose, code, val, color, icon, pos in default_categories:
        cat, _ = Category.objects.get_or_create(
            name=name,
            purpose=purpose,
            defaults={"code": code, "value": val, "color_state": color, "icon": icon, "position": pos},
        )
        cat_map[(purpose, name)] = cat

    # 4. Roles
    default_roles = [
        ("Mitarbeiter", cat_map.get(("person", "Mitarbeiter")), 1, 10, "Interne Mitarbeitende"),
        ("Gast", cat_map.get(("person", "Gast")), 2, 20, "Externe Gäste mit eingeschränktem Zugriff"),
        ("Personalverantwortlicher", cat_map.get(("person", "Personalverantwortlicher")), 3, 30, "HR & Personalleitung"),
        ("Ansprechpartner", cat_map.get(("person", "Dienstleister")), 4, 40, "Externer Kontakt"),
        ("Eigentümer", None, 5, 50, "Asset- oder Kontoeigentümer"),
    ]
    for name, cat, color, pos, desc in default_roles:
        Role.objects.get_or_create(
            name=name,
            defaults={"category": cat, "color_state": color, "position": pos, "description": desc},
        )

    # 5. Default Permission Groups (Gast, Mitarbeiter, Personalverantwortlicher)
    group_matrices = {
        "Gast": {
            "master_data": "none",
            "persons": "read",
            "addresses": "read",
            "assets": "read",
            "contracts": "none",
            "inventory": "read",
            "accounts": "none",
            "documents": "read",
            "global_search": "read",
        },
        "Mitarbeiter": {
            "master_data": "read",
            "persons": "read",
            "addresses": "write",
            "assets": "write",
            "contracts": "read",
            "inventory": "write",
            "accounts": "none",
            "documents": "write",
            "global_search": "read",
        },
        "Personalverantwortlicher": {
            m: "write" for m in ALL_MODULES
        },
    }
    for grp_name, rules in group_matrices.items():
        grp, _ = Group.objects.get_or_create(name=grp_name)
        for mod_key, level in rules.items():
            DomainGroupPermission.objects.get_or_create(
                group=grp,
                module_key=mod_key,
                defaults={"access_level": level},
            )

    return {
        "units": Unit.objects.count(),
        "statuses": Status.objects.count(),
        "categories": Category.objects.count(),
        "roles": Role.objects.count(),
        "groups": len(group_matrices),
    }


def count_module_data(module_key: str) -> int:
    if module_key == "persons":
        return Person.objects.count()
    if module_key == "addresses":
        return Address.objects.count()
    if module_key == "contracts":
        return AssetItem.objects.filter(asset_type="contract").count()
    if module_key == "inventory":
        return AssetItem.objects.filter(asset_type="inventory").count()
    if module_key == "accounts":
        return AssetItem.objects.filter(asset_type="account").count()
    if module_key == "assets":
        return AssetItem.objects.count()
    if module_key == "documents":
        return Document.objects.count()
    if module_key == "master_data":
        return Category.objects.count() + Unit.objects.count() + Status.objects.count() + Role.objects.count()
    return 0


def purge_module_data(module_key: str) -> int:
    if module_key == "persons":
        cnt, _ = Person.objects.all().delete()
        return cnt
    if module_key == "addresses":
        cnt, _ = Address.objects.all().delete()
        return cnt
    if module_key == "contracts":
        cnt, _ = AssetItem.objects.filter(asset_type="contract").delete()
        return cnt
    if module_key == "inventory":
        cnt, _ = AssetItem.objects.filter(asset_type="inventory").delete()
        return cnt
    if module_key == "accounts":
        cnt, _ = AssetItem.objects.filter(asset_type="account").delete()
        return cnt
    if module_key == "assets":
        cnt, _ = AssetItem.objects.all().delete()
        return cnt
    if module_key == "documents":
        cnt, _ = Document.objects.all().delete()
        return cnt
    if module_key == "master_data":
        c1, _ = Category.objects.all().delete()
        c2, _ = Unit.objects.all().delete()
        c3, _ = Status.objects.all().delete()
        c4, _ = Role.objects.all().delete()
        return c1 + c2 + c3 + c4
    return 0
