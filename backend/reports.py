"""Local PDF/DOCX audit reports; no generated factual narrative or remote service."""

import io
import json
from typing import Any
import textwrap
import unicodedata
import zipfile
from html import escape


def paragraphs(payload: dict[str, Any]) -> list[str]:
    """Render stored evidence and uncertainty into report paragraphs."""
    result = [
        "SHERLOCK OSINT — PROJECT LOOKING GLASS",
        "Evidence and investigation audit report",
        "Exported UTC: " + payload["exported"],
        "This report records stored evidence, acquisition states, cited board relationships and provisional analyses. It is not a determination of guilt or independent authentication of source assertions.",
        "Original files are retained in the local vault; this report does not embed them. Full structured records and execution traces are available in the JSON case export. Quotes and individual analytical results exceeding 3,000 characters are explicitly abbreviated below. Secondary notes are not original evidence.",
    ]
    ev = payload["evidence"]
    result.append(
        f"Evidence inventory: {len(ev)} records; {sum(bool(e.get('sha256')) for e in ev)} records with preserved original hashes."
    )
    for e in ev:
        result.extend(
            [
                f"{e['id']} | {e['title']}",
                f"Status: {e['status']} | MIME: {e.get('mime')} | bytes: {e.get('size')}",
                "Source URL: " + str(e.get("url") or "User-supplied/secondary record"),
                "SHA-256: " + str(e.get("sha256") or "No original hash"),
            ]
        )
    result.append(
        "Board relationships — states are stored assessments, not new verified conclusions"
    )
    for b in payload["boards"]:
        result.append("Board: " + str(b.get("name", b["id"])))
        for edge in b.get("edges", []):
            data = edge.get("data", {})
            result.append(
                f"{edge['source']} → {edge['target']} | {edge.get('label', 'Relationship')} | {data.get('state', 'UNVERIFIED')}"
            )
            result.append(str(data.get("claim", "")))
            for c in data.get("evidence", []):
                quote = str(c.get("quote", ""))
                result.append(
                    f"Source {c.get('id')} | {c.get('location', 'Location not recorded')} | "
                    + clip(quote)
                )
    result.append("Acquisition failures and incomplete work")
    for j in payload["jobs"]:
        if j.get("status") not in ("COMPLETE",):
            result.append(
                f"{j['id']} | {j.get('status')} | {j.get('url')} | {j.get('error') or 'No failure reason; pending/active state'}"
            )
    result.append("Saved analyses — provisional, human review required")
    for row in payload.get("analytic_records", []):
        data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        result.append(
            f"{row['id']} | method {row['method']} | {row['created']} | {data.get('validation')}"
        )
        result.append(
            "Output: " + clip(json.dumps(data.get("output", {}), ensure_ascii=False))
        )
        for c in data.get("citations", []):
            result.append(
                f"Source {c.get('evidence_id')} | page {c.get('page') or 'not specified'} | SHA-256 {c.get('sha256')} | "
                + clip(str(c.get("quote", "")))
            )
        if data.get("notes"):
            result.append("Investigator notes: " + clip(data["notes"]))
    result.append(
        "Method execution status — pending taxonomy entries are not capabilities"
    )
    for row in payload.get("method_registry", []):
        m = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        result.append(f"{m['name']} | {m['implementation']}")
    # Strip forbidden XML/control characters in user-supplied fields.
    return [
        "".join(c for c in str(p) if c in "\n\t" or ord(c) >= 32) for p in result if p
    ]


def clip(value: str) -> str:
    """Disclose abbreviation of oversized values."""
    return (
        value
        if len(value) <= 3000
        else value[:3000] + " [ABBREVIATED: full record in JSON export]"
    )


def docx(payload: dict[str, Any]) -> bytes:
    """Generate an escaped Unicode OpenXML report without remote content."""
    body = "".join(
        '<w:p><w:r><w:t xml:space="preserve">' + escape(p) + "</w:t></w:r></w:p>"
        for p in paragraphs(payload)
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + body
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr></w:body></w:document>'
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        z.writestr("word/document.xml", document.encode("utf-8"))
    return stream.getvalue()


def pdf(payload: dict[str, Any]) -> bytes:
    """Generate a paginated PDF audit report using the bundled font."""
    import fitz

    doc = fitz.open()
    # Use the bundled font; PDF text uses Latin transliteration, DOCX retains Unicode.
    all_lines = [
        "PDF text uses Latin transliteration for unsupported characters. DOCX/JSON preserve Unicode.",
        "",
    ]
    for p in paragraphs(payload):
        p = p.replace("→", " -> ").replace("—", " - ").replace("’", "'")
        p = unicodedata.normalize("NFKD", p).encode("ascii", "replace").decode("ascii")
        all_lines.extend(textwrap.wrap(p, width=95, replace_whitespace=True) or [""])
        all_lines.append("")
    for offset in range(0, len(all_lines), 64):
        page = doc.new_page(width=595, height=842)
        page.insert_text(
            (36, 42),
            "\n".join(all_lines[offset : offset + 64]),
            fontname="cour",
            fontsize=9,
            lineheight=1.25,
        )
        page.insert_text(
            (36, 815),
            f"PROJECT LOOKING GLASS | page {offset // 64 + 1}",
            fontname="cour",
            fontsize=8,
        )
    data = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return data
