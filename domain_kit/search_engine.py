"""Universal app-wide Global Search engine for domain-django-kit.

Combines:
1. Built-in domain_kit modules (persons, addresses, assets, documents, master data)
2. Built-in Baukasten kit providers (cal_kit, notify_kit) when installed
3. Optional app-specific providers via settings.DOMAIN_SEARCH_PROVIDERS
4. Zero-config auto-discovery over host-app models with strict user isolation
"""
from __future__ import annotations

from django.apps import apps
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.module_loading import import_string

from .models import Address, AssetItem, Category, Document, Person, Role, Status, Unit
from .services import get_user_module_map

DEFAULT_EXCLUDED_APPS = frozenset({
    "admin",
    "auth",
    "contenttypes",
    "sessions",
    "messages",
    "staticfiles",
    "humanize",
    "design_studio",
    "ops_kit",
    "domain_kit",
    "cal_kit",
    "notify_kit",
    "auth_kit",
    "grid_kit",
    "seed_kit",
    "pwa",
    "admin_interface",
    "colorfield",
    "django_extensions",
    "django_htmx",
    "crispy_forms",
    "crispy_bootstrap5",
})

DEFAULT_EXCLUDED_MODELS = frozenset({
    "userprofile",
    "usersetting",
    "designharmony",
    "processedtransactionhash",
    "importbatch",
    "pendingtransaction",
    "editablepagecontent",
    "tenant",
    "listparticipant",
})

SENSITIVE_FIELD_TOKENS = (
    "password",
    "token",
    "secret",
    "hash",
    "data_uri",
    "raw_",
    "_json",
    "signature",
    "salt",
    "uid",
    "api_key",
    "webhook",
)

USER_FK_NAMES = ("user", "owner", "created_by")


def _extract_snippet(text: str, q: str, max_len: int = 120) -> str:
    raw = " ".join(str(text or "").split())
    if not raw:
        return ""
    low = raw.lower()
    idx = low.find(q.lower())
    if idx == -1 or len(raw) <= max_len:
        return raw[:max_len] + ("…" if len(raw) > max_len else "")
    start = max(0, idx - 35)
    end = min(len(raw), idx + len(q) + 65)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(raw) else ""
    return f"{prefix}{raw[start:end]}{suffix}"


def _safe_reverse(name: str, args=None, fallback: str = "") -> str:
    try:
        return reverse(name, args=args or ())
    except Exception:
        return fallback


def _get_searchable_text_fields(model) -> list[models.Field]:
    fields = []
    for f in model._meta.concrete_fields:
        if not isinstance(f, (models.CharField, models.TextField, models.EmailField, models.SlugField)):
            continue
        lname = f.name.lower()
        if any(tok in lname for tok in SENSITIVE_FIELD_TOKENS):
            continue
        fields.append(f)
    return fields


def _get_user_fk_field_name(model) -> str | None:
    user_model = get_user_model()
    for fname in USER_FK_NAMES:
        try:
            f = model._meta.get_field(fname)
        except Exception:
            continue
        if isinstance(f, models.ForeignKey) and f.related_model == user_model:
            return f.name
    # Also scan any other FK directly to AUTH_USER_MODEL if unambiguous
    user_fks = [
        f.name
        for f in model._meta.concrete_fields
        if isinstance(f, models.ForeignKey) and f.related_model == user_model
    ]
    if len(user_fks) == 1:
        return user_fks[0]
    return None


def _resolve_object_url(obj, user) -> str:
    if hasattr(obj, "get_absolute_url") and callable(obj.get_absolute_url):
        try:
            url = obj.get_absolute_url()
            if url:
                return str(url)
        except Exception:
            pass
    # Fallback: check if a parent FK target defines get_absolute_url()
    for f in obj._meta.concrete_fields:
        if isinstance(f, models.ForeignKey) and f.name not in ("user", "owner", "created_by", "updated_by"):
            try:
                rel_obj = getattr(obj, f.name, None)
                if rel_obj is not None and hasattr(rel_obj, "get_absolute_url") and callable(rel_obj.get_absolute_url):
                    parent_url = rel_obj.get_absolute_url()
                    if parent_url:
                        sep = "" if "#" in str(parent_url) else f"#item-{obj.pk}"
                        return f"{parent_url}{sep}"
            except Exception:
                continue
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        app_label = obj._meta.app_label
        model_name = obj._meta.model_name
        return _safe_reverse(f"admin:{app_label}_{model_name}_change", args=[obj.pk])
    return ""


