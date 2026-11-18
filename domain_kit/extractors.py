from io import BytesIO
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".xml", ".log", ".ini", ".yaml", ".yml"}
MAX_CHARS = 200_000


def _extract_xml_text(raw_xml: bytes) -> str:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return ""
    return " ".join(t.strip() for t in root.itertext() if t and t.strip())


def _extract_ooxml(data: bytes, ext: str) -> str:
    parts = []
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = zf.namelist()
            if ext == ".docx":
                targets = [n for n in names if n == "word/document.xml" or n.startswith("word/header") or n.startswith("word/footer")]
            elif ext == ".xlsx":
                targets = [n for n in names if n == "xl/sharedStrings.xml" or (n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))]
            elif ext == ".pptx":
                targets = sorted(n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            else:
                targets = []
            for name in targets:
                parts.append(_extract_xml_text(zf.read(name)))
    except Exception:
        return ""
    return "\n".join(p for p in parts if p)


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(BytesIO(data))
        return "\n".join((page.extract_text() or "").strip() for page in reader.pages)
    except Exception:
        return ""


def extract_text_from_file(file_obj, filename: str = "", max_chars: int = MAX_CHARS) -> str:
    if not file_obj:
        return ""
    ext = Path(filename or getattr(file_obj, "name", "")).suffix.lower()
    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        data = file_obj.read()
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
    except Exception:
        return ""

    if not data:
        return ""

    text = ""
    if ext in TEXT_EXTS:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="ignore")
    elif ext in (".docx", ".xlsx", ".pptx"):
        text = _extract_ooxml(data, ext)
    elif ext == ".pdf":
        text = _extract_pdf(data)

    return text.strip()[:max_chars]
