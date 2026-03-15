from jp_anki_builder.filtering import filter_tokens, is_sfx_token


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
    def test_sfx_excluded_in_prepare_review(self):
        import json
        import shutil
        import tempfile
        from jp_anki_builder.review import prepare_review

        tmp = tempfile.mkdtemp()
        try:
            from pathlib import Path
            run_dir = Path(tmp) / "manga-a" / "run-1"
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
                base_dir=tmp,
                exclude_sfx=True,
            )

            assert "ドドド" not in plan.filtered_candidates
            assert "ゴゴゴ" not in plan.filtered_candidates
            assert "ドドド" in plan.excluded_sfx
            assert "ゴゴゴ" in plan.excluded_sfx
            assert "勇者" in plan.filtered_candidates
            assert "冒険" in plan.filtered_candidates
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sfx_passes_through_when_disabled(self):
        import json
        import shutil
        import tempfile
        from jp_anki_builder.review import prepare_review

        tmp = tempfile.mkdtemp()
        try:
            from pathlib import Path
            run_dir = Path(tmp) / "manga-a" / "run-2"
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
                base_dir=tmp,
                exclude_sfx=False,
            )

            assert "ドドド" in plan.filtered_candidates
            assert plan.excluded_sfx == []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_config_exclude_sfx_key_recognized(self):
        from jp_anki_builder.project_config import ProjectDefaults
        defaults = ProjectDefaults(exclude_sfx=False)
        assert defaults.exclude_sfx is False
        defaults2 = ProjectDefaults(exclude_sfx=True)
        assert defaults2.exclude_sfx is True