def _search_domain_kit(request, q: str):
    mod_map = get_user_module_map(request.user)
    scopes = []
    groups = []
    legacy = {
        "found_persons": [],
        "found_addresses": [],
        "found_assets": [],
        "found_documents": [],
        "found_categories": [],
    }

    if mod_map.get("persons", {}).get("can_read"):
        scopes.append({"key": "domain_persons", "label": "Personen", "icon": "bi-people"})
        if q:
            rows = list(
                Person.objects.filter(
                    Q(first_name__icontains=q)
                    | Q(last_name__icontains=q)
                    | Q(display_name__icontains=q)
                    | Q(email__icontains=q)
                    | Q(company__icontains=q)
                    | Q(notes__icontains=q)
                ).select_related("category", "status")[:50]
            )
            legacy["found_persons"] = rows
            if rows:
                url = _safe_reverse("domain_kit:persons", fallback="/domain/persons/") + "?tab=persons"
                groups.append({
                    "key": "domain_persons",
                    "label": "Personen",
                    "icon": "bi-people",
                    "state": 2,
                    "hits": [
                        {
                            "title": p.full_name,
                            "subtitle": " · ".join(x for x in (p.company, p.email) if x),
                            "snippet": _extract_snippet(p.notes, q) if q.lower() in (p.notes or "").lower() else "",
                            "badge": p.category.name if p.category else "",
                            "url": url,
                            "url_label": "Zu Personen",
                        }
                        for p in rows
                    ],
                })

    if mod_map.get("addresses", {}).get("can_read"):
        scopes.append({"key": "domain_addresses", "label": "Adressen", "icon": "bi-geo-alt"})
        if q:
            rows = list(
                Address.objects.filter(
                    Q(street__icontains=q) | Q(city__icontains=q) | Q(postal_code__icontains=q) | Q(label__icontains=q)
                ).select_related("person")[:50]
            )
            legacy["found_addresses"] = rows
            if rows:
                url = _safe_reverse("domain_kit:persons", fallback="/domain/persons/") + "?tab=addresses"
                groups.append({
                    "key": "domain_addresses",
                    "label": "Adressen",
                    "icon": "bi-geo-alt",
                    "state": 2,
                    "hits": [
                        {
                            "title": f"{a.street}, {a.postal_code} {a.city}".strip(", "),
                            "subtitle": a.person.full_name if a.person else "",
                            "snippet": "",
                            "badge": a.label or "",
                            "url": url,
                            "url_label": "Zu Adressen",
                        }
                        for a in rows
                    ],
                })

    if mod_map.get("assets", {}).get("can_read"):
        allowed_types = []
        if mod_map.get("contracts", {}).get("can_read"):
            allowed_types.append("contract")
        if mod_map.get("inventory", {}).get("can_read"):
            allowed_types.extend(["inventory", "resource"])
        if mod_map.get("accounts", {}).get("can_read"):
            allowed_types.append("account")
        if allowed_types:
            scopes.append({"key": "domain_assets", "label": "Assets & Inventar", "icon": "bi-boxes"})
            if q:
                rows = list(
                    AssetItem.objects.filter(asset_type__in=allowed_types)
                    .filter(
                        Q(title__icontains=q)
                        | Q(identifier__icontains=q)
                        | Q(institution__icontains=q)
                        | Q(serial_number__icontains=q)
                        | Q(notes__icontains=q)
                    )
                    .select_related("category", "status", "unit")[:50]
                )
                legacy["found_assets"] = rows
                if rows:
                    base_url = _safe_reverse("domain_kit:assets", fallback="/domain/assets/")
                    groups.append({
                        "key": "domain_assets",
                        "label": "Assets & Inventar",
                        "icon": "bi-boxes",
                        "state": 3,
                        "hits": [
                            {
                                "title": a.title,
                                "subtitle": f"{a.quantity} {a.unit.symbol if a.unit else ''}".strip(),
                                "snippet": _extract_snippet(a.notes or a.institution or a.identifier, q),
                                "badge": a.get_asset_type_display(),
                                "url": f"{base_url}?tab={a.asset_type}",
                                "url_label": "Zum Asset",
                            }
                            for a in rows
                        ],
                    })

    if mod_map.get("documents", {}).get("can_read"):
        scopes.append({"key": "domain_documents", "label": "Dokumente", "icon": "bi-folder2-open"})
        if q:
            rows = list(
                Document.objects.filter(
                    Q(title__icontains=q)
                    | Q(tags__icontains=q)
                    | Q(file_name__icontains=q)
                    | Q(notes__icontains=q)
                    | Q(extracted_text__icontains=q)
                ).select_related("category", "status")[:50]
            )
            legacy["found_documents"] = rows
            if rows:
                url = _safe_reverse("domain_kit:documents", fallback="/domain/documents/")
                groups.append({
                    "key": "domain_documents",
                    "label": "Dokumente",
                    "icon": "bi-folder2-open",
                    "state": 4,
                    "hits": [
                        {
                            "title": d.title,
                            "subtitle": d.file_name or "",
                            "snippet": _extract_snippet(d.extracted_text or d.notes or d.tags, q),
                            "badge": d.get_topic_display(),
                            "url": url,
                            "url_label": "Zu Dokumenten",
                        }
                        for d in rows
                    ],
                })

    if apps.is_installed("finance_kit") and mod_map.get("accounts", {}).get("can_read"):
        scopes.append({"key": "finance_kit", "label": "Finanzen & Belege", "icon": "bi-cash-coin"})
        if q:
            try:
                from finance_kit.models import BusinessDocument, DonationReceipt, LedgerEntry
                fin_hits = []
                for e in LedgerEntry.objects.filter(Q(description__icontains=q) | Q(receipt_number__icontains=q) | Q(person_name__icontains=q))[:20]:
                    fin_hits.append({
                        "title": f"{e.receipt_number or e.id}: {e.description}",
                        "subtitle": f"{e.date:%d.%m.%Y} · {e.amount:.2f} €",
                        "snippet": e.person_name or e.get_sphere_display(),
                        "badge": e.get_entry_type_display(),
                        "url": _safe_reverse("finance_kit:ledger", fallback="/finance/ledger/"),
                        "url_label": "Zum Journal",
                    })
                for r in DonationReceipt.objects.filter(Q(donor_name__icontains=q) | Q(receipt_number__icontains=q))[:10]:
                    fin_hits.append({
                        "title": f"{r.receipt_number}: {r.donor_name}",
                        "subtitle": f"{r.date_received:%d.%m.%Y} · {r.amount:.2f} €",
                        "snippet": r.purpose_note,
                        "badge": "Spendenquittung",
                        "url": _safe_reverse("finance_kit:donations", fallback="/finance/donations/"),
                        "url_label": "Zu Spenden",
                    })
                for bd in BusinessDocument.objects.filter(Q(doc_number__icontains=q) | Q(recipient_name__icontains=q) | Q(subject__icontains=q))[:10]:
                    fin_hits.append({
                        "title": f"{bd.doc_number}: {bd.subject}",
                        "subtitle": f"{bd.recipient_name} · {bd.total_gross:.2f} €",
                        "snippet": bd.notes,
                        "badge": bd.get_doc_type_display(),
                        "url": _safe_reverse("finance_kit:documents", fallback="/finance/documents/"),
                        "url_label": "Zu Belegen",
                    })
                if fin_hits:
                    groups.append({
                        "key": "finance_kit",
                        "label": "Finanzen & Belege",
                        "icon": "bi-cash-coin",
                        "state": 2,
                        "hits": fin_hits,
                    })
            except Exception:
                pass

    if mod_map.get("master_data", {}).get("can_read"):
        scopes.append({"key": "domain_master_data", "label": "Stammdaten", "icon": "bi-tags"})
        if q:
            cats = list(Category.objects.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(purpose__icontains=q))[:30])
            statuses = list(Status.objects.filter(Q(name__icontains=q) | Q(scope__icontains=q))[:20])
            units = list(Unit.objects.filter(Q(name__icontains=q) | Q(symbol__icontains=q))[:20])
            roles = list(Role.objects.filter(Q(name__icontains=q) | Q(description__icontains=q))[:20])
            legacy["found_categories"] = cats
            md_hits = []
            base_url = _safe_reverse("domain_kit:settings", fallback="/domain/settings/")
            for c in cats:
                md_hits.append({"title": c.name, "subtitle": c.code or "", "snippet": "", "badge": f"Kategorie ({c.get_purpose_display()})", "url": f"{base_url}?tab=categories", "url_label": "Zu Stammdaten"})
            for s in statuses:
                md_hits.append({"title": s.name, "subtitle": s.scope or "", "snippet": "", "badge": "Status", "url": f"{base_url}?tab=statuses", "url_label": "Zu Stammdaten"})
            for u in units:
                md_hits.append({"title": f"{u.name} ({u.symbol})", "subtitle": "", "snippet": "", "badge": "Einheit", "url": f"{base_url}?tab=units", "url_label": "Zu Stammdaten"})
            for r in roles:
                md_hits.append({"title": r.name, "subtitle": "", "snippet": _extract_snippet(r.description, q) if r.description else "", "badge": "Rolle", "url": f"{base_url}?tab=roles", "url_label": "Zu Stammdaten"})
            if md_hits:
                groups.append({
                    "key": "domain_master_data",
                    "label": "Stammdaten",
                    "icon": "bi-tags",
                    "state": 5,
                    "hits": md_hits,
                })

    return scopes, groups, legacy


