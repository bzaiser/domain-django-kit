# domain-django-kit

Universelles Stammdaten-, Personen-, Asset-, Dokumenten- & Such-Paket für Django + `django-design-studio` inkl. Modul-Schaltzentrale & Gruppen-Berechtigungs-Matrix (`Gast`, `Mitarbeiter`, `Personalverantwortlicher`, `Administrator`).

## Features
- **Stammdaten**:
  - **Kategorien (`Category`)**: Mit Zweck (`purpose`), Farbe (`color_state` 1..8), Wert/Code und Position — überall nach Zweck gefiltert einsetzbar.
  - **Maßeinheiten (`Unit`)**: `Stk.`, `€`, `m`, `Std.`, `l`, `m²`, `kg`, `%`, `psch.` usw.
  - **Status (`Status`)**: Erledigt, Begonnen, Fertig, Fehler, Verspätet, Zu groß, Zu klein usw. mit Farbe & fester **Sortierposition** (nicht alphabetisch).
  - **Rollen (`Role`)**: Mitarbeiter, Gast, Personalverantwortlicher, Dienstleister, Eigentümer usw.
- **Komplette Seiten (Tabs, KPI-Karten, Charts, Tabellen & Anzeigen/Ändern/Neu/Löschen-Modals)**:
  - `/domain/persons/` — Thema Personen, Rollen, Adressen & Dokumente zum Thema
  - `/domain/assets/` — Thema Assets (Übersicht, Dokumente zum Thema, Verträge, Inventar, Konten + Chart.js)
  - `/domain/documents/` — Dokumenten-Zentrale
  - `/domain/search/` — Globale Suche über alle aktiven & freigegebenen Module
  - `/domain/settings/` — Modul-Schaltzentrale, Gruppen-Rechte-Matrix (`Aus` / `Lesen` / `Schreiben`), Standarddaten-Loader, Daten-Purge & Stammdaten-Pflege

## Installation
```bash
pip install --no-user --upgrade --no-cache-dir git+https://github.com/bzaiser/domain-django-kit.git@main
```

```python
INSTALLED_APPS = [..., "design_studio", "domain_kit"]
TEMPLATES[0]["OPTIONS"]["context_processors"] += ["domain_kit.context_processors.domain_context"]
# urls.py
path("domain/", include("domain_kit.urls")),
```
