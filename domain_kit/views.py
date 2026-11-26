from decimal import Decimal, InvalidOperation
import json
import mimetypes

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .extractors import extract_text_from_file
from .preview import render_document_preview
from .models import (
    ACCESS_CHOICES,
    MODULE_CHOICES,
    PURPOSE_CHOICES,
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
from .services import (
    count_module_data,
    ensure_group_permission_rows,
    get_module_access,
    get_user_module_map,
    purge_module_data,
    seed_domain_defaults,
)


def _to_int(val, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _to_dec(val, default="0.00") -> Decimal:
    try:
        return Decimal(str(val or default).replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _maybe_grid_export(request, queryset, fields, filename: str):
    exp = (request.GET.get("export") or "").strip().lower()
    if exp not in ("csv", "json"):
        return None
    try:
        from grid_kit.mixins import export_queryset_csv, export_queryset_json
    except ImportError:
        return None
    if exp == "csv":
        return export_queryset_csv(queryset, fields, filename=f"{filename}.csv")
    return export_queryset_json(queryset, fields, filename=f"{filename}.json")


def _fk_or_none(model_cls, val):
    try:
        return model_cls.objects.filter(pk=int(val)).first() if val else None
    except (TypeError, ValueError):
        return None


def _save_document_from_request(request, doc: Document, default_topic: str = "general", allowed_topics=None, uploaded_file=None):
    uploaded = uploaded_file if uploaded_file is not None else request.FILES.get("file")
    raw_title = (request.POST.get("title") or "").strip()
    if not raw_title and uploaded:
        raw_title = uploaded.name
    doc.title = (raw_title or "Dokument")[:160]
    tp = request.POST.get("topic", default_topic)
    valid_topics = allowed_topics or ("person", "asset", "contract", "inventory", "account", "finance", "general")
    doc.topic = tp if tp in valid_topics else default_topic
    if uploaded:
        doc.file = uploaded
        doc.file_name = uploaded.name[:180]
        try:
            doc.extracted_text = extract_text_from_file(uploaded, uploaded.name)
        except Exception:
            doc.extracted_text = ""
        try:
            uploaded.seek(0)
        except Exception:
            pass
    elif request.POST.get("file_name"):
        doc.file_name = request.POST.get("file_name", "").strip()[:180]
    doc.file_url = (request.POST.get("file_url") or "").strip()[:255]
    doc.category = _fk_or_none(Category, request.POST.get("category_id"))
    doc.status = _fk_or_none(Status, request.POST.get("status_id"))
    doc.person = _fk_or_none(Person, request.POST.get("person_id"))
    doc.asset = _fk_or_none(AssetItem, request.POST.get("asset_id"))
    doc.amount = _to_dec(request.POST.get("amount"))
    doc.unit = _fk_or_none(Unit, request.POST.get("unit_id"))
    doc.document_date = request.POST.get("document_date") or None
    doc.valid_until = request.POST.get("valid_until") or None
    doc.tags = (request.POST.get("tags") or "").strip()[:160]
    doc.notes = (request.POST.get("notes") or "").strip()
    if "is_public" in request.POST or "is_public_present" in request.POST:
        doc.is_public = bool(request.POST.get("is_public"))
    doc.save()
    return doc


def _create_documents_from_request(request, default_topic: str = "general", allowed_topics=None):
    files = request.FILES.getlist("file")
    if not files:
        return [_save_document_from_request(request, Document(topic=default_topic), default_topic=default_topic, allowed_topics=allowed_topics)]
    docs = []
    raw_title = (request.POST.get("title") or "").strip()
    for f in files:
        doc = Document(topic=default_topic)
        _save_document_from_request(request, doc, default_topic=default_topic, allowed_topics=allowed_topics, uploaded_file=f)
        if len(files) > 1 and raw_title:
            doc.title = f"{raw_title} — {f.name}"[:160]
            doc.save(update_fields=["title"])
        docs.append(doc)
    return docs


def _doc_ajax_or_redirect(request, docs, redirect_to: str, msg: str):
    doc_list = docs if isinstance(docs, list) else [docs]
    first = doc_list[0]
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "status": "ok",
            "id": first.id,
            "ids": [d.id for d in doc_list],
            "count": len(doc_list),
            "title": first.title,
            "file_name": first.file_name,
            "message": msg,
        })
    messages.success(request, msg)
    return redirect(redirect_to)


@login_required
def persons_page_view(request):
    solo = DomainModuleSettings.get_solo()
    if not solo.is_module_enabled("persons"):
        messages.warning(request, "Das Modul Personen ist in den Einstellungen deaktiviert.")
        return redirect("domain_kit:settings" if (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)) else "/")
    access = get_module_access(request.user, "persons")
    if access == "none":
        return HttpResponseForbidden("Kein Zugriff auf Modul Personen.")
    can_write = access == "write"
    mod_map = get_user_module_map(request.user)
    active_tab = request.GET.get("tab", "persons")

    if request.method == "POST":
        if not can_write:
            return HttpResponseForbidden("Schreibzugriff auf Personen verweigert.")
        action = request.POST.get("action", "")

        if action in ("create_person", "update_person"):
            person = get_object_or_404(Person, pk=request.POST.get("pk")) if action == "update_person" else Person()
            person.salutation = (request.POST.get("salutation") or "").strip()[:30]
            person.title_prefix = (request.POST.get("title_prefix") or "").strip()[:40]
            person.first_name = (request.POST.get("first_name") or "").strip()[:80] or "Neu"
            person.last_name = (request.POST.get("last_name") or "").strip()[:80]
            display_name = (request.POST.get("display_name") or "").strip()[:140]
            if not display_name and action == "create_person":
                display_name = f"{person.first_name} {person.last_name}".strip()[:140]
            person.display_name = display_name
            person.email = (request.POST.get("email") or "").strip()[:140]
            person.phone = (request.POST.get("phone") or "").strip()[:60]
            person.mobile = (request.POST.get("mobile") or "").strip()[:60]
            person.company = (request.POST.get("company") or "").strip()[:120]
            person.department = (request.POST.get("department") or "").strip()[:100]
            person.job_title = (request.POST.get("job_title") or "").strip()[:100]
            person.birth_date = request.POST.get("birth_date") or None
            person.website = (request.POST.get("website") or "").strip()[:200]
            person.is_public = bool(request.POST.get("is_public"))
            person.tax_id = (request.POST.get("tax_id") or "").strip()[:60]
            if request.FILES.get("photo"):
                person.photo = request.FILES["photo"]
            elif request.POST.get("remove_photo") == "1":
                person.photo = None
            person.category = _fk_or_none(Category, request.POST.get("category_id"))
            person.status = _fk_or_none(Status, request.POST.get("status_id"))
            person.responsible_person = _fk_or_none(Person, request.POST.get("responsible_id"))
            person.notes = (request.POST.get("notes") or "").strip()
            person.bio = (request.POST.get("bio") or "").strip()
            person.save()
            role_ids = [int(r) for r in request.POST.getlist("role_ids") if str(r).isdigit()]
            if role_ids or "role_ids_present" in request.POST:
                person.roles.set(Role.objects.filter(pk__in=role_ids))

            can_logins = (
                request.user.is_superuser
                or request.user.is_staff
                or request.user.groups.filter(name__in=("Leitung / Vorstand", "Vorstand", "Personalverantwortlicher")).exists()
            )
            created_login_info = ""
            if can_logins:
                User = get_user_model()
                if "user_id" in request.POST:
                    target_u = _fk_or_none(User, request.POST.get("user_id"))
                    if target_u is None or request.user.is_superuser or not target_u.is_superuser:
                        person.user = target_u
                        person.save(update_fields=["user"])
                if request.POST.get("create_login") == "1" and person.user is None:
                    from django.utils.crypto import get_random_string
                    from django.utils.text import slugify

                    raw_un = (request.POST.get("new_username") or f"{person.first_name}.{person.last_name}").strip()
                    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("Ä", "ae"), ("Ö", "oe"), ("Ü", "ue")):
                        raw_un = raw_un.replace(src, dst)
                    base_un = slugify(raw_un.replace(".", "-")).replace("-", ".").strip(".") or "mitglied"
                    while ".." in base_un:
                        base_un = base_un.replace("..", ".")
                    uname = base_un[:30]
                    idx = 2
                    while User.objects.filter(username=uname).exists():
                        uname = f"{base_un[:25]}{idx}"
                        idx += 1
                    raw_pw = (request.POST.get("new_password") or "").strip() or get_random_string(10)
                    u = User.objects.create_user(
                        username=uname,
                        email=person.email,
                        password=raw_pw,
                        first_name=person.first_name[:30],
                        last_name=person.last_name[:30],
                        is_staff=False,
                    )
                    person.user = u
                    person.save(update_fields=["user"])
                    created_login_info = f" · Login „{uname}“ (Start-Passwort: {raw_pw})"
                elif person.user is not None:
                    u = person.user
                    new_pw = (request.POST.get("new_password") or "").strip()
                    if new_pw:
                        u.set_password(new_pw)
                        u.save(update_fields=["password"])
                    if "user_active_present" in request.POST and u.id != request.user.id and not u.is_superuser:
                        u.is_active = bool(request.POST.get("user_is_active"))
                        u.save(update_fields=["is_active"])

                if person.user is not None and "auth_group_ids_present" in request.POST and not person.user.is_superuser:
                    gids = [int(g) for g in request.POST.getlist("auth_group_ids") if str(g).isdigit()]
                    person.user.groups.set(Group.objects.filter(pk__in=gids))

            messages.success(request, f"Person gespeichert.{created_login_info}")
            return redirect(f"{request.path}?tab=persons")

        if action == "delete_person":
            Person.objects.filter(pk=request.POST.get("pk")).delete()
            messages.success(request, "Person gelöscht.")
            return redirect(f"{request.path}?tab=persons")

        if action in ("create_address", "update_address"):
            addr = get_object_or_404(Address, pk=request.POST.get("pk")) if action == "update_address" else Address()
            addr.person = _fk_or_none(Person, request.POST.get("person_id"))
            addr.label = (request.POST.get("label") or "Hauptadresse").strip()[:80]
            addr.street = (request.POST.get("street") or "").strip()[:140]
            addr.address_addition = (request.POST.get("address_addition") or "").strip()[:140]
            addr.postal_code = (request.POST.get("postal_code") or "").strip()[:24]
            addr.city = (request.POST.get("city") or "").strip()[:80]
            addr.state = (request.POST.get("state") or "").strip()[:80]
            addr.country = (request.POST.get("country") or "Deutschland").strip()[:60]
            addr.phone = (request.POST.get("phone") or "").strip()[:60]
            addr.email = (request.POST.get("email") or "").strip()[:140]
            addr.category = _fk_or_none(Category, request.POST.get("category_id"))
            addr.is_primary = bool(request.POST.get("is_primary"))
            addr.notes = (request.POST.get("notes") or "").strip()[:200]
            addr.save()
            messages.success(request, "Adresse gespeichert.")
            return redirect(f"{request.path}?tab=addresses")

        if action == "delete_address":
            Address.objects.filter(pk=request.POST.get("pk")).delete()
            messages.success(request, "Adresse gelöscht.")
            return redirect(f"{request.path}?tab=addresses")

        if action == "create_doc":
            docs = _create_documents_from_request(request, default_topic="person", allowed_topics=("person",))
            return _doc_ajax_or_redirect(request, docs, f"{request.path}?tab=documents", f"{len(docs)} Dokument(e) gespeichert.")
        if action == "update_doc":
            doc = get_object_or_404(Document, pk=request.POST.get("pk"))
            _save_document_from_request(request, doc, default_topic="person", allowed_topics=("person",))
            return _doc_ajax_or_redirect(request, doc, f"{request.path}?tab=documents", "Dokument zum Thema Personen gespeichert.")

        if action == "delete_doc":
            Document.objects.filter(pk=request.POST.get("pk")).delete()
            messages.success(request, "Dokument gelöscht.")
            return redirect(f"{request.path}?tab=documents")

        if action == "create_person_contract":
            person = get_object_or_404(Person, pk=request.POST.get("person_id"))
            title = (request.POST.get("title") or "").strip()[:140] or f"Vertrag {person.full_name}"
            contract = AssetItem.objects.create(
                asset_type="contract",
                title=title,
                person=person,
                quantity=_parse_decimal(request.POST.get("quantity")),
                billing_interval=(request.POST.get("billing_interval") or "").strip()[:32],
                start_date=request.POST.get("start_date") or None,
                end_date=request.POST.get("end_date") or None,
                status=_fk_or_none(Status, request.POST.get("status_id")),
                notes=(request.POST.get("notes") or "").strip(),
            )
            if request.FILES.get("contract_file"):
                up = request.FILES["contract_file"]
                Document.objects.create(
                    title=title[:160],
                    file=up,
                    file_name=up.name[:180],
                    topic="contract",
                    person=person,
                    asset=contract,
                    amount=contract.quantity,
                    document_date=contract.start_date,
                )
            messages.success(request, f"Vertrag „{contract.title}“ mit {person.full_name} verknüpft.")
            return redirect(f"{request.path}?tab=persons")

    persons = Person.objects.select_related("category", "status", "responsible_person").prefetch_related(
        "roles", "addresses", "assets__status", "documents"
    )
    category_filter = (request.GET.get("category") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    q = (request.GET.get("q") or "").strip()
    if category_filter.isdigit():
        persons = persons.filter(category_id=int(category_filter))
    if status_filter.isdigit():
        persons = persons.filter(status_id=int(status_filter))
    if q:
        persons = persons.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q)
        )
    exp_resp = _maybe_grid_export(
        request, persons, ["id", "first_name", "last_name", "email", "phone", "category__name", "status__name"], "personen"
    )
    if exp_resp is not None:
        return exp_resp
    addresses = Address.objects.select_related("person", "category")
    person_docs = Document.objects.filter(Q(topic="person") | Q(person__isnull=False)).select_related(
        "category", "status", "person", "unit"
    )

    return render(
        request,
        "domain_kit/persons.html",
        {
            "active_tab": active_tab,
            "can_write": can_write,
            "persons": persons,
            "addresses": addresses,
            "person_docs": person_docs,
            "category_filter": category_filter,
            "status_filter": status_filter,
            "q": q,
            "person_categories": Category.for_purpose("person", "general"),
            "address_categories": Category.for_purpose("address", "location", "general"),
            "doc_categories": Category.for_purpose("document", "general"),
            "person_statuses": Status.for_scope("person"),
            "statuses": Status.for_scope("document"),
            "roles": Role.objects.all(),
            "units": Unit.objects.all(),
            "auth_users": get_user_model().objects.order_by("username"),
            "auth_groups": Group.objects.all().order_by("name"),
            "can_manage_logins": (
                request.user.is_superuser
                or request.user.is_staff
                or request.user.groups.filter(name__in=("Leitung / Vorstand", "Vorstand", "Personalverantwortlicher")).exists()
            ),
            "kpi_persons_total": persons.count(),
            "kpi_roles_total": Role.objects.count(),
            "kpi_addresses_total": addresses.count(),
            "kpi_docs_total": person_docs.count(),
            "mod_map": mod_map,
        },
    )


