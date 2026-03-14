"""Yomitan-style rule-based deinflection engine.

Generates dictionary form candidates from inflected Japanese text by
applying suffix-replacement rules. Designed as a fallback when
morphological analysis (SudachiPy/fugashi) fails due to OCR noise or
partial text selection.

Each rule specifies a suffix to match (kana_in), a replacement suffix
(kana_out), and type constraints for chaining multiple deinflections.
Candidates are generated exhaustively and must be validated against a
dictionary by the caller.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeinflectionRule:
    """A single suffix-replacement rule."""

    kana_in: str
    kana_out: str
    rules_in: frozenset[str]  # word types this rule accepts (empty = any)
    rules_out: frozenset[str]  # word types the result could be
    name: str = ""


@dataclass(frozen=True)
class DeinflectionCandidate:
    """A candidate dictionary form produced by deinflection."""

    term: str
    word_types: frozenset[str]
    reasons: tuple[str, ...]


def _r(
    kana_in: str,
    kana_out: str,
    rules_out: set[str],
    name: str,
    rules_in: set[str] | None = None,
) -> DeinflectionRule:
    return DeinflectionRule(
        kana_in=kana_in,
        kana_out=kana_out,
        rules_in=frozenset(rules_in or set()),
        rules_out=frozenset(rules_out),
        name=name,
    )


# fmt: off
DEINFLECTION_RULES: list[DeinflectionRule] = [
    # === te-form ===
    _r("て",   "る",  {"v1"},  "te-form (ichidan)"),
    _r("いて", "く",  {"v5"},  "te-form (godan-ku)"),
    _r("いで", "ぐ",  {"v5"},  "te-form (godan-gu)"),
    _r("して", "す",  {"v5"},  "te-form (godan-su)"),
    _r("って", "う",  {"v5"},  "te-form (godan-u)"),
    _r("って", "つ",  {"v5"},  "te-form (godan-tsu)"),
    _r("って", "る",  {"v5"},  "te-form (godan-ru)"),
    _r("って", "く",  {"v5"},  "te-form (iku-special)"),
    _r("んで", "む",  {"v5"},  "te-form (godan-mu)"),
    _r("んで", "ぶ",  {"v5"},  "te-form (godan-bu)"),
    _r("んで", "ぬ",  {"v5"},  "te-form (godan-nu)"),

    # === ta-form (past) ===
    _r("た",   "る",  {"v1"},  "past (ichidan)"),
    _r("いた", "く",  {"v5"},  "past (godan-ku)"),
    _r("いだ", "ぐ",  {"v5"},  "past (godan-gu)"),
    _r("した", "す",  {"v5"},  "past (godan-su)"),
    _r("った", "う",  {"v5"},  "past (godan-u)"),
    _r("った", "つ",  {"v5"},  "past (godan-tsu)"),
    _r("った", "る",  {"v5"},  "past (godan-ru)"),
    _r("った", "く",  {"v5"},  "past (iku-special)"),
    _r("んだ", "む",  {"v5"},  "past (godan-mu)"),
    _r("んだ", "ぶ",  {"v5"},  "past (godan-bu)"),
    _r("んだ", "ぬ",  {"v5"},  "past (godan-nu)"),

    # === negative (nai-form) ===
    _r("ない",   "る",  {"v1", "adj-i"}, "negative (ichidan)"),
    _r("かない", "く",  {"v5"},  "negative (godan-ku)"),
    _r("がない", "ぐ",  {"v5"},  "negative (godan-gu)"),
    _r("さない", "す",  {"v5"},  "negative (godan-su)"),
    _r("たない", "つ",  {"v5"},  "negative (godan-tsu)"),
    _r("わない", "う",  {"v5"},  "negative (godan-u)"),
    _r("ばない", "ぶ",  {"v5"},  "negative (godan-bu)"),
    _r("まない", "む",  {"v5"},  "negative (godan-mu)"),
    _r("らない", "る",  {"v5"},  "negative (godan-ru)"),
    _r("なない", "ぬ",  {"v5"},  "negative (godan-nu)"),

    # === polite (masu-form) ===
    _r("ます",   "る",  {"v1"},  "polite (ichidan)"),
    _r("きます", "く",  {"v5"},  "polite (godan-ku)"),
    _r("ぎます", "ぐ",  {"v5"},  "polite (godan-gu)"),
    _r("します", "す",  {"v5"},  "polite (godan-su)"),
    _r("ちます", "つ",  {"v5"},  "polite (godan-tsu)"),
    _r("います", "う",  {"v5"},  "polite (godan-u)"),
    _r("びます", "ぶ",  {"v5"},  "polite (godan-bu)"),
    _r("みます", "む",  {"v5"},  "polite (godan-mu)"),
    _r("ります", "る",  {"v5"},  "polite (godan-ru)"),
    _r("にます", "ぬ",  {"v5"},  "polite (godan-nu)"),

    # === passive (reru/rareru) ===
    _r("られる", "る",  {"v1"},  "passive (ichidan)"),
    _r("かれる", "く",  {"v5"},  "passive (godan-ku)"),
    _r("がれる", "ぐ",  {"v5"},  "passive (godan-gu)"),
    _r("される", "す",  {"v5"},  "passive (godan-su)"),
    _r("たれる", "つ",  {"v5"},  "passive (godan-tsu)"),
    _r("われる", "う",  {"v5"},  "passive (godan-u)"),
    _r("ばれる", "ぶ",  {"v5"},  "passive (godan-bu)"),
    _r("まれる", "む",  {"v5"},  "passive (godan-mu)"),
    _r("られる", "る",  {"v5"},  "passive (godan-ru)"),
    _r("なれる", "ぬ",  {"v5"},  "passive (godan-nu)"),

    # === causative (seru/saseru) ===
    _r("させる", "る",  {"v1"},  "causative (ichidan)"),
    _r("かせる", "く",  {"v5"},  "causative (godan-ku)"),
    _r("がせる", "ぐ",  {"v5"},  "causative (godan-gu)"),
    _r("させる", "す",  {"v5"},  "causative (godan-su)"),
    _r("たせる", "つ",  {"v5"},  "causative (godan-tsu)"),
    _r("わせる", "う",  {"v5"},  "causative (godan-u)"),
    _r("ばせる", "ぶ",  {"v5"},  "causative (godan-bu)"),
    _r("ませる", "む",  {"v5"},  "causative (godan-mu)"),
    _r("らせる", "る",  {"v5"},  "causative (godan-ru)"),
    _r("なせる", "ぬ",  {"v5"},  "causative (godan-nu)"),

    # === potential (eru) ===
    _r("ける",  "く",  {"v5"},  "potential (godan-ku)"),
    _r("げる",  "ぐ",  {"v5"},  "potential (godan-gu)"),
    _r("せる",  "す",  {"v5"},  "potential (godan-su)"),
    _r("てる",  "つ",  {"v5"},  "potential (godan-tsu)"),
    _r("える",  "う",  {"v5"},  "potential (godan-u)"),
    _r("べる",  "ぶ",  {"v5"},  "potential (godan-bu)"),
    _r("める",  "む",  {"v5"},  "potential (godan-mu)"),
    _r("れる",  "る",  {"v5"},  "potential (godan-ru)"),
    _r("ねる",  "ぬ",  {"v5"},  "potential (godan-nu)"),

    # === conditional (eba) ===
    _r("れば",  "る",  {"v1"},  "conditional (ichidan)"),
    _r("けば",  "く",  {"v5"},  "conditional (godan-ku)"),
    _r("げば",  "ぐ",  {"v5"},  "conditional (godan-gu)"),
    _r("せば",  "す",  {"v5"},  "conditional (godan-su)"),
    _r("てば",  "つ",  {"v5"},  "conditional (godan-tsu)"),
    _r("えば",  "う",  {"v5"},  "conditional (godan-u)"),
    _r("べば",  "ぶ",  {"v5"},  "conditional (godan-bu)"),
    _r("めば",  "む",  {"v5"},  "conditional (godan-mu)"),
    _r("れば",  "る",  {"v5"},  "conditional (godan-ru)"),
    _r("ねば",  "ぬ",  {"v5"},  "conditional (godan-nu)"),

    # === volitional (ou/you) ===
    _r("よう",  "る",  {"v1"},  "volitional (ichidan)"),
    _r("こう",  "く",  {"v5"},  "volitional (godan-ku)"),
    _r("ごう",  "ぐ",  {"v5"},  "volitional (godan-gu)"),
    _r("そう",  "す",  {"v5"},  "volitional (godan-su)"),
    _r("とう",  "つ",  {"v5"},  "volitional (godan-tsu)"),
    _r("おう",  "う",  {"v5"},  "volitional (godan-u)"),
    _r("ぼう",  "ぶ",  {"v5"},  "volitional (godan-bu)"),
    _r("もう",  "む",  {"v5"},  "volitional (godan-mu)"),
    _r("ろう",  "る",  {"v5"},  "volitional (godan-ru)"),
    _r("のう",  "ぬ",  {"v5"},  "volitional (godan-nu)"),

    # === i-adjective forms ===
    _r("くない", "い",  {"adj-i"}, "adj negative"),
    _r("かった", "い",  {"adj-i"}, "adj past"),
    _r("くて",   "い",  {"adj-i"}, "adj te-form"),
    _r("く",     "い",  {"adj-i"}, "adj adverbial"),
    _r("ければ", "い",  {"adj-i"}, "adj conditional"),
    _r("かろう", "い",  {"adj-i"}, "adj volitional"),

    # === suru verb ===
    _r("した",   "する", {"vs"}, "suru past"),
    _r("して",   "する", {"vs"}, "suru te-form"),
    _r("しない", "する", {"vs"}, "suru negative"),
    _r("します", "する", {"vs"}, "suru polite"),
    _r("すれば", "する", {"vs"}, "suru conditional"),
    _r("しよう", "する", {"vs"}, "suru volitional"),
    _r("される", "する", {"vs"}, "suru passive"),
    _r("させる", "する", {"vs"}, "suru causative"),
    _r("できる", "する", {"vs"}, "suru potential"),

    # === kuru verb ===
    _r("きた",     "くる", {"vk"}, "kuru past"),
    _r("きて",     "くる", {"vk"}, "kuru te-form"),
    _r("こない",   "くる", {"vk"}, "kuru negative"),
    _r("きます",   "くる", {"vk"}, "kuru polite"),
    _r("くれば",   "くる", {"vk"}, "kuru conditional"),
    _r("こよう",   "くる", {"vk"}, "kuru volitional"),
    _r("こられる", "くる", {"vk"}, "kuru passive"),
    _r("こさせる", "くる", {"vk"}, "kuru causative"),

    # === chaining rules (intermediate → dictionary form) ===
    _r("なかった", "ない", {"v1", "v5", "vs", "vk", "adj-i"},
       "negative-past chain", rules_in={"adj-i"}),
    _r("ません",   "ます", {"v1", "v5", "vs", "vk"},
       "polite-negative chain"),
    _r("ました",   "ます", {"v1", "v5", "vs", "vk"},
       "polite-past chain"),
    _r("ませんでした", "ます", {"v1", "v5", "vs", "vk"},
       "polite-negative-past chain"),

    # === te-iru contractions ===
    _r("ている", "る",  {"v1"}, "te-iru (ichidan)"),
    _r("ていた", "る",  {"v1"}, "te-ita (ichidan)"),
    _r("てる",   "る",  {"v1"}, "te-ru contraction (ichidan)"),
    _r("てた",   "る",  {"v1"}, "te-ta contraction (ichidan)"),

    # === imperative ===
    _r("ろ",   "る",  {"v1"},  "imperative (ichidan)"),
    _r("け",   "く",  {"v5"},  "imperative (godan-ku)"),
    _r("げ",   "ぐ",  {"v5"},  "imperative (godan-gu)"),
    _r("せ",   "す",  {"v5"},  "imperative (godan-su)"),
    _r("て",   "つ",  {"v5"},  "imperative (godan-tsu)"),
    _r("え",   "う",  {"v5"},  "imperative (godan-u)"),
    _r("べ",   "ぶ",  {"v5"},  "imperative (godan-bu)"),
    _r("め",   "む",  {"v5"},  "imperative (godan-mu)"),
    _r("れ",   "る",  {"v5"},  "imperative (godan-ru)"),
    _r("ね",   "ぬ",  {"v5"},  "imperative (godan-nu)"),
]
# fmt: on


_MAX_CHAIN_DEPTH = 4


def deinflect(term: str) -> list[DeinflectionCandidate]:
    """Generate all possible dictionary form candidates for *term*.

    Returns a list of candidates including the original term itself.
    Candidates should be validated against a dictionary by the caller;
    many candidates will be spurious.
    """
    if not term:
        return []

    results: list[DeinflectionCandidate] = [
        DeinflectionCandidate(term=term, word_types=frozenset(), reasons=()),
    ]
    seen: set[str] = {term}

    i = 0
    while i < len(results):
        current = results[i]
        depth = len(current.reasons)
        if depth >= _MAX_CHAIN_DEPTH:
            i += 1
            continue

        for rule in DEINFLECTION_RULES:
            if not _rule_matches(current, rule):
                continue

            new_term = current.term[: -len(rule.kana_in)] + rule.kana_out
            if not new_term or new_term in seen:
                continue
            seen.add(new_term)

            results.append(
                DeinflectionCandidate(
                    term=new_term,
                    word_types=rule.rules_out,
                    reasons=current.reasons + (rule.name,),
                )
            )

        i += 1

    return results


def _rule_matches(candidate: DeinflectionCandidate, rule: DeinflectionRule) -> bool:
    """Check whether *rule* can be applied to *candidate*."""
    # Suffix must match. The term must be at least as long as the suffix
    # (allowing exact matches for suru/kuru where the stem is empty).
    if not candidate.term.endswith(rule.kana_in):
        return False
    if len(candidate.term) < len(rule.kana_in):
        return False

    # Type constraint: if the rule requires specific input types and the
    # candidate already has types assigned (i.e. it's an intermediate
    # form from a previous deinflection), check compatibility.
    if rule.rules_in:
        if candidate.word_types and not (candidate.word_types & rule.rules_in):
            return False

    return True


def deinflect_to_validated(
    term: str,
    word_exists: Callable[[str], bool],
) -> str | None:
    """Return the first dictionary-validated deinflection of *term*, or None.

    Tries candidates in order (shortest deinflection chain first) and
    returns the first one that passes *word_exists* validation.  Skips
    the original term itself so this only returns true deinflections.
    """
    candidates = deinflect(term)
    for candidate in candidates[1:]:  # skip original term
        if word_exists(candidate.term):
            return candidate.term
    return None