def _search_cal_kit(request, q: str):
    if not apps.is_installed("cal_kit"):
        return [], []
    try:
        CalendarEvent = apps.get_model("cal_kit", "CalendarEvent")
    except Exception:
        return [], []
    scopes = [{"key": "cal_kit", "label": "Kalender", "icon": "bi-calendar3"}]
    if not q:
        return scopes, []
    try:
        rows = list(
            CalendarEvent.objects.filter(user=request.user)
            .filter(Q(title__icontains=q) | Q(location__icontains=q) | Q(description__icontains=q))
            .order_by("-start_at")[:30]
        )
    except Exception:
        return scopes, []
    if not rows:
        return scopes, []
    cal_url = _safe_reverse("cal_kit:calendar", fallback="/calendar/")
    hits = []
    for ev in rows:
        date_str = ev.start_at.strftime("%d.%m.%Y %H:%M") if getattr(ev, "start_at", None) else ""
        sub = " · ".join(x for x in (date_str, ev.location) if x)
        hits.append({
            "title": ev.title,
            "subtitle": sub,
            "snippet": _extract_snippet(ev.description, q) if ev.description else "",
            "badge": "Erinnerung" if getattr(ev, "is_reminder", False) else "Termin",
            "url": cal_url,
            "url_label": "Zum Kalender",
        })
    return scopes, [{"key": "cal_kit", "label": "Kalender", "icon": "bi-calendar3", "state": 6, "hits": hits}]