@login_required
def assets_page_view(request):
    solo = DomainModuleSettings.get_solo()
    if not solo.is_module_enabled("assets"):
        messages.warning(request, "Das Modul Assets ist in den Einstellungen deaktiviert.")
        return redirect("domain_kit:settings" if (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)) else "/")
    access = get_module_access(request.user, "assets")
    if access == "none":
        return HttpResponseForbidden("Kein Zugriff auf Modul Assets.")
    can_write = access == "write"
    mod_map = get_user_module_map(request.user)
    active_tab = request.GET.get("tab", "overview")
    type_to_mod = {"contract": "contracts", "inventory": "inventory", "resource": "inventory", "account": "accounts"}
    allowed_asset_types = [t for t, mk in type_to_mod.items() if mod_map.get(mk, {}).get("can_read")]

    if active_tab in type_to_mod and not mod_map.get(type_to_mod[active_tab], {}).get("can_read"):
        return HttpResponseForbidden("Kein Zugriff auf diesen Asset-Bereich.")
    if active_tab == "documents" and not mod_map.get("documents", {}).get("can_read"):
        return HttpResponseForbidden("Kein Zugriff auf Asset-Dokumente.")

    if request.method == "POST":
        if not can_write:
            return HttpResponseForbidden("Schreibzugriff auf Assets verweigert.")
        action = request.POST.get("action", "")

        if action in ("create_asset", "update_asset"):
            item = get_object_or_404(AssetItem, pk=request.POST.get("pk")) if action == "update_asset" else AssetItem()
            atype = request.POST.get("asset_type", "inventory")
            if atype not in ("contract", "inventory", "resource", "account"):
                atype = "inventory"
            if not mod_map.get(type_to_mod[atype], {}).get("can_write"):
                return HttpResponseForbidden("Schreibzugriff auf diesen Asset-Typ verweigert.")
            item.asset_type = atype
            item.title = (request.POST.get("title") or "Asset").strip()[:140]
            item.identifier = (request.POST.get("identifier") or "").strip()[:80]
            item.category = _fk_or_none(Category, request.POST.get("category_id"))
            item.status = _fk_or_none(Status, request.POST.get("status_id"))
            item.person = _fk_or_none(Person, request.POST.get("person_id"))
            item.address = _fk_or_none(Address, request.POST.get("address_id"))
            item.quantity = _to_dec(request.POST.get("quantity"))
            item.unit = _fk_or_none(Unit, request.POST.get("unit_id"))
            item.billing_interval = (request.POST.get("billing_interval") or "").strip()[:32]
            item.serial_number = (request.POST.get("serial_number") or "").strip()[:80]
            item.institution = (request.POST.get("institution") or "").strip()[:120]
            item.start_date = request.POST.get("start_date") or None
            item.end_date = request.POST.get("end_date") or None
            item.notes = (request.POST.get("notes") or "").strip()
            item.save()
            messages.success(request, "Asset gespeichert.")
            default_tab = "inventory" if atype == "resource" else atype
            return redirect(f"{request.path}?tab={request.POST.get('return_tab') or default_tab}")

        if action == "delete_asset":
            ret_tab = request.POST.get("return_tab") or "overview"
            target = get_object_or_404(AssetItem, pk=request.POST.get("pk"))
            if not mod_map.get(type_to_mod.get(target.asset_type, "inventory"), {}).get("can_write"):
                return HttpResponseForbidden("Löschzugriff auf diesen Asset-Typ verweigert.")
            target.delete()
            messages.success(request, "Asset gelöscht.")
            return redirect(f"{request.path}?tab={ret_tab}")

        if action == "create_doc":
            docs = _create_documents_from_request(request, default_topic="asset", allowed_topics=("asset", "contract", "inventory", "account"))
            return _doc_ajax_or_redirect(request, docs, f"{request.path}?tab=documents", f"{len(docs)} Asset-Dokument(e) gespeichert.")
        if action == "update_doc":
            doc = get_object_or_404(Document, pk=request.POST.get("pk"))
            _save_document_from_request(request, doc, default_topic="asset", allowed_topics=("asset", "contract", "inventory", "account"))
            return _doc_ajax_or_redirect(request, doc, f"{request.path}?tab=documents", "Asset-Dokument gespeichert.")

        if action == "delete_doc":
            Document.objects.filter(pk=request.POST.get("pk")).delete()
            messages.success(request, "Dokument gelöscht.")
            return redirect(f"{request.path}?tab=documents")

    all_assets = AssetItem.objects.filter(asset_type__in=allowed_asset_types).select_related(
        "category", "status", "person", "address", "unit"
    )
    category_filter = (request.GET.get("category") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    q = (request.GET.get("q") or "").strip()
    if category_filter.isdigit():
        all_assets = all_assets.filter(category_id=int(category_filter))
    if status_filter.isdigit():
        all_assets = all_assets.filter(status_id=int(status_filter))
    if q:
        all_assets = all_assets.filter(
            Q(title__icontains=q) | Q(notes__icontains=q) | Q(identifier__icontains=q)
        )
    exp_resp = _maybe_grid_export(
        request, all_assets, ["id", "asset_type", "title", "category__name", "status__name", "quantity", "amount"], "ressourcen"
    )
    if exp_resp is not None:
        return exp_resp
    contracts = all_assets.filter(asset_type="contract")
    inventory = all_assets.filter(asset_type__in=["inventory", "resource"])
    accounts = all_assets.filter(asset_type="account")
    if mod_map.get("documents", {}).get("can_read"):
        asset_docs = Document.objects.filter(
            Q(topic__in=["asset", "contract", "inventory", "account"]) | Q(asset__isnull=False)
        ).select_related("category", "status", "asset", "person", "unit")
    else:
        asset_docs = Document.objects.none()

    sum_contracts = contracts.aggregate(s=Sum("quantity"))["s"] or Decimal("0.00")
    sum_inventory = inventory.aggregate(s=Sum("quantity"))["s"] or Decimal("0.00")
    sum_accounts = accounts.aggregate(s=Sum("quantity"))["s"] or Decimal("0.00")

    has_finance_kit = False
    all_assets_list = list(all_assets)
    try:
        from django.apps import apps as dj_apps
        if dj_apps.is_installed("finance_kit"):
            from finance_kit.services import get_account_balances
            has_finance_kit = True
            bal_map = {r["ref"]: r["balance"] for r in get_account_balances()}
            for a in all_assets_list:
                if a.asset_type == "account":
                    a.live_balance = bal_map.get(f"account:{a.id}")
    except Exception:
        pass

    chart_payload = json.dumps({
        "overview_labels": ["Verträge", "Inventar", "Konten"],
        "overview_counts": [contracts.count(), inventory.count(), accounts.count()],
        "overview_values": [float(sum_contracts), float(sum_inventory), float(sum_accounts)],
        "contract_labels": [c.title for c in contracts[:8]],
        "contract_values": [float(c.quantity) for c in contracts[:8]],
        "inventory_labels": [i.title for i in inventory[:8]],
        "inventory_values": [float(i.quantity) for i in inventory[:8]],
        "account_labels": [a.title for a in accounts[:8]],
        "account_values": [float(a.quantity) for a in accounts[:8]],
    })

    return render(
        request,
        "domain_kit/assets.html",
        {
            "active_tab": active_tab,
            "can_write": can_write,
            "all_assets": all_assets_list,
            "has_finance_kit": has_finance_kit,
            "contracts": contracts,
            "inventory": inventory,
            "accounts": accounts,
            "asset_docs": asset_docs,
            "sum_contracts": sum_contracts,
            "sum_inventory": sum_inventory,
            "sum_accounts": sum_accounts,
            "chart_payload": chart_payload,
            "contract_categories": Category.for_purpose("contract", "asset", "general"),
            "inventory_categories": Category.for_purpose("inventory", "asset", "general"),
            "account_categories": Category.for_purpose("account", "asset", "general"),
            "all_asset_categories": Category.for_purpose("contract", "inventory", "account", "asset", "general"),
            "doc_categories": Category.for_purpose("document", "general"),
            "statuses": Status.for_scope("asset", "contract", "inventory", "account"),
            "category_filter": category_filter,
            "status_filter": status_filter,
            "q": q,
            "units": Unit.objects.all(),
            "persons": Person.objects.all(),
            "addresses": Address.objects.all(),
            "mod_map": mod_map,
        },
    )


@login_required
def documents_page_view(request):
    solo = DomainModuleSettings.get_solo()
    if not solo.is_module_enabled("documents"):
        messages.warning(request, "Das Modul Dokumente ist in den Einstellungen deaktiviert.")
        return redirect("domain_kit:settings" if (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)) else "/")
    access = get_module_access(request.user, "documents")
    if access == "none":
        return HttpResponseForbidden("Kein Zugriff auf Modul Dokumente.")
    can_write = access == "write"
    topic_filter = request.GET.get("topic", "all")

    if request.method == "POST":
        if not can_write:
            return HttpResponseForbidden("Schreibzugriff auf Dokumente verweigert.")
        action = request.POST.get("action", "")
        if action == "create_doc":
            docs = _create_documents_from_request(request, default_topic="general")
            return _doc_ajax_or_redirect(request, docs, "domain_kit:documents", f"{len(docs)} Dokument(e) gespeichert.")
        if action == "update_doc":
            doc = get_object_or_404(Document, pk=request.POST.get("pk"))
            _save_document_from_request(request, doc, default_topic="general")
            return _doc_ajax_or_redirect(request, doc, "domain_kit:documents", "Dokument gespeichert.")
        if action == "delete_doc":
            Document.objects.filter(pk=request.POST.get("pk")).delete()
            messages.success(request, "Dokument gelöscht.")
            return redirect("domain_kit:documents")

    docs = Document.objects.select_related("category", "status", "person", "asset", "unit")
    if topic_filter in ("person", "asset", "contract", "inventory", "account", "finance", "general"):
        docs = docs.filter(topic=topic_filter)
    category_filter = (request.GET.get("category") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    q = (request.GET.get("q") or "").strip()
    if category_filter.isdigit():
        docs = docs.filter(category_id=int(category_filter))
    if status_filter.isdigit():
        docs = docs.filter(status_id=int(status_filter))
    if q:
        docs = docs.filter(Q(title__icontains=q) | Q(notes__icontains=q) | Q(extracted_text__icontains=q))
    exp_resp = _maybe_grid_export(
        request, docs, ["id", "title", "topic", "category__name", "status__name", "amount", "valid_until", "is_public"], "dokumente"
    )
    if exp_resp is not None:
        return exp_resp

    total_amount = docs.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    return render(
        request,
        "domain_kit/documents.html",
        {
            "can_write": can_write,
            "topic_filter": topic_filter,
            "category_filter": category_filter,
            "status_filter": status_filter,
            "q": q,
            "documents": docs,
            "total_amount": total_amount,
            "doc_categories": Category.for_purpose("document", "general"),
            "statuses": Status.for_scope("document"),
            "units": Unit.objects.all(),
            "persons": Person.objects.all(),
            "assets": AssetItem.objects.all(),
        },
    )


@login_required
def person_photo_view(request, pk):
    if get_module_access(request.user, "persons") == "none":
        return HttpResponseForbidden("Kein Zugriff auf Personen.")
    person = get_object_or_404(Person, pk=pk)
    if not person.photo:
        raise Http404("Kein Bild hinterlegt.")
    ctype, _ = mimetypes.guess_type(person.photo.name)
    return FileResponse(person.photo.open("rb"), as_attachment=False, content_type=ctype or "application/octet-stream")


@login_required
@xframe_options_sameorigin
def view_document_view(request, pk):
    if get_module_access(request.user, "documents") == "none":
        return HttpResponseForbidden("Kein Zugriff auf Dokumente.")
    doc = get_object_or_404(Document, pk=pk)
    if not doc.file:
        raise Http404("Keine Datei hinterlegt.")
    fname = doc.file_name or doc.file.name.rsplit("/", 1)[-1]
    ctype, _ = mimetypes.guess_type(fname)
    return FileResponse(doc.file.open("rb"), as_attachment=False, filename=fname, content_type=ctype or "application/octet-stream")


@login_required
@xframe_options_sameorigin
def preview_document_view(request, pk):
    if get_module_access(request.user, "documents") == "none":
        return HttpResponseForbidden("Kein Zugriff auf Dokumente.")
    doc = get_object_or_404(Document, pk=pk)
    fname = doc.file_name or (doc.file.name.rsplit("/", 1)[-1] if doc.file else doc.title)
    fobj = doc.file.open("rb") if doc.file else None
    try:
        res = render_document_preview(fobj, filename=fname, fallback_text=doc.extracted_text or "")
    finally:
        if fobj:
            fobj.close()
    return JsonResponse({"status": "ok", "title": doc.title, "filename": fname, **res})


@login_required
def download_document_view(request, pk):
    if get_module_access(request.user, "documents") == "none":
        return HttpResponseForbidden("Kein Zugriff auf Dokumente.")
    doc = get_object_or_404(Document, pk=pk)
    if not doc.file:
        raise Http404("Keine Datei hinterlegt.")
    return FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.file_name or doc.file.name.rsplit("/", 1)[-1])


