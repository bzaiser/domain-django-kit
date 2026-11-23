from seed_kit.registry import fake_email, fake_name, register_seeder

from .models import Address, AssetItem, Category, Person, Role
from .services import seed_domain_defaults


def seed_domain_demo(count: int = 5):
    seed_domain_defaults()
    created = 0

    # Public lecturer + board member
    dozent_role, _ = Role.objects.get_or_create(name="Dozent / Referent", defaults={"color_state": 2, "position": 25})
    vorstand_role, _ = Role.objects.get_or_create(name="Vorstand", defaults={"color_state": 1, "position": 15})

    doz, doz_new = Person.objects.get_or_create(
        first_name="Clara",
        last_name="Beispiel",
        defaults={
            "display_name": "Clara Beispiel",
            "job_title": "Kursleiterin & Referentin",
            "email": "clara.beispiel@example.com",
            "website": "https://example.com",
            "is_public": True,
            "bio": "Langjährige Dozentin für Praxis-Workshops.\n- Zertifizierte Trainerin\n- Über 50 geleitete Kurse",
        },
    )
    doz.roles.add(dozent_role)
    if doz_new:
        created += 1

    vorst, vorst_new = Person.objects.get_or_create(
        first_name="Bernd",
        last_name="Vorstand",
        defaults={
            "display_name": "Bernd Vorstand",
            "job_title": "1. Vorsitzender",
            "email": "vorstand@example.com",
            "is_public": True,
        },
    )
    vorst.roles.add(vorstand_role)
    if vorst_new:
        created += 1

    for i in range(max(0, count - 2)):
        full = fake_name()
        first, last = full.split(" ", 1)
        p = Person.objects.create(
            first_name=first,
            last_name=last,
            display_name=full,
            email=fake_email(full),
        )
        Address.objects.create(
            person=p,
            label="Privat",
            street=f"Musterstraße {10 + i}",
            postal_code="70173",
            city="Stuttgart",
            is_primary=True,
        )
        created += 1

    room_cat, _ = Category.objects.get_or_create(name="Veranstaltungsraum", purpose="inventory")
    AssetItem.objects.get_or_create(
        title="Schulungsraum 1",
        asset_type="resource",
        defaults={"category": room_cat, "notes": "EG Links · Beamer, 20 Plätze"},
    )
    return created


def reset_domain_demo():
    Person.objects.filter(email__endswith="@example.com").delete()
    AssetItem.objects.filter(title="Schulungsraum 1", asset_type="resource").delete()


register_seeder("domain_kit", seed_domain_demo, order=20, reset_fn=reset_domain_demo)