def _search_notify_kit(request, q: str):
    if not apps.is_installed("notify_kit"):
        return [], []
    try:
        Notification = apps.get_model("notify_kit", "Notification")
    except Exception:
        return [], []
    scopes = [{"key": "notify_kit", "label": "Meldungen", "icon": "bi-bell"}]
    if not q:
        return scopes, []
    try:
        rows = list(
            Notification.objects.filter(user=request.user)
            .filter(Q(title__icontains=q) | Q(message__icontains=q))
            .order_by("-created_at")[:25]
        )
    except Exception:
        return scopes, []
    if not rows:
        return scopes, []
    inbox_url = _safe_reverse("notify_kit:inbox", fallback="/notifications/")
    hits = [
        {
            "title": n.title,
            "subtitle": n.created_at.strftime("%d.%m.%Y %H:%M") if getattr(n, "created_at", None) else "",
            "snippet": _extract_snippet(n.message, q),
            "badge": getattr(n, "level", "") or "",
            "url": getattr(n, "link", "") or inbox_url,
            "url_label": "Öffnen",
        }
        for n in rows
    ]
    return scopes, [{"key": "notify_kit", "label": "Meldungen", "icon": "bi-bell", "state": 7, "hits": hits}]


def _search_custom_providers(request, q: str):
    provider_paths = getattr(django_settings, "DOMAIN_SEARCH_PROVIDERS", ()) or ()
    scopes = []
    groups = []
    handled_models: set[str] = set()
    for dotted in provider_paths:
        try:
            fn = import_string(dotted)
            res = fn(request, q)
        except Exception:
            continue
        if not res:
            continue
        if isinstance(res, dict):
            res = [res]
        for grp in res:
            if not isinstance(grp, dict) or not grp.get("key"):
                continue
            scopes.append({
                "key": grp["key"],
                "label": grp.get("label") or grp["key"],
                "icon": grp.get("icon") or "bi-app",
            })
            for m in grp.get("handled_models") or ():
                handled_models.add(str(m).lower())
            if q and grp.get("hits"):
                groups.append({
                    "key": grp["key"],
                    "label": grp.get("label") or grp["key"],
                    "icon": grp.get("icon") or "bi-app",
                    "state": grp.get("state", 1),
                    "hits": grp["hits"][:40],
                })
    return scopes, groups, handled_models


