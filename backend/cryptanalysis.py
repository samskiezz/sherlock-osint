"""Bounded, deterministic transformations. Outputs are experiments, never authenticated messages."""

import base64
import codecs
import html
import math
import random
import re
import string
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import unquote

VERSION = "1.1"
METHODS = {
    "hex": "Hexadecimal → UTF-8",
    "base64": "Base64 → UTF-8",
    "base32": "Base32 → UTF-8",
    "base85": "Base85 → UTF-8",
    "ascii85": "Ascii85 → UTF-8",
    "binary": "Binary bytes",
    "octal": "Octal bytes",
    "decimal": "Decimal bytes",
    "rot": "Caesar / ROT",
    "rot47": "ROT47",
    "atbash": "Atbash",
    "vigenere": "Vigenère decrypt",
    "beaufort": "Beaufort",
    "affine": "Affine decrypt",
    "rail_fence": "Rail fence decrypt",
    "columnar": "Keyed columnar decrypt",
    "morse": "Morse decode",
    "a1z26": "A1Z26",
    "polybius": "Polybius 5×5",
    "bacon": "Bacon 26-letter",
    "xor": "Repeating-key XOR (hex input)",
    "url": "URL percent decode",
    "html": "HTML entities",
    "unicode_escape": "Unicode escape decode",
    "nfkc": "Unicode NFKC",
    "reverse": "Reverse characters",
    "reverse_words": "Reverse word order",
    "acrostic": "Word initials",
    "telestich": "Word final letters",
    "line_initials": "Line initials",
    "line_finals": "Line final letters",
    "word_lengths": "Word-length sequence",
    "nth_letters": "Nth letter of each word",
    "frequency": "Frequency / coincidence analysis",
    "scrabble": "Scrabble rack / anagrams",
    "snowflake": "X-format Snowflake timestamp",
    "unix": "Unix seconds",
    "unix_ms": "Unix milliseconds",
    "hex_encode": "UTF-8 → hex",
    "base64_encode": "UTF-8 → Base64",
    "binary_encode": "UTF-8 → binary",
}
# Additional algorithms keep their assumptions and normalisation explicit.
from .extended_ciphers import METHODS as EXTRA_METHODS

METHODS.update(EXTRA_METHODS)

# Small original curated English lexicon; callers may supply their own reproducible dictionary.
WORDS = """a i an as at be by do go he if in is it me my no of on or so to up us we act add age ago air all and any ape arc are arm art ask ate bad bag bar bat bay bed bee beg bet big bit boa bog boo bot bow box boy bus but buy cab can cap car cat cod cog con cop cot cow cry cub cue cup cut dad day den dew did die dig dim dip dog dot dry due dug dye ear eat eel egg ego elf elk end era eve eye fan far fat fax fee few fig fin fit fix fly fog for fox fun fur gap gas gem get gig gin god got gum gun gut guy gym had ham has hat hay hen her hey hid him hip his hit hog hop hot how hub hue hug hum hut ice ill ink inn ion ire its ivy jam jar jaw jet job jog joy jug key kid kin kit lab lag lap law lay led leg let lid lie lip lit log lot low mad man map mat may men met mix mob mod mop mud mug nap net new nil nip nod nor not now nut oak odd off oil old one orb ore our out owe owl own pad pal pan pat paw pay pea peg pen pet pie pig pin pit ply pod pop pot pro pry pub pug pun pup put rag ram ran rap rat raw ray red rib rid rig rim rip rob rod rot row rub rug rum run rye sad sag sap sat saw say sea see set sew she shy sin sip sir sit six ski sky sly sob son sow soy spa spy sub sue sum sun tab tag tan tap tar tax tea ten the tie tin tip toe ton too top toy try tub tug two use van vat vet via vow war was wax way web wed wet who why wig win wit won wow yak yam yap yes yet you zip zoo atom atoms board case cipher code evidence game graph image lab note paper puzzle rack radio rail read research review science source space steam string team test time trace word words world alert alter later art rat tar listen silent enlist tinsel evil vile veil live stone tones notes onset stop pots tops spot post east eats seat teas care race acre angel angle glean triangle integral relating""".split()
SCRABBLE = {
    c: v
    for chars, v in [
        ("aeilnorstu", 1),
        ("dg", 2),
        ("bcmp", 3),
        ("fhvwy", 4),
        ("k", 5),
        ("jx", 8),
        ("qz", 10),
    ]
    for c in chars
}
MORSE = dict(
    zip(
        ".- -... -.-. -.. . ..-. --. .... .. .--- -.- .-.. -- -. --- .--. --.- .-. ... - ..- ...- .-- -..- -.-- --.. ----- .---- ..--- ...-- ....- ..... -.... --... ---.. ----.".split(),
        string.ascii_uppercase + string.digits,
    )
)


