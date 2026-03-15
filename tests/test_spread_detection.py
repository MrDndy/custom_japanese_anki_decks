from __future__ import annotations

from PIL import Image


class TestDetectAndSplitSpread:
    """detect_and_split_spread splits wide images and passes through normal ones."""

    def test_normal_image_returned_as_single_element_list(self):
        from jp_anki_builder.format_handlers import detect_and_split_spread

        img = Image.new("RGB", (100, 100))  # ratio = 1.0, not a spread
        result = detect_and_split_spread(img)

        assert len(result) == 1
        assert result[0] is img

    def test_portrait_image_returned_as_single_element_list(self):
        from jp_anki_builder.format_handlers import detect_and_split_spread

        img = Image.new("RGB", (80, 200))  # ratio = 0.4, portrait
        result = detect_and_split_spread(img)

        assert len(result) == 1
        assert result[0] is img

    def test_image_at_threshold_is_not_split(self):
        from jp_anki_builder.format_handlers import detect_and_split_spread

        # ratio exactly 1.3 → not a spread (must be strictly greater)
        img = Image.new("RGB", (130, 100))
        result = detect_and_split_spread(img)

        assert len(result) == 1

    def test_wide_image_is_split_into_two(self):
        from jp_anki_builder.format_handlers import detect_and_split_spread

        img = Image.new("RGB", (200, 100))  # ratio = 2.0 > 1.3
        result = detect_and_split_spread(img)

        assert len(result) == 2

    def test_right_half_returned_first_for_japanese_reading_order(self):
        from jp_anki_builder.format_handlers import detect_and_split_spread

        # Left half is red, right half is blue
        img = Image.new("RGB", (200, 100), color=(255, 0, 0))
        blue = Image.new("RGB", (100, 100), color=(0, 0, 255))
        img.paste(blue, (100, 0))  # paste blue into right half

        result = detect_and_split_spread(img)

        assert len(result) == 2
        # Right half (blue) should be first
        right_pixel = result[0].getpixel((50, 50))
        left_pixel = result[1].getpixel((50, 50))
        assert right_pixel == (0, 0, 255), "right half (blue) should be first"
        assert left_pixel == (255, 0, 0), "left half (red) should be second"

    def test_split_halves_have_correct_dimensions(self):
        from jp_anki_builder.format_handlers import detect_and_split_spread

        img = Image.new("RGB", (200, 100))
        result = detect_and_split_spread(img)

        assert result[0].size == (100, 100)
        assert result[1].size == (100, 100)

    def test_custom_threshold_respected(self):
        from jp_anki_builder.format_handlers import detect_and_split_spread

        img = Image.new("RGB", (140, 100))  # ratio = 1.4
        # With default threshold 1.3, this IS a spread
        assert len(detect_and_split_spread(img)) == 2
        # With threshold 1.5, this is NOT a spread
        assert len(detect_and_split_spread(img, threshold=1.5)) == 1

    def test_works_with_rgba_image(self):
        from jp_anki_builder.format_handlers import detect_and_split_spread

        img = Image.new("RGBA", (200, 100))
        result = detect_and_split_spread(img)

        assert len(result) == 2
