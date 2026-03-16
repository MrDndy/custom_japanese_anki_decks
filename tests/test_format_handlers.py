from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image


class TestPageResult:
    """PageResult dataclass has the expected fields."""

    def test_has_required_fields(self):
        from jp_anki_builder.format_handlers import PageResult

        pr = PageResult(image=None, text="hello", page_number=1, source_file="test.pdf")
        assert pr.image is None
        assert pr.text == "hello"
        assert pr.page_number == 1
        assert pr.source_file == "test.pdf"

    def test_image_field_accepts_pil_image(self):
        from jp_anki_builder.format_handlers import PageResult

        img = Image.new("RGB", (10, 10), color=(255, 0, 0))
        pr = PageResult(image=img, text=None, page_number=1, source_file="test.png")
        assert pr.image is img
        assert pr.text is None


class TestExtractPagesDirectory:
    """extract_pages dispatches to directory handler."""

    def test_directory_returns_page_results_for_images(self, tmp_path: Path):
        from jp_anki_builder.format_handlers import extract_pages

        img_dir = tmp_path / "pages"
        img_dir.mkdir()
        # create minimal valid PNG files
        for name in ["page1.png", "page2.jpg"]:
            img = Image.new("RGB", (10, 10))
            img.save(str(img_dir / name))

        results = extract_pages(img_dir)

        assert len(results) == 2
        assert all(r.image is not None for r in results)
        assert all(r.text is None for r in results)
        assert results[0].page_number == 1
        assert results[1].page_number == 2

    def test_directory_ignores_non_image_files(self, tmp_path: Path):
        from jp_anki_builder.format_handlers import extract_pages

        img_dir = tmp_path / "pages"
        img_dir.mkdir()
        img = Image.new("RGB", (10, 10))
        img.save(str(img_dir / "page1.png"))
        (img_dir / "readme.txt").write_text("ignore me")

        results = extract_pages(img_dir)

        assert len(results) == 1

    def test_single_image_file_returns_one_result(self, tmp_path: Path):
        from jp_anki_builder.format_handlers import extract_pages

        img_path = tmp_path / "page.png"
        img = Image.new("RGB", (10, 10))
        img.save(str(img_path))

        results = extract_pages(img_path)

        assert len(results) == 1
        assert results[0].image is not None
        assert results[0].page_number == 1


class TestExtractPagesCBZ:
    """CBZ handler extracts images in natural sort order."""

    def _make_cbz(self, tmp_path: Path, names: list[str]) -> Path:
        cbz_path = tmp_path / "manga.cbz"
        with zipfile.ZipFile(cbz_path, "w") as zf:
            for name in names:
                buf = io.BytesIO()
                img = Image.new("RGB", (10, 10), color=(100, 100, 100))
                img.save(buf, format="PNG")
                zf.writestr(name, buf.getvalue())
        return cbz_path

    def test_cbz_extracts_all_images(self, tmp_path: Path):
        from jp_anki_builder.format_handlers import extract_pages

        cbz = self._make_cbz(tmp_path, ["page_01.png", "page_02.png", "page_03.png"])
        results = extract_pages(cbz)

        assert len(results) == 3
        assert all(r.image is not None for r in results)
        assert all(r.text is None for r in results)

    def test_cbz_natural_sort_order(self, tmp_path: Path):
        from jp_anki_builder.format_handlers import extract_pages

        # without natural sort, "page_10" would come before "page_2"
        cbz = self._make_cbz(tmp_path, ["page_10.png", "page_2.png", "page_1.png"])
        results = extract_pages(cbz)

        assert len(results) == 3
        # natural sort: page_1, page_2, page_10
        assert results[0].source_file.endswith("page_1.png")
        assert results[1].source_file.endswith("page_2.png")
        assert results[2].source_file.endswith("page_10.png")

    def test_cbz_page_numbers_are_sequential(self, tmp_path: Path):
        from jp_anki_builder.format_handlers import extract_pages

        cbz = self._make_cbz(tmp_path, ["a.png", "b.png"])
        results = extract_pages(cbz)

        assert [r.page_number for r in results] == [1, 2]

    def test_cbz_skips_non_image_entries(self, tmp_path: Path):
        from jp_anki_builder.format_handlers import extract_pages

        cbz_path = tmp_path / "manga.cbz"
        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, format="PNG")

        with zipfile.ZipFile(cbz_path, "w") as zf:
            zf.writestr("page_1.png", buf.getvalue())
            zf.writestr("thumbs.db", b"not an image")
            zf.writestr("info.xml", b"<xml/>")

        results = extract_pages(cbz_path)
        assert len(results) == 1

    def test_cbz_source_file_includes_entry_name(self, tmp_path: Path):
        from jp_anki_builder.format_handlers import extract_pages

        cbz = self._make_cbz(tmp_path, ["page_01.png"])
        results = extract_pages(cbz)

        assert "page_01.png" in results[0].source_file


