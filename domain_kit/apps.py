from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_after_migrate(sender, **kwargs):
    from .services import seed_domain_defaults

    using = kwargs.get("using") or "default"
    try:
        seed_domain_defaults(db_alias=using)
    except Exception:
        pass


class DomainKitConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "domain_kit"
    verbose_name = "Domain, Master Data & Assets Kit"

    def ready(self):
        post_migrate.connect(_seed_after_migrate, sender=self)
