# domain-django-kit

Universelles, modulares Stammdaten-, Personen-, Asset-, Dokumenten- & Such-Paket für Django + `django-design-studio` inkl. Modul-Schaltzentrale & Gruppen-Berechtigungs-Matrix (`Gast`, `Mitarbeiter`, `Personalverantwortlicher`, `Administrator`).

## Modulare Teilbereiche (einzeln schaltbar)
Über `DomainModuleSettings` (in `/domain/settings/` oder direkt per Checkbox im `ops_kit` Updates-Tab) können Teilbereiche einzeln ein- und ausgeschaltet werden — deaktivierte Module verschwinden automatisch aus der Navigation (`design_studio/menu.py`):
- **`master_data` (Stammdaten-Basis)**: `Category` (mit `purpose`, `color_state` 1..8), `Unit`, `Status` (feste Sortierposition), `Role` → `/domain/settings/`
- **`persons` (Personen & Adressen)**: Kontakte, Kunden, Lieferanten, Adressbuch & Fotos → `/domain/persons/`
- **`documents` (Dokumente)**: Multi-Upload, Inline-Vorschau, `.docx`/`.txt`-Volltextextraktion → `/domain/documents/`
- **`assets` (Assets & Inventar)**: Übersicht, Verträge, Inventar, Konten + Chart.js → `/domain/assets/`
- **`global_search` (Globale Suche)**: App-weite Suche über alle aktiven `domain_kit`-Module (inkl. Stammdaten & Adressen), `cal_kit`, `notify_kit`, optionale App-Provider (`DOMAIN_SEARCH_PROVIDERS`) sowie **Zero-Config Auto-Discovery** aller Host-App-Models (mit automatischer User-Isolation) → `/domain/search/`

Schnell-Profile per `DomainModuleSettings.get_solo().apply_profile(...)`: `"all"`, `"master_data"`, `"persons"`, `"documents"`, `"assets"` oder kommaseparierte Modul-Liste (z. B. `"master_data,persons"`).

## Einbindung
```python
# settings.py
INSTALLED_APPS = [..., "design_studio", "domain_kit"]
TEMPLATES[0]["OPTIONS"]["context_processors"] += ["domain_kit.context_processors.domain_context"]
# Mit ops_kit.runtime (erlaubt sicheres Deaktivieren ohne Crash):
from ops_kit.runtime import filter_runtime_context_processors
TEMPLATES[0]["OPTIONS"]["context_processors"] = filter_runtime_context_processors(
    TEMPLATES[0]["OPTIONS"]["context_processors"], INSTALLED_APPS
)

# urls.py
from ops_kit.runtime import optional_kit_path
urlpatterns += optional_kit_path("domain_kit", "domain/", "domain_kit.urls")
```