@login_required
def global_search_view(request):
    from .search_engine import run_global_search

    solo = DomainModuleSettings.get_solo()
    if not solo.is_module_enabled("global_search"):
        messages.warning(request, "Die Globale Suche ist in den Einstellungen deaktiviert.")
        return redirect("domain_kit:settings" if (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)) else "/")

    # Only deny if an explicit group rule blocks global_search (default: allow logged-in users with per-user data isolation)
    if not (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)):
        group_ids = list(request.user.groups.values_list("id", flat=True))
        if group_ids:
            explicit_perms = list(
                DomainGroupPermission.objects.filter(
                    group_id__in=group_ids, module_key="global_search"
                ).values_list("access_level", flat=True)
            )
            if explicit_perms and all(lvl == "none" for lvl in explicit_perms):
                return HttpResponseForbidden("Kein Zugriff auf Globale Suche.")

    q = (request.GET.get("q") or "").strip()
    scope_filter = (request.GET.get("scope") or "").strip()
    res = run_global_search(request, q, scope_filter=scope_filter)
    legacy = res["legacy"]

    return render(
        request,
        "domain_kit/search.html",
        {
            "q": q,
            "scope_filter": scope_filter,
            "total_hits": res["total_hits"],
            "visible_hits": res["visible_hits"],
            "search_scopes": res["scopes"],
            "search_all_groups": res["all_groups"],
            "search_groups": res["groups"],
            "found_persons": legacy["found_persons"],
            "found_addresses": legacy["found_addresses"],
            "found_assets": legacy["found_assets"],
            "found_documents": legacy["found_documents"],
            "found_categories": legacy["found_categories"],
        },
    )


