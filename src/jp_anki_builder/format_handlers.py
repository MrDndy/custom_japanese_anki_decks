from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image as PilImage

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# ---------------------------------------------------------------------------
# Optional dependency availability flags (monkeypatched in tests)
# ---------------------------------------------------------------------------

try:
    import pdfplumber as _pdfplumber  # noqa: F401
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    _PDFPLUMBER_AVAILABLE = False

try:
    import pypdfium2 as _pypdfium2  # noqa: F401
    _PYPDFIUM2_AVAILABLE = True
except ImportError:
    _PYPDFIUM2_AVAILABLE = False

try:
    import rarfile as _rarfile  # noqa: F401
    _RARFILE_AVAILABLE = True
except ImportError:
    _RARFILE_AVAILABLE = False

try:
    import ebooklib as _ebooklib  # noqa: F401
    _EBOOKLIB_AVAILABLE = True
except ImportError:
    _EBOOKLIB_AVAILABLE = False

# ---------------------------------------------------------------------------
# Internal helper wrappers — replaceable in tests via monkeypatch
# ---------------------------------------------------------------------------

def _open_pdfplumber(path: Path):
    import pdfplumber
    return pdfplumber.open(str(path))


def _open_pypdfium2(path: Path):
    import pypdfium2
    return pypdfium2.PdfDocument(str(path))


# ---------------------------------------------------------------------------
# PageResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class PageResult:
    image: PilImage.Image | None  # page as PIL Image, or None if text was extracted
    text: str | None              # pre-extracted text from PDF text layer
    page_number: int
    source_file: str


# ---------------------------------------------------------------------------
# CJK detection
# ---------------------------------------------------------------------------

_CJK_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uf900-\ufaff]")
_MIN_CJK_CHARS = 5


def _has_substantial_japanese(text: str | None) -> bool:
    if not text:
        return False
    return len(_CJK_RE.findall(text)) >= _MIN_CJK_CHARS


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle_directory(path: Path) -> list[PageResult]:
    if path.is_file():
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            return []
        from PIL import Image
        img = Image.open(path)
        img.load()
        return [PageResult(image=img, text=None, page_number=1, source_file=str(path))]

    image_paths = sorted(
        p for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    results = []
    for i, ip in enumerate(image_paths, start=1):
        from PIL import Image
        img = Image.open(ip)
        img.load()
        results.append(PageResult(image=img, text=None, page_number=i, source_file=str(ip)))
    return results


def _handle_cbz(path: Path) -> list[PageResult]:
    try:
        from natsort import natsorted
    except ImportError:
        natsorted = sorted  # type: ignore[assignment]

    results = []
    with zipfile.ZipFile(path, "r") as zf:
        names = [
            n for n in zf.namelist()
            if Path(n).suffix.lower() in IMAGE_EXTENSIONS
        ]
        names = natsorted(names)
        for i, name in enumerate(names, start=1):
            from PIL import Image
            import io
            data = zf.read(name)
            try:
                img = Image.open(io.BytesIO(data))
                img.load()
            except Exception as exc:
                logger.warning("CBZ: skipping %s — %s", name, exc)
                continue
            results.append(PageResult(image=img, text=None, page_number=i, source_file=name))
    return results


def _handle_cbr(path: Path) -> list[PageResult]:
    if not _RARFILE_AVAILABLE:
        raise RuntimeError(
            "rarfile is required to open CBR files. "
            "Install it with: pip install rarfile  "
            "(also requires the 'unrar' system utility)"
        )
    import rarfile

    try:
        from natsort import natsorted
    except ImportError:
        natsorted = sorted  # type: ignore[assignment]

    results = []
    with rarfile.RarFile(str(path)) as rf:
        names = [
            n for n in rf.namelist()
            if Path(n).suffix.lower() in IMAGE_EXTENSIONS
        ]
        names = natsorted(names)
        for i, name in enumerate(names, start=1):
            from PIL import Image
            import io
            data = rf.read(name)
            try:
                img = Image.open(io.BytesIO(data))
                img.load()
            except Exception as exc:
                logger.warning("CBR: skipping %s — %s", name, exc)
                continue
            results.append(PageResult(image=img, text=None, page_number=i, source_file=name))
    return results


def _handle_pdf(path: Path) -> list[PageResult]:
    if not _PDFPLUMBER_AVAILABLE:
        raise RuntimeError(
            "pdfplumber is required to open PDF files. "
            "Install it with: pip install pdfplumber"
        )

    results = []
    with _open_pdfplumber(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if _has_substantial_japanese(text):
                results.append(PageResult(
                    image=None,
                    text=text,
                    page_number=i,
                    source_file=str(path),
                ))
            else:
                # Fall back to image rendering via pypdfium2
                if not _PYPDFIUM2_AVAILABLE:
                    raise RuntimeError(
                        "pypdfium2 is required for rendering image-only PDF pages. "
                        "Install it with: pip install pypdfium2"
                    )
                doc = _open_pypdfium2(path)
                pdf_page = doc[i - 1]
                pil_img = pdf_page.render(scale=300 / 72).to_pil()
                results.append(PageResult(
                    image=pil_img,
                    text=None,
                    page_number=i,
                    source_file=str(path),
                ))

    return results


def _handle_epub(path: Path) -> list[PageResult]:
    if not _EBOOKLIB_AVAILABLE:
        raise RuntimeError(
            "ebooklib is required to open EPUB files. "
            "Install it with: pip install ebooklib"
        )
    import io
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
    from PIL import Image

    book = epub.read_epub(str(path))
    results = []
    page_num = 1
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        data = item.get_content()
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as exc:
            logger.warning("EPUB: skipping image item — %s", exc)
            continue
        results.append(PageResult(
            image=img,
            text=None,
            page_number=page_num,
            source_file=item.get_name(),
        ))
        page_num += 1
    return results


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def extract_pages(path: Path) -> list[PageResult]:
    """Auto-detect format and return ordered PageResult list."""
    path = Path(path)

    if path.is_dir():
        return _handle_directory(path)

    ext = path.suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        return _handle_directory(path)

    if ext == ".cbz":
        return _handle_cbz(path)

    if ext == ".cbr":
        return _handle_cbr(path)

    if ext == ".pdf":
        return _handle_pdf(path)

    if ext == ".epub":
        return _handle_epub(path)

    logger.warning("Unsupported file format: %s — returning empty list", path.suffix)
    return []
