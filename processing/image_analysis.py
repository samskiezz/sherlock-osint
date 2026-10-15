"""Bounded image diagnostics, not an authentication or AI-image detector."""

import io, math, statistics
from PIL import Image, ImageChops, ImageEnhance, ImageStat


def diagnostics(image, path, der):
    original_format = image.format
    rgb = image.convert("RGB")
    step = max(1, math.ceil(math.sqrt(rgb.width * rgb.height / 262144)))
    channels = {name: {"ones": 0, "samples": 0} for name in ("red", "green", "blue")}
    for y in range(0, rgb.height, step):
        for x in range(0, rgb.width, step):
            for name, value in zip(channels, rgb.getpixel((x, y))):
                channels[name]["ones"] += value & 1
                channels[name]["samples"] += 1
    for values in channels.values():
        values["one_fraction"] = values["ones"] / max(1, values["samples"])
    display = rgb.copy()
    display.thumbnail((900, 700))
    stats = ImageStat.Stat(display)
    channel_stats = []
    for i, name in enumerate(channels):
        band = display.getchannel(i)
        band.save(der / (name + ".png"))
        hist = band.histogram()
        n = sum(hist)
        channel_stats.append(
            {
                "channel": name,
                "mean": stats.mean[i],
                "standard_deviation": stats.stddev[i],
                "entropy": -sum(v / n * math.log2(v / n) for v in hist if v),
                "extrema": band.getextrema(),
            }
        )
    # Nearest-neighbour preserves selected original channel values for a diagnostic bit plane.
    bitview = (
        rgb.getchannel(0)
        .resize(display.size, Image.Resampling.NEAREST)
        .point(lambda x: 255 if x & 1 else 0)
    )
    bitview.save(der / "lsb.png")

    def recompress(im, quality):
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
        buf.seek(0)
        with Image.open(buf) as copy:
            return copy.convert("RGB")

    baseline = recompress(display, 95)
    diff = ImageChops.difference(display, baseline)
    residual = ImageStat.Stat(diff)
    ImageEnhance.Contrast(diff).enhance(12).save(der / "ela.png")
    controls = []
    for quality in (75, 85, 95):
        benign = recompress(display, quality)
        d = ImageChops.difference(benign, recompress(benign, 95))
        controls.append(
            {
                "initial_quality": quality,
                "second_quality": 95,
                "mean_absolute_residual": ImageStat.Stat(d).mean,
            }
        )
    blocks = []
    for y in range(0, diff.height, 32):
        for x in range(0, diff.width, 32):
            box = (x, y, min(x + 32, diff.width), min(y + 32, diff.height))
            blocks.append(
                {
                    "display_bbox": list(box),
                    "mean_residual": sum(ImageStat.Stat(diff.crop(box)).mean) / 3,
                }
            )
    median = statistics.median(b["mean_residual"] for b in blocks)
    mad = statistics.median(abs(b["mean_residual"] - median) for b in blocks)
    threshold = median + max(1, 6 * mad)
    outliers = sorted(
        (b for b in blocks if b["mean_residual"] > threshold),
        key=lambda b: -b["mean_residual"],
    )[:30]
    flags = []
    if not image.getexif():
        flags.append(
            {
                "indicator": "NO EXIF",
                "interpretation": "Common after export or platform recompression; not evidence of manipulation.",
            }
        )
    for name, v in channels.items():
        if v["one_fraction"] < 0.01 or v["one_fraction"] > 0.99:
            flags.append(
                {
                    "indicator": "LOW LSB VARIATION",
                    "channel": name,
                    "interpretation": "Can occur in graphics, flat regions or quantisation. No payload inferred.",
                }
            )
    if outliers:
        flags.append(
            {
                "indicator": "LOCAL RESIDUAL OUTLIERS",
                "count_displayed": len(outliers),
                "interpretation": "Texture and contrast may explain these regions; compare the original and benign controls.",
            }
        )
    data = path.read_bytes()
    last = data.rfind(b"\xff\xd9") if original_format == "JPEG" else -1
    return {
        "version": "1.0",
        "state": "INDICATORS ONLY",
        "original_format": original_format,
        "display_dimensions": list(display.size),
        "channel_statistics": channel_stats,
        "lsb": {
            "sampling_step": step,
            "channels": channels,
            "view_channel": "red",
            "warning": "Noise-like or balanced bit planes are common in ordinary images; no hidden message was extracted.",
        },
        "jpeg_residual": {
            "quality": 95,
            "display_gain": 12,
            "mean_absolute_residual": residual.mean,
            "benign_recompression_controls": controls,
            "warning": "Display resized before recompression. Texture, edges, rescaling and compression create residuals; this is not a tampering classifier.",
        },
        "anomaly_indicators": flags,
        "residual_regions": {
            "block_size": 32,
            "threshold": threshold,
            "median": median,
            "mad": mad,
            "coordinate_system": "resized diagnostic display",
            "outliers": outliers,
        },
        "jpeg_bytes_after_last_eoi": len(data) - last - 2 if last >= 0 else None,
        "exif_present": bool(image.getexif()),
        "views": ["red", "green", "blue", "lsb", "ela"],
        "limitations": [
            "No calibrated authenticity score",
            "No AI-generation attribution",
            "No proven steganography",
            "EXIF may be absent or edited",
            "No location or face identification",
        ],
        "review_required": True,
    }