@login_required
def settings_page_view(request):
    access = get_module_access(request.user, "master_data")
    is_admin = bool(getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False))
    if access == "none" and not is_admin:
        return HttpResponseForbidden("Kein Zugriff auf Stammdaten & Schaltzentrale.")
    can_write = is_admin or (access == "write")
    active_tab = request.GET.get("tab", "modules" if is_admin else "categories")
    solo = DomainModuleSettings.get_solo()

    if request.method == "POST":
        if not can_write:
            return HttpResponseForbidden("Schreibzugriff verweigert.")
        action = request.POST.get("action", "")

        if action == "save_modules" and is_admin:
            if request.POST.get("apply_profile"):
                p = request.POST.get("apply_profile")
                solo.apply_profile(p)
                profile_names = {
                    "all": "Vollständig",
                    "persons": "Nur Personen & Kontakte",
                    "documents": "Nur Dokumente",
                    "assets": "Nur Assets & Inventar",
                    "master_data": "Nur Stammdaten",
                }
                messages.success(request, f"Profil '{profile_names.get(p, p)}' erfolgreich angewendet.")
                return redirect(f"{request.path}?tab=modules")

            for mod_key, _ in MODULE_CHOICES:
                setattr(solo, f"enable_{mod_key}", bool(request.POST.get(f"enable_{mod_key}")))
            solo.save()
            for grp in Group.objects.all():
                for mod_key, _ in MODULE_CHOICES:
                    lvl = request.POST.get(f"perm_{grp.id}_{mod_key}")
                    if lvl in ("none", "read", "write"):
                        DomainGroupPermission.objects.update_or_create(
                            group=grp,
                            module_key=mod_key,
                            defaults={"access_level": lvl},
                        )
            messages.success(request, "Modul-Schaltzentrale & Gruppenrechte gespeichert.")
            return redirect(f"{request.path}?tab=modules")

        if action == "seed_defaults" and is_admin:
            stats = seed_domain_defaults()
            messages.success(request, f"Standard-Stammdaten & Gruppen geladen ({stats}).")
            return redirect(f"{request.path}?tab=modules")

        if action == "purge_module":
            if not getattr(request.user, "is_superuser", False):
                return HttpResponseForbidden("Nur Superuser/Admin darf Modul-Daten bereinigen.")
            mod_key = request.POST.get("module_key", "")
            if request.POST.get("confirm_purge") != mod_key:
                messages.error(request, "Löschung abgebrochen: Bestätigung fehlte.")
                return redirect(f"{request.path}?tab=modules")
            deleted = purge_module_data(mod_key)
            messages.warning(request, f"Modul '{mod_key}' bereinigt ({deleted} Datensätze gelöscht).")
            return redirect(f"{request.path}?tab=modules")

        if action == "create_group" and is_admin:
            gname = (request.POST.get("group_name") or "").strip()[:150]
            if gname:
                Group.objects.get_or_create(name=gname)
                messages.success(request, f"Django-Gruppe '{gname}' angelegt.")
            return redirect(f"{request.path}?tab=modules")

        if action in ("create_category", "update_category"):
            cat = get_object_or_404(Category, pk=request.POST.get("pk")) if action == "update_category" else Category()
            cat.name = (request.POST.get("name") or "Kategorie").strip()[:100]
            cat.purpose = request.POST.get("purpose") if request.POST.get("purpose") in dict(PURPOSE_CHOICES) else "general"
            cat.code = (request.POST.get("code") or "").strip()[:40]
            cat.value = (request.POST.get("value") or "").strip()[:80]
            cat.color_state = max(1, min(8, _to_int(request.POST.get("color_state"), 1)))
            cat.custom_color = (request.POST.get("custom_color") or "").strip()[:16] if request.POST.get("use_custom_color") else ""
            cat.position = _to_int(request.POST.get("position"), 10)
            cat.save()
            messages.success(request, "Kategorie gespeichert.")
            ret_purpose = (request.POST.get("return_purpose") or "").strip()
            return redirect(f"{request.path}?tab=categories" + (f"&purpose={ret_purpose}" if ret_purpose else ""))

        if action == "delete_category":
            Category.objects.filter(pk=request.POST.get("pk")).delete()
            ret_purpose = (request.POST.get("return_purpose") or "").strip()
            return redirect(f"{request.path}?tab=categories" + (f"&purpose={ret_purpose}" if ret_purpose else ""))

        if action in ("create_unit", "update_unit"):
            u = get_object_or_404(Unit, pk=request.POST.get("pk")) if action == "update_unit" else Unit()
            u.name = (request.POST.get("name") or "Einheit").strip()[:60]
            u.symbol = (request.POST.get("symbol") or "Stk.").strip()[:20]
            dim = (request.POST.get("dimension") or "count").strip()[:24]
            u.dimension = dim if dim in dict(Unit.DIMENSION_CHOICES) else "other"
            u.decimals = max(0, min(6, _to_int(request.POST.get("decimals"), 2)))
            u.position = _to_int(request.POST.get("position"), 10)
            u.save()
            messages.success(request, "Maßeinheit gespeichert.")
            return redirect(f"{request.path}?tab=units")

        if action == "delete_unit":
            Unit.objects.filter(pk=request.POST.get("pk")).delete()
            return redirect(f"{request.path}?tab=units")

        if action in ("create_status", "update_status"):
            st = get_object_or_404(Status, pk=request.POST.get("pk")) if action == "update_status" else Status()
            st.name = (request.POST.get("name") or "Status").strip()[:60]
            st.scope = (request.POST.get("scope") or "global").strip()[:32]
            st.color_state = max(1, min(8, _to_int(request.POST.get("color_state"), 1)))
            st.custom_color = (request.POST.get("custom_color") or "").strip()[:16] if request.POST.get("use_custom_color") else ""
            st.position = _to_int(request.POST.get("position"), 10)
            st.is_final = bool(request.POST.get("is_final"))
            st.save()
            messages.success(request, "Status gespeichert.")
            ret_scope = (request.POST.get("return_scope") or "").strip()
            return redirect(f"{request.path}?tab=statuses" + (f"&scope={ret_scope}" if ret_scope else ""))

        if action == "delete_status":
            Status.objects.filter(pk=request.POST.get("pk")).delete()
            ret_scope = (request.POST.get("return_scope") or "").strip()
            return redirect(f"{request.path}?tab=statuses" + (f"&scope={ret_scope}" if ret_scope else ""))

        if action in ("create_role", "update_role"):
            rl = get_object_or_404(Role, pk=request.POST.get("pk")) if action == "update_role" else Role()
            rl.name = (request.POST.get("name") or "Rolle").strip()[:80]
            rl.category = _fk_or_none(Category, request.POST.get("category_id"))
            rl.color_state = max(1, min(8, _to_int(request.POST.get("color_state"), 1)))
            rl.custom_color = (request.POST.get("custom_color") or "").strip()[:16] if request.POST.get("use_custom_color") else ""
            rl.position = _to_int(request.POST.get("position"), 10)
            rl.description = (request.POST.get("description") or "").strip()[:200]
            rl.save()
            messages.success(request, "Rolle gespeichert.")
            return redirect(f"{request.path}?tab=roles")

        if action == "delete_role":
            Role.objects.filter(pk=request.POST.get("pk")).delete()
            return redirect(f"{request.path}?tab=roles")

    ensure_group_permission_rows()
    groups = list(Group.objects.all().order_by("name"))
    perm_lookup = {
        (p.group_id, p.module_key): p.access_level
        for p in DomainGroupPermission.objects.all()
    }
    module_rows = []
    for mod_key, mod_label in MODULE_CHOICES:
        module_rows.append({
            "key": mod_key,
            "label": mod_label,
            "enabled": solo.is_module_enabled(mod_key),
            "record_count": count_module_data(mod_key),
            "group_perms": [
                {"group": g, "level": perm_lookup.get((g.id, mod_key), "none")}
                for g in groups
            ],
        })

    purpose_filter = request.GET.get("purpose", "")
    cats = Category.objects.all()
    if purpose_filter:
        cats = cats.filter(purpose=purpose_filter)
    scope_filter = request.GET.get("scope", "")
    status_scope_choices = [
        ("global", "Global (überall verfügbar)"),
        ("document", "Dokumente"),
        ("person", "Personen & Adressen"),
        ("contract", "Verträge"),
        ("inventory", "Inventar"),
        ("account", "Konten"),
        ("finance", "Finanzen & Buchhaltung"),
        ("asset", "Assets (Allgemein)"),
    ]
    scope_label_map = dict(status_scope_choices)
    sts = list(Status.objects.filter(scope=scope_filter) if scope_filter else Status.objects.all())
    for s in sts:
        s.scope_label = scope_label_map.get(s.scope, s.scope)

    return render(
        request,
        "domain_kit/settings.html",
        {
            "active_tab": active_tab,
            "is_admin": is_admin,
            "can_write": can_write,
            "module_rows": module_rows,
            "groups": groups,
            "access_choices": ACCESS_CHOICES,
            "purpose_choices": PURPOSE_CHOICES,
            "purpose_filter": purpose_filter,
            "scope_filter": scope_filter,
            "categories": cats,
            "units": Unit.objects.all(),
            "unit_dimension_choices": Unit.DIMENSION_CHOICES,
            "statuses": sts,
            "status_scope_choices": status_scope_choices,
            "roles": Role.objects.select_related("category"),
            "role_categories": Category.for_purpose("person", "general"),
        },
    )