class TestExtractPagesUnsupportedFormat:
    """Unsupported formats return empty list with a warning (no crash)."""

    def test_unsupported_extension_returns_empty_list(self, tmp_path: Path):
        from jp_anki_builder.format_handlers import extract_pages

        bad_file = tmp_path / "file.xyz"
        bad_file.write_bytes(b"irrelevant")

        results = extract_pages(bad_file)
        assert results == []

    def test_unsupported_extension_does_not_raise(self, tmp_path: Path):
        from jp_anki_builder.format_handlers import extract_pages

        bad_file = tmp_path / "file.docx"
        bad_file.write_bytes(b"irrelevant")

        # Must not raise
        extract_pages(bad_file)


class TestExtractPagesCBROptionalDep:
    """CBR handler raises ImportError-derived error when rarfile not installed."""

    def test_cbr_raises_clear_error_when_rarfile_missing(self, tmp_path: Path, monkeypatch):
        import sys
        from jp_anki_builder import format_handlers

        # Simulate rarfile not installed by hiding it from sys.modules
        monkeypatch.setitem(sys.modules, "rarfile", None)
        # Force re-evaluation of the import check
        monkeypatch.setattr(format_handlers, "_RARFILE_AVAILABLE", False)

        cbr_path = tmp_path / "manga.cbr"
        cbr_path.write_bytes(b"fake rar")

        with pytest.raises(RuntimeError, match="rarfile"):
            format_handlers.extract_pages(cbr_path)


class TestExtractPagesPDF:
    """PDF handler uses pdfplumber for text-layer PDFs; pypdfium2 for image-only PDFs."""

    def test_pdf_with_japanese_text_returns_text_result(self, tmp_path: Path, monkeypatch):
        """If pdfplumber extracts substantial Japanese text, skip OCR."""
        from jp_anki_builder import format_handlers

        pdf_path = tmp_path / "text_manga.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        japanese_text = "冒険に行く勇者"

        class FakePage:
            def extract_text(self):
                return japanese_text

        class FakePDF:
            pages = [FakePage()]
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        monkeypatch.setattr(format_handlers, "_open_pdfplumber", lambda path: FakePDF())
        monkeypatch.setattr(format_handlers, "_PDFPLUMBER_AVAILABLE", True)

        results = format_handlers.extract_pages(pdf_path)

        assert len(results) == 1
        assert results[0].text == japanese_text
        assert results[0].image is None

    def test_pdf_without_japanese_text_returns_image_result(self, tmp_path: Path, monkeypatch):
        """If pdfplumber finds no CJK text, fall back to pypdfium2 rendering."""
        from jp_anki_builder import format_handlers

        pdf_path = tmp_path / "scan_manga.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        pil_img = Image.new("RGB", (100, 100), color=(200, 200, 200))

        class FakePage:
            def extract_text(self):
                return "no japanese here"

        class FakePDF:
            pages = [FakePage()]
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        class FakePdfium2Page:
            def render(self, scale):
                return self
            def to_pil(self):
                return pil_img

        class FakePdfium2Doc:
            def __len__(self):
                return 1
            def __getitem__(self, i):
                return FakePdfium2Page()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def close(self):
                pass

        monkeypatch.setattr(format_handlers, "_open_pdfplumber", lambda path: FakePDF())
        monkeypatch.setattr(format_handlers, "_open_pypdfium2", lambda path: FakePdfium2Doc())
        monkeypatch.setattr(format_handlers, "_PDFPLUMBER_AVAILABLE", True)
        monkeypatch.setattr(format_handlers, "_PYPDFIUM2_AVAILABLE", True)

        results = format_handlers.extract_pages(pdf_path)

        assert len(results) == 1
        assert results[0].image is pil_img
        assert results[0].text is None

    def test_pdf_raises_clear_error_when_pdfplumber_missing(self, tmp_path: Path, monkeypatch):
        from jp_anki_builder import format_handlers

        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        monkeypatch.setattr(format_handlers, "_PDFPLUMBER_AVAILABLE", False)

        with pytest.raises(RuntimeError, match="pdfplumber"):
            format_handlers.extract_pages(pdf_path)


class TestExtractPagesEPUBOptionalDep:
    """EPUB handler raises clear error when ebooklib not installed."""

    def test_epub_raises_clear_error_when_ebooklib_missing(self, tmp_path: Path, monkeypatch):
        from jp_anki_builder import format_handlers

        epub_path = tmp_path / "book.epub"
        epub_path.write_bytes(b"PK fake epub")

        monkeypatch.setattr(format_handlers, "_EBOOKLIB_AVAILABLE", False)

        with pytest.raises(RuntimeError, match="ebooklib"):
            format_handlers.extract_pages(epub_path)
