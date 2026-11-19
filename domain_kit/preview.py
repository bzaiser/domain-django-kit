import csv
import html
from io import BytesIO, StringIO
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

MAX_PREVIEW_ROWS = 250
MAX_PREVIEW_COLS = 30
MAX_TEXT_CHARS = 120_000


def _decode_bytes(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="ignore")


def _render_table(rows: list[list[str]], title: str = "") -> str:
    if not rows:
        return ""
    out = []
    if title:
        out.append(f'<h6 class="fw-bold mt-3 mb-2">{html.escape(title)}</h6>')
    out.append('<div class="table-responsive border rounded mb-3"><table class="table table-sm table-striped table-hover align-middle mb-0 text-start">')
    for idx, row in enumerate(rows[:MAX_PREVIEW_ROWS]):
        tag = "th" if idx == 0 else "td"
        cells = "".join(f"<{tag}>{html.escape(str(c or ''))}</{tag}>" for c in row[:MAX_PREVIEW_COLS])
        if idx == 0:
            out.append(f"<thead><tr>{cells}</tr></thead><tbody>")
        else:
            out.append(f"<tr>{cells}</tr>")
    out.append("</tbody></table></div>")
    if len(rows) > MAX_PREVIEW_ROWS:
        out.append(f'<div class="small text-muted mb-2">… weitere {len(rows) - MAX_PREVIEW_ROWS} Zeilen gekürzt</div>')
    return "".join(out)


def _preview_docx(data: bytes) -> str:
    try:
        import docx  # optional open-source python-docx
        doc = docx.Document(BytesIO(data))
        parts = []
        for p in doc.paragraphs:
            txt = (p.text or "").strip()
            if not txt:
                continue
            style_name = (p.style.name or "").lower() if p.style else ""
            if "heading 1" in style_name or "überschrift 1" in style_name:
                parts.append(f'<h5 class="fw-bold mt-3">{html.escape(txt)}</h5>')
            elif "heading" in style_name or "überschrift" in style_name:
                parts.append(f'<h6 class="fw-bold mt-2">{html.escape(txt)}</h6>')
            else:
                parts.append(f'<p class="mb-2">{html.escape(txt)}</p>')
        for tbl in doc.tables:
            rows = [[cell.text.strip() for cell in r.cells] for r in tbl.rows]
            parts.append(_render_table(rows))
        if parts:
            return f'<div class="text-start">{"".join(parts)}</div>'
    except Exception:
        pass

    parts = []
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            if "word/document.xml" in zf.namelist():
                root = ET.fromstring(zf.read("word/document.xml"))
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                body = root.find("w:body", ns)
                if body is not None:
                    for child in body:
                        tag = child.tag.rsplit("}", 1)[-1]
                        if tag == "p":
                            txt = "".join(t.text or "" for t in child.iter() if t.tag.endswith("}t")).strip()
                            if txt:
                                parts.append(f'<p class="mb-2">{html.escape(txt)}</p>')
                        elif tag == "tbl":
                            rows = []
                            for tr in child.findall("w:tr", ns):
                                row = []
                                for tc in tr.findall("w:tc", ns):
                                    cell_txt = " ".join(
                                        t.text.strip() for t in tc.iter() if t.tag.endswith("}t") and t.text and t.text.strip()
                                    )
                                    row.append(cell_txt)
                                if row:
                                    rows.append(row)
                            parts.append(_render_table(rows))
    except Exception:
        return ""
    return f'<div class="text-start">{"".join(parts)}</div>' if parts else ""


def _preview_xlsx(data: bytes) -> str:
    try:
        import openpyxl  # optional open-source openpyxl
        wb = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
        out = []
        for sheet_name in wb.sheetnames[:10]:
            ws = wb[sheet_name]
            rows = []
            for r_idx, row in enumerate(ws.iter_rows(values_only=True)):
                if r_idx >= MAX_PREVIEW_ROWS:
                    break
                rows.append(["" if v is None else str(v) for v in row[:MAX_PREVIEW_COLS]])
            if rows:
                out.append(_render_table(rows, title=sheet_name))
        if out:
            return "".join(out)
    except Exception:
        pass

    out = []
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            shared = []
            if "xl/sharedStrings.xml" in zf.namelist():
                s_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in s_root:
                    shared.append("".join(t.text or "" for t in si.iter() if t.tag.endswith("}t")))
            sheets = sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            for s_idx, s_name in enumerate(sheets[:10], start=1):
                root = ET.fromstring(zf.read(s_name))
                rows = []
                for row_el in root.iter():
                    if not row_el.tag.endswith("}row"):
                        continue
                    row_vals = []
                    for c_el in row_el:
                        if not c_el.tag.endswith("}c"):
                            continue
                        ctype = c_el.attrib.get("t", "")
                        v_el = next((x for x in c_el if x.tag.endswith("}v")), None)
                        if v_el is not None and v_el.text is not None:
                            if ctype == "s" and v_el.text.isdigit() and int(v_el.text) < len(shared):
                                row_vals.append(shared[int(v_el.text)])
                            else:
                                row_vals.append(v_el.text)
                        else:
                            row_vals.append("".join(x.text or "" for x in c_el.iter() if x.tag.endswith("}t")))
                    if any(row_vals):
                        rows.append(row_vals)
                if rows:
                    out.append(_render_table(rows, title=f"Tabellenblatt {s_idx}"))
    except Exception:
        return ""
    return "".join(out)


