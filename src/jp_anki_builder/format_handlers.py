"""Format handlers for extracting page images from manga containers.

Supports directories of images, CBZ (ZIP), CBR (RAR), PDF, and EPUB files.
All handlers apply spread detection to wide pages before returning results.
"""
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
# Spread-aware page appender
# ---------------------------------------------------------------------------

def _append_image_pages(
    results: list[PageResult],
    img: PilImage.Image,
    source_file: str,
    page_counter: list[int],
) -> None:
    """Apply spread detection to *img* and append one or two PageResults.

    *page_counter* is a single-element list used as a mutable counter so
    callers don't need to track page numbers explicitly.
    """
    halves = detect_and_split_spread(img)
    if len(halves) == 1:
        results.append(PageResult(
            image=halves[0],
            text=None,
            page_number=page_counter[0],
            source_file=source_file,
        ))
        page_counter[0] += 1
    else:
        for half_idx, half_img in enumerate(halves):
            results.append(PageResult(
                image=half_img,
                text=None,
                page_number=page_counter[0],
                source_file=f"{source_file}::half_{half_idx}",
            ))
            page_counter[0] += 1


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle_directory(path: Path) -> list[PageResult]:
    from PIL import Image

    if path.is_file():
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            return []
        img = Image.open(path)
        img.load()
        results: list[PageResult] = []
        _append_image_pages(results, img, str(path), [1])
        return results

    image_paths = sorted(
        p for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    results = []
    page_counter = [1]
    for ip in image_paths:
        img = Image.open(ip)
        img.load()
        _append_image_pages(results, img, str(ip), page_counter)
    return results


def _handle_cbz(path: Path) -> list[PageResult]:
    import io
    from PIL import Image

    try:
        from natsort import natsorted
    except ImportError:
        natsorted = sorted  # type: ignore[assignment]

    results = []
    page_counter = [1]
    with zipfile.ZipFile(path, "r") as zf:
        names = [
            n for n in zf.namelist()
            if Path(n).suffix.lower() in IMAGE_EXTENSIONS
        ]
        names = natsorted(names)
        for name in names:
            data = zf.read(name)
            try:
                img = Image.open(io.BytesIO(data))
                img.load()
            except Exception as exc:
                logger.warning("CBZ: skipping %s — %s", name, exc)
                continue
            _append_image_pages(results, img, name, page_counter)
    return results


def _handle_cbr(path: Path) -> list[PageResult]:
    import io
    from PIL import Image

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
    page_counter = [1]
    with rarfile.RarFile(str(path)) as rf:
        names = [
            n for n in rf.namelist()
            if Path(n).suffix.lower() in IMAGE_EXTENSIONS
        ]
        names = natsorted(names)
        for name in names:
            data = rf.read(name)
            try:
                img = Image.open(io.BytesIO(data))
                img.load()
            except Exception as exc:
                logger.warning("CBR: skipping %s — %s", name, exc)
                continue
            _append_image_pages(results, img, name, page_counter)
    return results


def _handle_pdf(path: Path) -> list[PageResult]:
    if not _PDFPLUMBER_AVAILABLE:
        raise RuntimeError(
            "pdfplumber is required to open PDF files. "
            "Install it with: pip install pdfplumber"
        )

    results = []
    page_counter = [1]
    _pypdfium2_doc = None
    try:
        with _open_pdfplumber(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if _has_substantial_japanese(text):
                    results.append(PageResult(
                        image=None,
                        text=text,
                        page_number=page_counter[0],
                        source_file=f"{path}::page{i}",
                    ))
                    page_counter[0] += 1
                else:
                    # Fall back to image rendering via pypdfium2
                    if not _PYPDFIUM2_AVAILABLE:
                        raise RuntimeError(
                            "pypdfium2 is required for rendering image-only PDF pages. "
                            "Install it with: pip install pypdfium2"
                        )
                    if _pypdfium2_doc is None:
                        _pypdfium2_doc = _open_pypdfium2(path)
                    pdf_page = _pypdfium2_doc[i - 1]
                    pil_img = pdf_page.render(scale=300 / 72).to_pil()
                    _append_image_pages(results, pil_img, f"{path}::page{i}", page_counter)
    finally:
        if _pypdfium2_doc is not None:
            _pypdfium2_doc.close()

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
    from PIL import Image

    book = epub.read_epub(str(path))
    results = []
    page_counter = [1]
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        data = item.get_content()
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as exc:
            logger.warning("EPUB: skipping image item — %s", exc)
            continue
        _append_image_pages(results, img, item.get_name(), page_counter)
    return results


# ---------------------------------------------------------------------------
# Spread detection
# ---------------------------------------------------------------------------

def detect_and_split_spread(image: PilImage.Image, threshold: float = 1.3) -> list[PilImage.Image]:
    """Returns [image] if not a spread, or [right_half, left_half] if it is.

    Detection: width/height ratio > threshold indicates a double-page spread.
    Splitting: right half first, then left half (Japanese reading order).
    """
    width, height = image.size
    if height == 0 or width / height <= threshold:
        return [image]

    mid = width // 2
    right_half = image.crop((mid, 0, width, height))
    left_half = image.crop((0, 0, mid, height))
    return [right_half, left_half]


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