def rotate(s, n):
    return "".join(
        chr(
            (ord(c) - ord("A" if c.isupper() else "a") + n) % 26
            + ord("A" if c.isupper() else "a")
        )
        if c.isascii() and c.isalpha()
        else c
        for c in s
    )


def statistics(s):
    counts = Counter(s)
    n = len(s)
    letters = Counter(c.lower() for c in s if c.isascii() and c.isalpha())
    ln = sum(letters.values())
    return {
        "characters": n,
        "entropy": -sum((v / n) * math.log2(v / n) for v in counts.values())
        if n
        else 0,
        "index_of_coincidence": sum(v * (v - 1) for v in letters.values())
        / (ln * (ln - 1))
        if ln > 1
        else 0,
        "frequencies": dict(counts.most_common(128)),
        "bigrams": dict(
            Counter(s[i : i + 2] for i in range(min(max(0, n - 1), 10000))).most_common(
                20
            )
        ),
        "non_ascii": sum(not c.isascii() for c in s),
        "unicode_controls": [
            {
                "offset": i,
                "codepoint": f"U+{ord(c):04X}",
                "name": unicodedata.name(c, "UNKNOWN"),
            }
            for i, c in enumerate(s)
            if unicodedata.category(c) == "Cf"
        ][:100],
    }