def _preview_pptx(data: bytes) -> str:
    slides_html = []
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            slide_files = sorted(n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            for idx, sfile in enumerate(slide_files[:50], start=1):
                root = ET.fromstring(zf.read(sfile))
                texts = [t.text.strip() for t in root.iter() if t.tag.endswith("}t") and t.text and t.text.strip()]
                if texts:
                    body = "".join(f'<div class="mb-1">{html.escape(t)}</div>' for t in texts)
                    slides_html.append(
                        f'<div class="card mb-2 text-start"><div class="card-header py-1 fw-bold small">Folie {idx}</div>'
                        f'<div class="card-body py-2 small">{body}</div></div>'
                    )
    except Exception:
        return ""
    return "".join(slides_html)


def _preview_odf(data: bytes, ext: str) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            if "content.xml" not in zf.namelist():
                return ""
            root = ET.fromstring(zf.read("content.xml"))
            if ext == ".ods":
                rows = []
                for tr in root.iter():
                    if not tr.tag.endswith("}table-row"):
                        continue
                    row = []
                    for tc in tr:
                        if tc.tag.endswith("}table-cell"):
                            txt = " ".join(t.strip() for t in tc.itertext() if t and t.strip())
                            row.append(txt)
                    if any(row):
                        rows.append(row)
                return _render_table(rows, title="Tabelle")
            paras = []
            for p in root.iter():
                if p.tag.endswith("}p") or p.tag.endswith("}h"):
                    txt = "".join(p.itertext()).strip()
                    if txt:
                        tag = "h6" if p.tag.endswith("}h") else "p"
                        paras.append(f'<{tag} class="mb-2">{html.escape(txt)}</{tag}>')
            return f'<div class="text-start">{"".join(paras)}</div>' if paras else ""
    except Exception:
        return ""


def _preview_csv(data: bytes, delimiter: str = ",") -> str:
    txt = _decode_bytes(data)
    try:
        sample = txt[:2048]
        if delimiter == "," and ";" in sample and sample.count(";") >= sample.count(","):
            delimiter = ";"
        rows = list(csv.reader(StringIO(txt), delimiter=delimiter))
        return _render_table(rows)
    except Exception:
        return f'<pre class="text-start small p-3 rounded border bg-body-tertiary mb-0">{html.escape(txt[:MAX_TEXT_CHARS])}</pre>'


def render_document_preview(file_obj, filename: str = "", fallback_text: str = "") -> dict:
    ext = Path(filename or getattr(file_obj, "name", "")).suffix.lower()
    data = b""
    if file_obj:
        try:
            if hasattr(file_obj, "seek"):
                file_obj.seek(0)
            data = file_obj.read()
        except Exception:
            data = b""

    html_out = ""
    if ext == ".docx" and data:
        html_out = _preview_docx(data)
    elif ext == ".xlsx" and data:
        html_out = _preview_xlsx(data)
    elif ext == ".pptx" and data:
        html_out = _preview_pptx(data)
    elif ext in (".odt", ".ods", ".odp") and data:
        html_out = _preview_odf(data, ext)
    elif ext in (".csv", ".tsv") and data:
        html_out = _preview_csv(data, delimiter="\t" if ext == ".tsv" else ",")
    elif ext == ".json" and data:
        raw = _decode_bytes(data)
        try:
            raw = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
        except Exception:
            pass
        html_out = f'<pre class="text-start small p-3 rounded border bg-body-tertiary mb-0" style="white-space: pre-wrap;">{html.escape(raw[:MAX_TEXT_CHARS])}</pre>'
    elif ext in (".txt", ".md", ".log", ".ini", ".xml", ".yaml", ".yml") and data:
        raw = _decode_bytes(data)
        html_out = f'<pre class="text-start small p-3 rounded border bg-body-tertiary mb-0" style="white-space: pre-wrap;">{html.escape(raw[:MAX_TEXT_CHARS])}</pre>'

    if not html_out and fallback_text:
        html_out = f'<pre class="text-start small p-3 rounded border bg-body-tertiary mb-0" style="white-space: pre-wrap;">{html.escape(fallback_text[:MAX_TEXT_CHARS])}</pre>'

    if not html_out:
        html_out = '<div class="text-muted py-4">Für dieses Dateiformat ist keine direkte Vorschau verfügbar.</div>'

    return {"ext": ext, "html": html_out}
