"""Static evidence parser. Runs only inside the locked-down processing image."""

import argparse, hashlib, json, os, re, resource, socket, subprocess
from pathlib import Path
import fitz
from PIL import Image, ExifTags
from bs4 import BeautifulSoup
import sys

sys.path.insert(0, "/app")
from image_analysis import diagnostics
from document_analysis import enrich_html

MAX_RESULT = 16 * 1024 * 1024
MAX_TEXT = 8 * 1024 * 1024


def extract(path, mime, der):
    e = {"mime": mime, "size": path.stat().st_size}
    meta = {}
    text = ""
    preview = None
    if e["mime"] == "application/json":
        data = json.loads(path.read_bytes())
        text = json.dumps(data, indent=2, ensure_ascii=False)
        meta["json_keys"] = list(data)[:50] if isinstance(data, dict) else []
        meta["static_only"] = True
    elif e["mime"] == "application/pdf":
        with fitz.open(path) as doc:
            meta["page_count"] = len(doc)
            meta["document_metadata"] = doc.metadata
            meta["pages"] = []
            for i, page in enumerate(doc):
                if i >= 500:
                    meta["extraction_truncated"] = True
                    break
                t = page.get_text()
                if not t.strip() and i < 2:
                    pixels = page.rect.width * page.rect.height * 2.25
                    if pixels < 10_000_000:
                        ocr_image = der / f"ocr-page-{i + 1}.png"
                        page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(ocr_image)
                        try:
                            ocr = subprocess.run(
                                ["tesseract", str(ocr_image), "stdout"],
                                capture_output=True,
                                text=True,
                                timeout=15,
                            )
                            if ocr.returncode == 0:
                                t = ocr.stdout
                                meta.setdefault("ocr_pages", []).append(i + 1)
                        except (FileNotFoundError, subprocess.TimeoutExpired):
                            pass
                        finally:
                            ocr_image.unlink(missing_ok=True)
                text += f"\n[Page {i + 1}]\n{t}"
                meta["pages"].append(
                    {
                        "page": i + 1,
                        "text": t,
                        "blocks": [
                            {"bbox": list(b[:4]), "text": b[4]}
                            for b in page.get_text("blocks")[:200]
                            if len(b) > 4
                        ],
                    }
                )
            if len(doc) and doc[0].rect.width * doc[0].rect.height * 0.64 < 10_000_000:
                preview = str(der / "preview.png")
                doc[0].get_pixmap(matrix=fitz.Matrix(0.8, 0.8)).save(preview)
    elif e["mime"].startswith("image/"):
        with Image.open(path) as im:
            if im.width * im.height > 40_000_000:
                raise ValueError("Image exceeds pixel limit")
            meta["image_forensics"] = diagnostics(im, path, der)
            from visual_features import features
            meta["visual_features"] = features(im, der)
            meta["dimensions"] = [im.width, im.height]
            meta["format"] = im.format
            meta["exif"] = {
                ExifTags.TAGS.get(k, str(k)): str(v) for k, v in im.getexif().items()
            }
            meta["histogram"] = im.convert("RGB").resize((256, 256)).histogram()
            gray = im.convert("L").resize((8, 8))
            values = list(gray.get_flattened_data())
            average = sum(values) / 64
            meta["average_hash"] = (
                f"{sum((v > average) << i for i, v in enumerate(values)):016x}"
            )
            im.thumbnail((900, 700))
            preview = str(der / "preview.png")
            im.convert("RGB").save(preview)
        try:
            p = subprocess.run(
                ["tesseract", str(path), "stdout"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            text = p.stdout
            meta["ocr"] = {"engine": "tesseract", "return_code": p.returncode}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            meta["ocr"] = {"status": "unavailable"}
    elif e["mime"].startswith(("video/", "audio/")):
        p = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        meta["media_probe"] = json.loads(p.stdout or "{}")
        meta["transcript_status"] = "Not generated; speech model not configured"
        if e["mime"].startswith("video/"):
            preview = str(der / "preview.png")
            p = subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-y",
                    "-i",
                    str(path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=640:-1",
                    preview,
                ],
                capture_output=True,
                timeout=30,
            )
            if p.returncode != 0:
                preview = None
    elif "html" in e["mime"]:
        soup = BeautifulSoup(path.read_bytes(), "html.parser")
        meta.update(enrich_html(soup))
        meta["links"] = [
            {
                "href": str(a.get("href", ""))[:3000],
                "label": a.get_text(" ", strip=True)[:200],
                "type": str(a.get("type", ""))[:100],
            }
            for a in soup.find_all("a", href=True)[:400]
        ]
        for n in soup(["script", "style", "nav"]):
            n.decompose()
        text = soup.get_text("\n", strip=True)
        meta["document_title"] = soup.title.get_text() if soup.title else None
    elif e["mime"].startswith("text/") or e["size"] < 2_000_000:
        data = path.read_bytes()
        text = data.decode("utf-8", "replace")
        meta["static_only"] = True
        meta["printable_strings"] = re.findall(r"[\x20-\x7e]{6,}", text)[:200]
    else:
        meta["processor_status"] = "No compatible processor enabled"
    if len(text.encode()) > MAX_TEXT:
        text = text.encode()[:MAX_TEXT].decode("utf-8", "ignore")
        meta["extraction_truncated"] = True
    return {"text": text, "metadata": meta, "preview": bool(preview)}


def probe(path, der):
    readonly = False
    try:
        with path.open("ab") as f:
            f.write(b"probe")
    except OSError:
        readonly = True
    network_blocked = False
    try:
        with socket.create_connection(("1.1.1.1", 80), timeout=1):
            pass
    except OSError:
        network_blocked = True
    return {
        "text": "Sandbox enforcement probe",
        "metadata": {
            "probe": {
                "input_read_only": readonly,
                "network_blocked": network_blocked,
                "host_vault_absent": not Path(
                    "/workspace/sherlock-osint/data/case.db"
                ).exists(),
                "root_read_only": not os.access("/usr", os.W_OK),
                "uid": os.getuid(),
            }
        },
        "preview": False,
    }


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    parser = argparse.ArgumentParser()
    parser.add_argument("--mime", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    source = Path("/input/original")
    der = Path("/output")
    if hashlib.sha256(source.read_bytes()).hexdigest() != args.sha256:
        raise ValueError("Input hash does not match preservation record")
    result = probe(source, der) if args.probe else extract(source, args.mime, der)
    if hashlib.sha256(source.read_bytes()).hexdigest() != args.sha256:
        raise ValueError("Original bytes changed during processing")
    encoded = json.dumps(result).encode()
    if len(encoded) > MAX_RESULT:
        raise ValueError("Extraction result exceeds 16 MB limit")
    (der / "text.txt").write_text(result["text"])
    (der / "result.json").write_bytes(encoded)
    print(json.dumps({"status": "complete", "characters": len(result["text"])}))


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(json.dumps({"status": "failed", "error": str(ex)[:1500]}))
        raise SystemExit(1)
