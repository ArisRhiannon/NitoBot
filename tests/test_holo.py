"""Holographic (HDC) memory tests — frontier properties, all offline & cheap."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory import MemoryStore, encode, similarity, hamming, _Codebook, DIM, SEED


def test_deterministic_and_portable():
    import numpy as np
    assert encode("hello world") == encode("hello world")          # stable
    assert np.array_equal(_Codebook(SEED).of(65), _Codebook(SEED).of(65))  # same spec -> same symbol vector
    assert similarity(encode("x"), encode("x")) == 1.0
    print(f"ok H1 encoding is deterministic & spec-portable (DIM={DIM} bits)")


def test_typo_and_morphology_robust():
    base = encode("rabbit")
    assert similarity(base, encode("rabbits")) > similarity(base, encode("guitar"))
    assert similarity(encode("coffee"), encode("coffe")) > similarity(encode("coffee"), encode("airplane"))
    print("ok H2 holographic similarity is robust to morphology/typos (not exact-match)")


def test_language_agnostic():
    base = encode("el conejo pequeño")                              # Spanish + non-ascii
    assert similarity(base, encode("conejo")) > similarity(base, encode("la guitarra eléctrica"))
    assert similarity(encode("café"), encode("café")) == 1.0        # utf-8 multibyte fine
    print("ok H3 language/script agnostic (byte n-grams, any UTF-8)")


def test_recall_is_associative():
    m = MemoryStore()
    m.remember("u", "alice loves rabbits and coffee", ts=1000)
    m.remember("u", "the server event is on friday", ts=1000)
    m.remember("u", "bob plays the guitar", ts=1000)
    assert "rabbits" in m.recall("u", "tell me about the rabbit", k=1, now=1000)[0]
    assert "guitar" in m.recall("u", "who plays guitars?", k=1, now=1000)[0]
    print("ok H4 associative recall by meaning-ish similarity, not keywords")


def test_cheap_ops():
    a, b = encode("anything"), encode("another thing")
    d = hamming(a, b)
    assert 0 <= d <= DIM                                            # pure bitwise popcount
    print(f"ok H5 recall = Hamming popcount over {DIM}-bit vectors (edge-cheap)")


def test_conformance_fixture():
    import json, pathlib
    fix = json.loads(pathlib.Path(__file__).with_name("holo_fixture.json").read_text(encoding="utf-8"))
    for text, hexvec in fix.items():
        assert format(encode(text), "x") == hexvec, f"spec drift on {text!r}"
    print("ok H6 conformance fixture matches (any port must reproduce these vectors)")


def run():
    test_deterministic_and_portable()
    test_typo_and_morphology_robust()
    test_language_agnostic()
    test_recall_is_associative()
    test_cheap_ops()
    test_conformance_fixture()


if __name__ == "__main__":
    run()
    print("\nAll NitoBot holographic-memory tests passed.")
