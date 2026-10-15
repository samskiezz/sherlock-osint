"""Classical cryptanalysis with disclosed English-language assumptions."""

import json
import math
import re
from collections import Counter, defaultdict

METHODS = {
    "caesar_scan": "Caesar · chi-squared ranking",
    "affine_scan": "Affine · chi-squared ranking",
    "vigenere_periods": "Vigenère · periodic coincidence scan",
    "kasiski": "Kasiski repeated-sequence examination",
    "friedman": "Friedman English key-length estimate",
    "playfair": "Playfair decrypt · I/J square",
    "hill2": "Hill 2×2 decrypt",
    "bifid": "Bifid decrypt",
    "gronsfeld": "Gronsfeld decrypt",
    "autokey": "Vigenère plaintext-autokey decrypt",
    "adfgx": "ADFGX decrypt",
}
ENGLISH = [
    0.08167,
    0.01492,
    0.02782,
    0.04253,
    0.12702,
    0.02228,
    0.02015,
    0.06094,
    0.06966,
    0.00153,
    0.00772,
    0.04025,
    0.02406,
    0.06749,
    0.07507,
    0.01929,
    0.00095,
    0.05987,
    0.06327,
    0.09056,
    0.02758,
    0.00978,
    0.02360,
    0.00150,
    0.01974,
    0.00074,
]


def letters(s):
    return re.sub("[^A-Z]", "", s.upper())


def square(key):
    result = ""
    for c in letters(key).replace("J", "I") + "ABCDEFGHIKLMNOPQRSTUVWXYZ":
        if c not in result:
            result += c
    return result


def chi2(s):
    s = letters(s)
    n = len(s)
    counts = Counter(s)
    return (
        sum((counts[chr(65 + i)] - n * p) ** 2 / (n * p) for i, p in enumerate(ENGLISH))
        if n
        else None
    )