def _search_autodiscover(request, q: str, handled_models: set[str]):
    if not getattr(django_settings, "DOMAIN_SEARCH_AUTO_DISCOVER", True):
        return [], []

    excluded_apps = set(DEFAULT_EXCLUDED_APPS) | {
        str(a).strip().lower() for a in (getattr(django_settings, "DOMAIN_SEARCH_EXCLUDE_APPS", ()) or ())
    }
    excluded_models = set(DEFAULT_EXCLUDED_MODELS) | {
        str(m).strip().lower() for m in (getattr(django_settings, "DOMAIN_SEARCH_EXCLUDE_MODELS", ()) or ())
    }

    scopes = []
    groups = []

    for model in apps.get_models():
        meta = model._meta
        if meta.abstract or meta.proxy or not meta.managed:
            continue
        app_label = meta.app_label.lower()
        model_name = meta.model_name.lower()
        full_key = f"{app_label}.{model_name}"
        if app_label in excluded_apps or model_name in excluded_models or full_key in handled_models:
            continue

        text_fields = _get_searchable_text_fields(model)
        if not text_fields:
            continue

        label = str(meta.verbose_name_plural or meta.verbose_name or model.__name__).capitalize()
        scope_key = f"app_{app_label}_{model_name}"
        scopes.append({"key": scope_key, "label": label, "icon": "bi-collection"})

        if not q:
            continue

        query_q = Q()
        for f in text_fields:
            query_q |= Q(**{f"{f.name}__icontains": q})

        try:
            qs = model.objects.all()
            user_fk = _get_user_fk_field_name(model)
            if user_fk:
                qs = qs.filter(**{user_fk: request.user})
            rows = list(qs.filter(query_q)[:25])
        except Exception:
            continue

        if not rows:
            continue

        hits = []
        for obj in rows:
            title = str(obj)[:140]
            snippet = ""
            for f in text_fields:
                val = str(getattr(obj, f.name, "") or "")
                if q.lower() in val.lower() and val.strip() != title.strip():
                    fname_lbl = str(getattr(f, "verbose_name", f.name)).capitalize()
                    snippet = f"{fname_lbl}: {_extract_snippet(val, q)}"
                    break
            url = _resolve_object_url(obj, request.user)
            hits.append({
                "title": title,
                "subtitle": "",
                "snippet": snippet,
                "badge": str(meta.verbose_name).capitalize(),
                "url": url,
                "url_label": "Öffnen" if url else "",
            })

        groups.append({
            "key": scope_key,
            "label": label,
            "icon": "bi-collection",
            "state": 1,
            "hits": hits,
        })

    return scopes, groups


def run_global_search(request, q: str, scope_filter: str = ""):
    """Run global search across domain_kit, active kits, custom providers & auto-discovered app models."""
    all_scopes: list[dict] = []
    all_groups: list[dict] = []

    c_scopes, c_groups, handled_models = _search_custom_providers(request, q)
    a_scopes, a_groups = _search_autodiscover(request, q, handled_models)
    cal_scopes, cal_groups = _search_cal_kit(request, q)
    not_scopes, not_groups = _search_notify_kit(request, q)
    d_scopes, d_groups, legacy = _search_domain_kit(request, q)

    # Order: Host App results first (most relevant!), then Calendar, Notifications, Domain Kit
    for s_list in (c_scopes, a_scopes, cal_scopes, not_scopes, d_scopes):
        for s in s_list:
            if not any(x["key"] == s["key"] for x in all_scopes):
                all_scopes.append(s)

    for g_list in (c_groups, a_groups, cal_groups, not_groups, d_groups):
        all_groups.extend(g_list)

    unfiltered_total = sum(len(g["hits"]) for g in all_groups)
    if scope_filter:
        visible_groups = [g for g in all_groups if g["key"] == scope_filter]
    else:
        visible_groups = all_groups

    return {
        "scopes": all_scopes,
        "all_groups": all_groups,
        "groups": visible_groups,
        "total_hits": unfiltered_total,
        "visible_hits": sum(len(g["hits"]) for g in visible_groups),
        "legacy": legacy,
    }
