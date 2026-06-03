"""Cross-language conformance: the C reference must produce identical hypervectors.
Skipped cleanly when no C compiler is available."""
import sys, os, json, shutil, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory import encode

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "native", "holo.c")


def test_c_reference_matches_python():
    cc = shutil.which("cc") or shutil.which("gcc")
    if not cc or not os.path.exists(SRC):
        print("ok N1 (skipped: no C compiler or native/holo.c)")
        return
    binp = os.path.join(tempfile.mkdtemp(), "holo")
    subprocess.run([cc, "-O2", "-o", binp, SRC], check=True)
    fix = json.load(open(os.path.join(HERE, "holo_fixture.json"), encoding="utf-8"))
    texts = list(fix)
    out = subprocess.run([binp, *texts], capture_output=True, text=True, check=True).stdout.split()
    for t, chex in zip(texts, out):
        assert int(chex, 16) == encode(t), f"C/Python mismatch on {t!r}"
    print(f"ok N1 C reference reproduces all {len(texts)} vectors byte-for-byte")


def run():
    test_c_reference_matches_python()


if __name__ == "__main__":
    run()
    print("\nNitoBot native-conformance test done.")
