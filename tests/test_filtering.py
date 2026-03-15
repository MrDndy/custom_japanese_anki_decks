import json
from pathlib import Path

from jp_anki_builder.filtering import filter_stray_furigana, filter_tokens, is_sfx_token
from jp_anki_builder.review import prepare_review


def test_filter_tokens_excludes_particles_and_known_words():
    tokens = ["\u79c1", "\u306f", "\u5b66\u751f", "\u3067\u3059"]
    known = {"\u5b66\u751f"}
    result = filter_tokens(tokens, known_words=known)
    assert result == ["\u79c1", "\u3067\u3059"]


def test_filter_tokens_excludes_naa_and_kanji_one_to_ten():
    tokens = [
        "\u306a\u3041",
        "\u4e00",
        "\u4e8c",
        "\u4e09",
        "\u56db",
        "\u4e94",
        "\u516d",
        "\u4e03",
        "\u516b",
        "\u4e5d",
        "\u5341",
        "\u4eba",
        "\u3059\u308b",
        "\u70ba\u308b",
        "\u3044\u308b",
        "\u5c45\u308b",
        "\u3066\u308b",
        "\u3053\u306e",
        "\u305d\u306e",
        "\u3042\u306e",
        "\u5192\u967a",
    ]
    result = filter_tokens(tokens, known_words=set())
    assert result == ["\u5192\u967a"]


def test_filter_tokens_excludes_common_noise_tokens_from_scan_feedback():
    tokens = [
        "\u3069\u306e",
        "\u3082\u306e",
        "\u3072\u3068",
        "\u307e\u3067",
        "\u304b\u3089",
        "\u306a\u3093",
        "\u3053\u3053",
        "\u3059\u3050",
        "\u3084\u308b",
        "\u3088\u301c",
        "\u306a\u301c",
        "\u304a\u3044\u3063",
        "\u30ca\u30f3\u30c0\u30ab\u30e9",
        "\u30b1",
        "\u50cd\u308b",
        "\u8db3",
    ]
    result = filter_tokens(tokens, known_words=set())
    assert result == ["\u8db3"]


class TestIsSfxToken:
    def test_repeated_katakana_is_sfx(self):
        # ドドド, ゴゴゴ — same character repeated
        assert is_sfx_token("ドドド") is True
        assert is_sfx_token("ゴゴゴ") is True
        assert is_sfx_token("ザザザザ") is True

    def test_two_char_repeated_katakana_is_sfx(self):
        assert is_sfx_token("ドド") is True

    def test_short_katakana_without_dict_is_sfx(self):
        # Pure katakana 2-4 chars, not in dictionary
        assert is_sfx_token("ズン", word_exists=lambda w: False) is True
        assert is_sfx_token("ドカ", word_exists=lambda w: False) is True

    def test_legitimate_katakana_word_not_sfx(self):
        # コンピューター, テレビ, ゲーム are real loanwords
        assert is_sfx_token("コンピューター") is False  # > 4 chars, not repeated
        assert is_sfx_token("テレビ", word_exists=lambda w: True) is False
        assert is_sfx_token("ゲーム", word_exists=lambda w: True) is False

    def test_short_katakana_in_dictionary_not_sfx(self):
        # 2-4 chars but found in dictionary → NOT sfx
        assert is_sfx_token("アニメ", word_exists=lambda w: True) is False

    def test_short_katakana_no_word_exists_not_sfx(self):
        # Without word_exists callable, rule 2 doesn't apply
        assert is_sfx_token("ズン") is False  # can't check dict, don't filter

    def test_non_katakana_not_sfx(self):
        assert is_sfx_token("冒険") is False
        assert is_sfx_token("する") is False
        assert is_sfx_token("") is False

    def test_mixed_katakana_hiragana_not_sfx(self):
        assert is_sfx_token("ドどど") is False  # mixed script


