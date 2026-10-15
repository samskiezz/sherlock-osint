"""Apply CyberChef's documented ESM suffix fix without executing dependency hooks."""

from pathlib import Path
import re, hashlib, json

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / "integrations/decoders/node_modules/crypto-api/src"
changed = []
for file in folder.rglob("*.mjs"):
    if file.is_symlink():
        raise RuntimeError("Unexpected symlink in reviewed dependency")
    source = file.read_text()
    updated = re.sub(
        r'from "(\.[^"]*)";',
        lambda m: m.group() if m[1].endswith(".mjs") else 'from "' + m[1] + '.mjs";',
        source,
    )
    if source != updated:
        file.write_text(updated)
        changed.append(
            {
                "file": str(file.relative_to(folder)),
                "before_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "after_sha256": hashlib.sha256(updated.encode()).hexdigest(),
            }
        )
(ROOT / "artifacts/cyberchef-esm-fix-v11.json").write_text(
    json.dumps(changed, indent=2)
)
print(
    "Reviewed ESM suffix fix applied to",
    len(changed),
    "files; no install hooks executed",
)