def transform(s, method, p=None):
    p = p or {}
    if method in EXTRA_METHODS:
        from .extended_ciphers import run

        return run(s, method, p)
    key = str(p.get("key", "KEY"))
    if method == "hex":
        return bytes.fromhex(s).decode("utf-8")
    if method in ("base64", "base32", "base85", "ascii85"):
        return {
            "base64": lambda x: base64.b64decode(x, validate=True),
            "base32": lambda x: base64.b32decode(x, casefold=True),
            "base85": base64.b85decode,
            "ascii85": base64.a85decode,
        }[method](s.strip()).decode("utf-8")
    if method in ("binary", "octal", "decimal"):
        return bytes(
            int(x, {"binary": 2, "octal": 8, "decimal": 10}[method]) for x in s.split()
        ).decode("utf-8")
    if method == "rot":
        return rotate(s, int(p.get("shift", 13)))
    if method == "rot47":
        return "".join(
            chr(33 + (ord(c) - 33 + 47) % 94) if 33 <= ord(c) <= 126 else c for c in s
        )
    if method == "atbash":
        return "".join(
            rotate(c, 25 - 2 * (ord(c.lower()) - 97))
            if c.isascii() and c.isalpha()
            else c
            for c in s
        )
    if method in ("vigenere", "beaufort"):
        if not re.fullmatch("[A-Za-z]{1,128}", key):
            raise ValueError("Key must contain 1–128 ASCII letters")
        out = []
        i = 0
        for c in s:
            if c.isascii() and c.isalpha():
                k = ord(key[i % len(key)].lower()) - 97
                v = ord(c.lower()) - 97
                out.append(
                    chr(
                        (v - k if method == "vigenere" else k - v) % 26
                        + ord("A" if c.isupper() else "a")
                    )
                )
                i += 1
            else:
                out.append(c)
        return "".join(out)
    if method == "affine":
        a = int(p.get("a", 5))
        b = int(p.get("b", 8))
        inv = pow(a, -1, 26)
        return "".join(
            chr(
                ((ord(c.lower()) - 97 - b) * inv) % 26
                + ord("A" if c.isupper() else "a")
            )
            if c.isascii() and c.isalpha()
            else c
            for c in s
        )
    if method == "rail_fence":
        rails = int(p.get("rails", 3))
        if not 2 <= rails <= 64:
            raise ValueError("Rails must be 2–64")
        route = [
            min(i % (2 * rails - 2), 2 * rails - 2 - i % (2 * rails - 2))
            for i in range(len(s))
        ]
        groups = []
        offset = 0
        for r in range(rails):
            count = route.count(r)
            groups.append(iter(s[offset : offset + count]))
            offset += count
        return "".join(next(groups[r]) for r in route)
    if method == "columnar":
        if not 1 <= len(key) <= 64:
            raise ValueError("Column key must contain 1–64 characters")
        width = len(key)
        cols = {}
        offset = 0
        for c in sorted(range(width), key=lambda i: (key[i], i)):
            size = len(s) // width + (c < len(s) % width)
            cols[c] = s[offset : offset + size]
            offset += size
        return "".join(cols[i % width][i // width] for i in range(len(s)))
    if method == "morse":
        return " ".join(
            "".join(MORSE[x] for x in part.split()) for part in s.split("/")
        )
    if method == "a1z26":
        vals = [int(x) for x in re.split(r"[\s,;-]+", s.strip())]
        if any(not 1 <= v <= 26 for v in vals):
            raise ValueError("A1Z26 values must be 1–26")
        return "".join(chr(64 + v) for v in vals)
    if method == "polybius":
        tokens = s.split()
        alphabet = "ABCDEFGHIKLMNOPQRSTUVWXYZ"
        if any(not re.fullmatch("[1-5]{2}", x) for x in tokens):
            raise ValueError("Use separated pairs 11–55; I/J share one cell")
        return "".join(alphabet[(int(x[0]) - 1) * 5 + int(x[1]) - 1] for x in tokens)
    if method == "bacon":
        letters = re.sub(r"\s", "", s.upper())
        if not re.fullmatch("[AB]+", letters) or len(letters) % 5:
            raise ValueError("Use groups of five A/B symbols")
        nums = [
            int(letters[i : i + 5].replace("A", "0").replace("B", "1"), 2)
            for i in range(0, len(letters), 5)
        ]
        if any(n > 25 for n in nums):
            raise ValueError("Bacon 26-letter alphabet value exceeds 25")
        return "".join(chr(65 + n) for n in nums)
    if method == "xor":
        raw = bytes.fromhex(s)
        k = key.encode()
        if not 1 <= len(k) <= 128:
            raise ValueError("XOR key must be 1–128 bytes")
        return bytes(b ^ k[i % len(k)] for i, b in enumerate(raw)).decode("utf-8")
    if method == "url":
        return unquote(s, errors="strict")
    if method == "html":
        return html.unescape(s)
    if method == "unicode_escape":
        # Preserve existing Unicode; decode only explicit escape sequences.
        return re.sub(
            r"\\(?:u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|x[0-9a-fA-F]{2}|[nrt\\])",
            lambda m: codecs.decode(m[0], "unicode_escape"),
            s,
        )
    if method == "nfkc":
        return unicodedata.normalize("NFKC", s)
    if method == "reverse":
        return s[::-1]
    if method == "reverse_words":
        return " ".join(s.split()[::-1])
    if method == "acrostic":
        return "".join(x[0] for x in s.split())
    if method == "telestich":
        return "".join(x[-1] for x in s.split())
    if method == "line_initials":
        return "".join(x.strip()[0] for x in s.splitlines() if x.strip())
    if method == "line_finals":
        return "".join(x.strip()[-1] for x in s.splitlines() if x.strip())
    if method == "word_lengths":
        return " ".join(str(len(x)) for x in re.findall(r"\b\w+\b", s))
    if method == "nth_letters":
        n = int(p.get("offset", 1))
        if not 1 <= n <= 100:
            raise ValueError("Letter offset must be 1–100")
        return "".join(x[n - 1] for x in s.split() if len(x) >= n)
    if method == "frequency":
        return __import__("json").dumps(statistics(s), ensure_ascii=False, indent=2)
    if method == "scrabble":
        rack = s.lower().strip()
        if not re.fullmatch("[a-z?]{1,30}", rack):
            raise ValueError("Rack accepts 1–30 letters and ? blanks")
        supplied = p.get("dictionary", "")
        if len(supplied) > 100000:
            raise ValueError("Dictionary exceeds 100,000 characters")
        words = set(supplied.lower().split() if supplied else WORDS)
        available = Counter(rack)
        blanks = available.pop("?", 0)
        found = []
        for word in words:
            if not re.fullmatch("[a-z]{1,30}", word):
                continue
            need = Counter(word)
            missing = sum(max(0, n - available[c]) for c, n in need.items())
            if missing <= blanks and (
                not p.get("exact", False) or len(word) == len(rack)
            ):
                score = sum(min(n, available[c]) * SCRABBLE[c] for c, n in need.items())
                found.append(
                    {"word": word, "tile_score": score, "blank_tiles_used": missing}
                )
        return __import__("json").dumps(
            sorted(found, key=lambda x: (-x["tile_score"], -len(x["word"]), x["word"]))[
                :250
            ],
            indent=2,
        )
    if method in ("snowflake", "unix", "unix_ms"):
        n = int(s.strip())
        if method == "snowflake":
            if not 0 <= n < 2**64:
                raise ValueError("Snowflake requires an unsigned 64-bit identifier")
            n = ((n >> 22) + 1288834974657) / 1000
        elif method == "unix_ms":
            n /= 1000
        return datetime.fromtimestamp(n, timezone.utc).isoformat()
    if method == "hex_encode":
        return s.encode().hex()
    if method == "base64_encode":
        return base64.b64encode(s.encode()).decode()
    if method == "binary_encode":
        return " ".join(f"{x:08b}" for x in s.encode())
    raise ValueError("Method unavailable")


def readability(s):
    # Exploratory English-only measure, not a calibrated probability of a message.
    tokens = re.findall("[a-z]+", s.lower())
    n = len(s)
    printable = sum(c.isprintable() or c.isspace() for c in s) / max(1, n)
    known = sum(t in WORDS for t in tokens) / max(1, len(tokens))
    return round(printable * known, 6)


def screen(s, seed=0):
    s = s[:4000]
    specs = [
        (m, {})
        for m in [
            "hex",
            "base64",
            "base32",
            "base85",
            "binary",
            "octal",
            "decimal",
            "morse",
            "a1z26",
            "atbash",
            "rot47",
            "reverse",
            "acrostic",
            "telestich",
            "line_initials",
            "line_finals",
            "word_lengths",
            "url",
            "html",
            "unicode_escape",
            "nfkc",
        ]
    ]
    specs += [("rot", {"shift": i}) for i in range(1, 26)]
    specs += [
        (m, {})
        for m in (
            "caesar_scan",
            "affine_scan",
            "vigenere_periods",
            "kasiski",
            "friedman",
        )
    ]
    attempts = []
    rng = random.Random(seed)
    for method, p in specs:
        try:
            output = transform(s, method, p)
            if method in (
                "caesar_scan",
                "affine_scan",
                "vigenere_periods",
                "kasiski",
                "friedman",
            ):
                analysis = __import__("json").loads(output)
                attempts.append(
                    {
                        "method": method,
                        "parameters": p,
                        "status": "ANALYSIS",
                        "output": output,
                        "parameter_trials": analysis.get("attempts", 0),
                        "controls": [],
                        "readability": None,
                        "empirical_p": None,
                        "adjusted_p": None,
                        "warning": "Exploratory classical analysis; negative controls/holdout not run for this analysis.",
                    }
                )
                continue
            score = readability(output)
            controls = []
            for _ in range(19):
                chars = list(s)
                rng.shuffle(chars)
                try:
                    controls.append(readability(transform("".join(chars), method, p)))
                except (ValueError, KeyError, UnicodeError, OverflowError):
                    controls.append(None)
            valid = [x for x in controls if x is not None]
            empirical = (
                (1 + sum(x >= score for x in valid)) / (1 + len(valid))
                if valid
                else None
            )
            attempts.append(
                {
                    "method": method,
                    "parameters": p,
                    "status": "OUTPUT",
                    "output": output,
                    "readability": score,
                    "controls": controls,
                    "empirical_p": empirical,
                    "adjusted_p": min(1, empirical * len(specs))
                    if empirical is not None
                    else None,
                }
            )
        except (ValueError, KeyError, UnicodeError, OverflowError) as ex:
            attempts.append(
                {
                    "method": method,
                    "parameters": p,
                    "status": "FAILED",
                    "reason": str(ex)[:180],
                }
            )
    return {
        "engine_version": VERSION,
        "input": s,
        "input_truncated": False,
        "seed": seed,
        "attempt_count": len(attempts)
        + sum(a.get("parameter_trials", 0) for a in attempts),
        "rule_count": len(attempts),
        "parameter_trials": sum(a.get("parameter_trials", 0) for a in attempts),
        "attempts": attempts,
        "validation": "UNVALIDATED",
        "warning": "Exploratory English lexicon score. Shuffled controls preserve characters, not language structure; 19 controls cannot establish significance across multiple rule and parameter trials. No authentication, holdout, attribution or prediction has been established.",
    }