@login_required
def self_service_profile_view(request):
    person = (
        Person.objects.filter(user=request.user)
        .select_related("category", "status")
        .prefetch_related("roles", "addresses")
        .first()
    )
    if person is None:
        cand = None
        if request.user.email:
            cand = Person.objects.filter(user__isnull=True, email__iexact=request.user.email).first()
        if cand is None and request.user.first_name and request.user.last_name:
            cand = Person.objects.filter(
                user__isnull=True,
                first_name__iexact=request.user.first_name,
                last_name__iexact=request.user.last_name,
            ).first()
        if cand is not None:
            cand.user = request.user
            cand.save(update_fields=["user"])
            person = cand
    if request.method == "POST":
        if not person:
            messages.error(request, "Ihrem Benutzerkonto ist noch kein Personenprofil zugeordnet.")
            return redirect("domain_kit:self_service")
        action = request.POST.get("action") or "save_contact"
        if action == "save_contact":
            person.email = (request.POST.get("email") or "").strip()[:140]
            person.phone = (request.POST.get("phone") or "").strip()[:60]
            person.mobile = (request.POST.get("mobile") or "").strip()[:60]
            person.birth_date = request.POST.get("birth_date") or None
            if request.FILES.get("photo"):
                person.photo = request.FILES["photo"]
            elif request.POST.get("remove_photo") == "1":
                person.photo = None
            person.save()
            messages.success(request, "Ihre Kontaktdaten wurden aktualisiert.")
            return redirect("domain_kit:self_service")
        if action in ("create_address", "update_address"):
            addr = (
                get_object_or_404(Address, pk=request.POST.get("pk"), person=person)
                if action == "update_address"
                else Address(person=person)
            )
            addr.label = (request.POST.get("label") or "Hauptadresse").strip()[:80]
            addr.street = (request.POST.get("street") or "").strip()[:140]
            addr.address_addition = (request.POST.get("address_addition") or "").strip()[:140]
            addr.postal_code = (request.POST.get("postal_code") or "").strip()[:24]
            addr.city = (request.POST.get("city") or "").strip()[:80]
            addr.state = (request.POST.get("state") or "").strip()[:80]
            addr.country = (request.POST.get("country") or "Deutschland").strip()[:60]
            addr.is_primary = bool(request.POST.get("is_primary"))
            addr.save()
            messages.success(request, "Adresse gespeichert.")
            return redirect("domain_kit:self_service")
        if action == "delete_address":
            Address.objects.filter(pk=request.POST.get("pk"), person=person).delete()
            messages.success(request, "Adresse entfernt.")
            return redirect("domain_kit:self_service")

    addresses = list(person.addresses.all()) if person else []
    return render(
        request,
        "domain_kit/self_service.html",
        {
            "person": person,
            "addresses": addresses,
        },
    )