class TestSfxFilterInReview:
    def test_sfx_excluded_in_prepare_review(self, tmp_path: Path):
        run_dir = tmp_path / "manga-a" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "scan.json").write_text(
            json.dumps({
                "source": "manga-a",
                "run_id": "run-1",
                "candidates": ["勇者", "ドドド", "ゴゴゴ", "冒険"],
            }, ensure_ascii=False),
            encoding="utf-8",
        )

        plan = prepare_review(
            source="manga-a",
            run_id="run-1",
            base_dir=str(tmp_path),
            exclude_sfx=True,
        )

        assert "ドドド" not in plan.filtered_candidates
        assert "ゴゴゴ" not in plan.filtered_candidates
        assert "ドドド" in plan.excluded_sfx
        assert "ゴゴゴ" in plan.excluded_sfx
        assert "勇者" in plan.filtered_candidates
        assert "冒険" in plan.filtered_candidates

    def test_sfx_passes_through_when_disabled(self, tmp_path: Path):
        run_dir = tmp_path / "manga-a" / "run-2"
        run_dir.mkdir(parents=True)
        (run_dir / "scan.json").write_text(
            json.dumps({
                "source": "manga-a",
                "run_id": "run-2",
                "candidates": ["ドドド", "勇者"],
            }, ensure_ascii=False),
            encoding="utf-8",
        )

        plan = prepare_review(
            source="manga-a",
            run_id="run-2",
            base_dir=str(tmp_path),
            exclude_sfx=False,
        )

        assert "ドドド" in plan.filtered_candidates
        assert plan.excluded_sfx == []

    def test_config_exclude_sfx_key_recognized(self):
        from jp_anki_builder.project_config import ProjectDefaults
        defaults = ProjectDefaults(exclude_sfx=False)
        assert defaults.exclude_sfx is False
        defaults2 = ProjectDefaults(exclude_sfx=True)
        assert defaults2.exclude_sfx is True


class TestFilterStrayFurigana:
    def test_single_hiragana_adjacent_to_kanji_is_excluded(self):
        # 「勇」「が」「者」→ が is adjacent to kanji on both sides
        kept, excluded = filter_stray_furigana(["勇", "が", "者"])
        assert "が" in excluded
        assert "勇" in kept
        assert "者" in kept

    def test_single_hiragana_after_kanji_is_excluded(self):
        # typical OCR furigana: 冒険 followed by stray ぼ
        kept, excluded = filter_stray_furigana(["冒険", "ぼ", "勇者"])
        assert "ぼ" in excluded

    def test_single_hiragana_before_kanji_is_excluded(self):
        kept, excluded = filter_stray_furigana(["ゆ", "勇者"])
        assert "ゆ" in excluded

    def test_multi_char_hiragana_not_excluded(self):
        # する, いる, ある are real words
        kept, excluded = filter_stray_furigana(["勇者", "する", "冒険"])
        assert "する" in kept
        assert excluded == []

    def test_single_hiragana_not_adjacent_to_kanji_not_excluded(self):
        # isolated single hiragana (no kanji neighbor) should pass through
        kept, excluded = filter_stray_furigana(["テレビ", "が", "好き"])
        # 「が」is between katakana and kanji — 好き has kanji
        # so が IS adjacent to 好き (kanji) → should be excluded
        assert "が" in excluded

    def test_single_hiragana_between_non_kanji_tokens_not_excluded(self):
        kept, excluded = filter_stray_furigana(["テレビ", "が", "ゲーム"])
        # テレビ = katakana only, ゲーム = katakana only → no kanji neighbors
        assert "が" in kept
        assert excluded == []

    def test_empty_list(self):
        kept, excluded = filter_stray_furigana([])
        assert kept == []
        assert excluded == []

    def test_furigana_filter_in_prepare_review(self, tmp_path: Path):
        run_dir = tmp_path / "manga-a" / "run-fur"
        run_dir.mkdir(parents=True)
        # 「勇者」「ゆ」「冒険」— ゆ is adjacent to 勇者 (kanji)
        (run_dir / "scan.json").write_text(
            json.dumps({
                "source": "manga-a",
                "run_id": "run-fur",
                "candidates": ["勇者", "ゆ", "冒険"],
            }, ensure_ascii=False),
            encoding="utf-8",
        )

        plan = prepare_review(
            source="manga-a",
            run_id="run-fur",
            base_dir=str(tmp_path),
            exclude_stray_furigana=True,
        )

        assert "ゆ" not in plan.filtered_candidates
        assert "ゆ" in plan.excluded_furigana
        assert "勇者" in plan.filtered_candidates
        assert "冒険" in plan.filtered_candidates

    def test_furigana_passes_through_when_disabled(self, tmp_path: Path):
        run_dir = tmp_path / "manga-a" / "run-fur2"
        run_dir.mkdir(parents=True)
        (run_dir / "scan.json").write_text(
            json.dumps({
                "source": "manga-a",
                "run_id": "run-fur2",
                "candidates": ["勇者", "ゆ"],
            }, ensure_ascii=False),
            encoding="utf-8",
        )

        plan = prepare_review(
            source="manga-a",
            run_id="run-fur2",
            base_dir=str(tmp_path),
            exclude_stray_furigana=False,
        )

        assert "ゆ" in plan.filtered_candidates
        assert plan.excluded_furigana == []
