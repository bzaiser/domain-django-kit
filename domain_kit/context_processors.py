from .models import DomainModuleSettings
from .services import get_user_module_map


def domain_context(request):
    user = getattr(request, "user", None)
    try:
        solo = DomainModuleSettings.get_solo()
        mod_map = get_user_module_map(user)
    except Exception:
        solo = None
        mod_map = {}
    return {
        "domain_settings": solo,
        "domain_modules": mod_map,
    }