def run(s, m, p):
    from .cryptanalysis import rotate, transform, statistics

    clean = letters(s)
    if m in ("caesar_scan", "affine_scan"):
        if len(clean) < 10:
            raise ValueError(
                "Ranking needs at least 10 ASCII letters; short texts are unreliable"
            )
        candidates = []
        if m == "caesar_scan":
            for shift in range(26):
                out = rotate(s, -shift)
                candidates.append(
                    {"encryption_shift": shift, "output": out, "chi_squared": chi2(out)}
                )
        else:
            for a in range(26):
                if math.gcd(a, 26) != 1:
                    continue
                for b in range(26):
                    out = transform(s, "affine", {"a": a, "b": b})
                    candidates.append(
                        {"a": a, "b": b, "output": out, "chi_squared": chi2(out)}
                    )
        return json.dumps(
            {
                "attempts": len(candidates),
                "candidates": sorted(candidates, key=lambda x: x["chi_squared"])[:30],
                "warning": "English monogram frequency ranking; low scores do not authenticate plaintext. All parameter combinations count as attempts.",
            },
            indent=2,
        )
    if m == "vigenere_periods":
        rows = []
        for period in range(1, min(30, max(1, len(clean) // 2)) + 1):
            values = [
                statistics(clean[i::period])["index_of_coincidence"]
                for i in range(period)
            ]
            rows.append(
                {
                    "period": period,
                    "mean_ic": sum(values) / period,
                    "column_lengths": [len(clean[i::period]) for i in range(period)],
                }
            )
        return json.dumps(
            {
                "candidates": sorted(rows, key=lambda r: -r["mean_ic"]),
                "warning": "Periodic coincidence can reflect language, repeated material or short columns. This is not a recovered key.",
            },
            indent=2,
        )
    if m == "kasiski":
        clean = clean[:10000]
        repeats = []
        factors = Counter()
        for width in (3, 4, 5):
            positions = defaultdict(list)
            for i in range(max(0, len(clean) - width + 1)):
                if len(positions[clean[i : i + width]]) < 20:
                    positions[clean[i : i + width]].append(i)
            for token, offsets in positions.items():
                if len(offsets) < 2:
                    continue
                distances = [b - a for a, b in zip(offsets, offsets[1:])]
                repeats.append(
                    {
                        "sequence": token,
                        "offsets_in_letters_only": offsets,
                        "successive_distances": distances,
                    }
                )
                for d in distances:
                    for n in range(2, 31):
                        if d % n == 0:
                            factors[n] += 1
        return json.dumps(
            {
                "normalised_input": clean,
                "truncated": len(letters(s)) > 10000,
                "repeats": repeats[:100],
                "factor_counts": dict(factors.most_common()),
                "warning": "Repeated sequences may be ordinary words or chance. No key length is proven.",
            },
            indent=2,
        )
    if m == "friedman":
        n = len(clean)
        ic = statistics(clean)["index_of_coincidence"]
        den = (n - 1) * ic - 0.0385 * n + 0.065
        return json.dumps(
            {
                "letters": n,
                "index_of_coincidence": ic,
                "estimated_key_length": 0.0265 * n / den
                if n >= 20 and den > 0
                else None,
                "warning": "English-language Friedman approximation; unsuitable for short/non-English text and not a modern-encryption detector.",
            },
            indent=2,
        )
    if m in ("gronsfeld", "autokey"):
        key = str(p.get("key", ""))
        keyvals = (
            [int(c) for c in key]
            if m == "gronsfeld" and re.fullmatch("[0-9]{1,128}", key)
            else [ord(c) - 65 for c in letters(key)]
            if m == "autokey"
            else []
        )
        if not keyvals:
            raise ValueError("Use a numeric Gronsfeld key or ASCII-letter autokey")
        out = []
        i = 0
        for c in s:
            if c.isascii() and c.isalpha():
                k = keyvals[i % len(keyvals)] if m == "gronsfeld" else keyvals[i]
                value = (ord(c.upper()) - 65 - k) % 26
                out.append(chr(value + ord("A" if c.isupper() else "a")))
                if m == "autokey":
                    keyvals.append(value)
                i += 1
            else:
                out.append(c)
        return "".join(out)
    if m == "hill2":
        numbers = [int(v) for v in str(p.get("key", "")).split(",")]
        if len(numbers) != 4 or len(clean) % 2:
            raise ValueError(
                "Supply four comma-separated matrix values and an even number of letters"
            )
        a, b, c, d = numbers
        inverse = pow(a * d - b * c, -1, 26)
        out = []
        for i in range(0, len(clean), 2):
            x, y = ord(clean[i]) - 65, ord(clean[i + 1]) - 65
            out += [
                chr((inverse * (d * x - b * y)) % 26 + 65),
                chr((inverse * (-c * x + a * y)) % 26 + 65),
            ]
        return "".join(out)
    sq = square(str(p.get("square_keyword", p.get("key", ""))))
    loc = {c: divmod(i, 5) for i, c in enumerate(sq)}
    if m == "playfair":
        clean = clean.replace("J", "I")
        if len(clean) % 2:
            raise ValueError(
                "Playfair requires even-length digraphs; padding is retained"
            )
        out = []
        for i in range(0, len(clean), 2):
            a, b = loc[clean[i]], loc[clean[i + 1]]
            pair = (
                [sq[a[0] * 5 + (a[1] - 1) % 5], sq[b[0] * 5 + (b[1] - 1) % 5]]
                if a[0] == b[0]
                else [sq[((a[0] - 1) % 5) * 5 + a[1]], sq[((b[0] - 1) % 5) * 5 + b[1]]]
                if a[1] == b[1]
                else [sq[a[0] * 5 + b[1]], sq[b[0] * 5 + a[1]]]
            )
            out += pair
        return "".join(out)
    if m == "bifid":
        period = int(p.get("period", 5))
        if not 1 <= period <= 100:
            raise ValueError("Bifid period must be 1–100")
        clean = clean.replace("J", "I")
        out = []
        for offset in range(0, len(clean), period):
            part = clean[offset : offset + period]
            coords = [v for c in part for v in loc[c]]
            n = len(part)
            out += [sq[coords[i] * 5 + coords[n + i]] for i in range(n)]
        return "".join(out)
    if m == "adfgx":
        symbols = re.sub(r"\s", "", s.upper())
        if not re.fullmatch("[ADFGX]+", symbols) or len(symbols) % 2:
            raise ValueError("ADFGX requires an even number of A/D/F/G/X symbols")
        sq = square(str(p.get("square_keyword", "")))
        decoded = transform(symbols, "columnar", {"key": str(p.get("key", "KEY"))})
        chars = "ADFGX"
        return "".join(
            sq[chars.index(decoded[i]) * 5 + chars.index(decoded[i + 1])]
            for i in range(0, len(decoded), 2)
        )
    raise ValueError("Unknown classical method")
