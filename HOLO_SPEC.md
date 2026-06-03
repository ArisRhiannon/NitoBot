# NitoBot Holographic Memory — encoding spec (v1)

Any implementation in any language that follows this spec produces **byte-identical**
hypervectors, so memories are interoperable across NitoBot forks and runtimes. The
algorithm is pure bitwise Hyperdimensional Computing (HDC/VSA) — no model, no training.

## Parameters
- `DIM = 8192` (bits per hypervector), `NGRAM = 3`, `SEED = "nito-hdc-v1"`.

## Symbol vector — one per byte value `b` (0..255)
1. `material = SHA256(SEED_utf8 ‖ b ‖ u32be(0)) ‖ SHA256(SEED_utf8 ‖ b ‖ u32be(1)) ‖ …`
   until `len ≥ DIM/8` bytes; take the first `DIM/8 = 1024` bytes. **Every** block appends
   the big-endian u32 counter, starting at `ctr = 0`.
2. Unpack those bytes to `DIM` bits, **MSB-first within each byte**: bit `8*i + k` of the
   vector = bit `(7-k)` of byte `i`.

## Encoding a text → hypervector
1. `data = UTF-8 bytes of text` (use `0x00` if empty).
2. Trigrams: `grams = [data[i:i+3] for i in 0 .. max(1, len-2))]`.
3. For each gram, bind its symbols with their position by **circular left-shift** (toward
   higher index, wrap-around) by the position `pos = 0,1,2`, then **XOR** them:
   `gram_vec = roll(sym[g0],0) ^ roll(sym[g1],1) ^ roll(sym[g2],2)`.
4. **Bundle** by majority: count set bits per dimension over all gram vectors; dimension `d`
   is `1` iff `2 * count[d] > len(grams)` (strict majority; ties → 0).
5. Pack the `DIM` bits MSB-first into `DIM/8` bytes — this is the hypervector.

## Comparison
- `hamming(a, b) = popcount(a XOR b)`; `similarity = 1 - hamming/DIM`.
- Recall = nearest stored vector by Hamming (ties broken by recency, weight 0.05).

## Conformance vector
`encode("nito")` must be identical across implementations. The fixture
(`tests/holo_fixture.json`: text → hex vector) is generated from the Python reference;
`native/holo.c` is a second, independent implementation that reproduces it byte-for-byte
(`tests/test_native.py` checks this when a C compiler is present).

## Cost (honest)
Encoding is `O(len(text) · DIM)` — for a ~70-char message at DIM=8192 that is ~0.5M bit
ops: ≈2.6 ms in Python/numpy and ≈2.3 ms in the (unoptimized, faithful) C reference. It is
**not** sub-microsecond at this size; sub-ms needs a smaller DIM or short inputs. The point
of the native reference is portability and a numpy-free, microcontroller-capable build, not
raw speed at DIM=8192.
