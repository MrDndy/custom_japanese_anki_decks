"""Manual Test 5: Lookup Service

Component: LookupService (lookup_service.py)

What to check:
  - Particles (は, と, に) are filtered out
  - Verbs are lemmatized to dictionary form (食べる, 行く)
  - Content words (昨日, 友達) are preserved
  - Readings and meanings populated (if dictionary is installed)
  - Processing time is reasonable (<100ms after warm-up)

Runs in the terminal — no GUI needed.
"""
from __future__ import annotations

from jp_anki_builder.lookup_service import LookupService

print("=" * 50)
print("Test 5: Lookup Service")
print("=" * 50)

sentences = [
    "昨日は友達と食べに行った",
    "日本語を勉強している",
    "この本はとても面白い",
]

with LookupService(data_dir="data") as svc:
    for sentence in sentences:
        print(f"\nInput: {sentence}")
        resp = svc.lookup(sentence)
        if resp.words:
            for w in resp.words:
                jlpt = f" [{w.jlpt_level}]" if w.jlpt_level else ""
                reading = f" ({w.reading})" if w.reading else ""
                meanings = f" — {'; '.join(w.meanings)}" if w.meanings else ""
                db_flag = " [in DB]" if w.is_in_vocab_db else ""
                print(f"  {w.surface} → {w.dictionary_form}{reading}{jlpt}{meanings}{db_flag}")
        else:
            print("  (no words after filtering)")
        print(f"  [{resp.processing_time_ms:.1f}ms]")

        # Check particles are filtered
        lemmas = {w.dictionary_form for w in resp.words}
        for particle in ("は", "と", "に", "を"):
            if particle in lemmas:
                print(f"  WARNING: particle '{particle}' was NOT filtered!")

print("\nDone.")
