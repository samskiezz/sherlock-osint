import io
import json
import zipfile
import fitz
from xml.etree import ElementTree as ET
from backend.reports import pdf, docx


def fixture():
    return {
        "exported": "2026-10-14T00:00:00Z",
        "evidence": [
            {
                "id": "EV-TEST",
                "title": "Matériaux & <alloy>",
                "status": "ORIGINAL VERIFIED",
                "url": "https://example.org/doc",
                "mime": "application/pdf",
                "size": 42,
                "sha256": "a" * 64,
            },
            {
                "id": "NOTE",
                "title": "Secondary hypothesis",
                "status": "SECONDARY SOURCE",
                "mime": "text/plain",
                "size": 0,
            },
        ],
        "boards": [
            {
                "id": "B",
                "name": "Fixture",
                "edges": [
                    {
                        "source": "N1",
                        "target": "N2",
                        "data": {
                            "state": "HYPOTHESIS",
                            "claim": "Not proved",
                            "evidence": [
                                {
                                    "id": "EV-TEST",
                                    "quote": "Specific source passage",
                                    "location": "page 3",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
        "jobs": [
            {
                "id": "JOB",
                "status": "ACQUISITION FAILED",
                "url": "https://example.org/missing",
                "error": "HTTP 404",
            }
        ],
        "analytic_records": [
            {
                "id": "A",
                "created": "UTC",
                "method": "mad",
                "data": json.dumps(
                    {
                        "validation": "PROVISIONAL",
                        "output": {"warning": "Not a finding"},
                        "citations": [
                            {
                                "evidence_id": "EV-TEST",
                                "quote": "Specific source passage",
                                "page": 3,
                                "sha256": "a" * 64,
                            }
                        ],
                    }
                ),
            }
        ],
        "method_registry": [
            {
                "data": json.dumps(
                    {"name": "Lab examination", "implementation": "NOT IMPLEMENTED"}
                )
            }
        ],
    }


def test_pdf_readable_paginated_and_preserves_uncertainty_and_source_hash():
    value = fixture()
    report = pdf(value)
    with fitz.open(stream=report, filetype="pdf") as document:
        text = "\n".join(p.get_text() for p in document)
        assert document.page_count >= 1
    for required in (
        "EV-TEST",
        "Specific source passage",
        "PROVISIONAL",
        "HYPOTHESIS",
        "HTTP 404",
        "a" * 64,
        "NOT IMPLEMENTED",
        "Latin transliteration",
    ):
        assert required in text
    value["evidence"] *= 100
    with fitz.open(stream=pdf(value), filetype="pdf") as document:
        assert document.page_count > 5
        assert "page 2" in document[1].get_text()


def test_docx_valid_openxml_unicode_escape_and_no_macro_or_remote_content():
    with zipfile.ZipFile(io.BytesIO(docx(fixture()))) as z:
        assert set(z.namelist()) == {
            "[Content_Types].xml",
            "_rels/.rels",
            "word/document.xml",
        }
        doc = ET.fromstring(z.read("word/document.xml"))
        text = " ".join(doc.itertext())
        assert "Matériaux & <alloy>" in text and "Specific source passage" in text
        assert "ORIGINAL VERIFIED" in text and "SECONDARY SOURCE" in text
        relationships = ET.fromstring(z.read("_rels/.rels"))
        assert all(r.attrib.get("TargetMode") != "External" for r in relationships)
