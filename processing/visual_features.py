"""Established image signatures and ORB feature descriptors for comparison, never identity."""

import base64
import imagehash
import cv2
import numpy as np
from PIL import ImageFilter, ImageOps


def features(image, der):
    """Extract bounded signatures and multi-scale views from actual decoded source pixels."""
    cv2.setNumThreads(1)
    im = ImageOps.exif_transpose(image).convert("RGB")
    im.thumbnail((1200, 1200))
    gray = np.asarray(im.convert("L"))
    orb = cv2.ORB_create(nfeatures=400)
    points, descriptors = orb.detectAndCompute(gray, None)
    views = {}
    for sigma in (0, 2, 8, 24):
        view = im.filter(ImageFilter.GaussianBlur(sigma)) if sigma else im.copy()
        filename = f"visual-blur-{sigma}.png"
        view.thumbnail((700, 700))
        view.save(der / filename)
        views[str(sigma)] = {
            "phash": str(imagehash.phash(view)),
            "dhash": str(imagehash.dhash(view)),
            "file": filename,
        }
    return {
        "method": "ImageHash pHash/dHash + OpenCV ORB; fixed multiscale Gaussian views",
        "version": "0.12.0",
        "panel_analysis": decompose_panels(im, der),
        "phash": str(imagehash.phash(im)),
        "dhash": str(imagehash.dhash(im)),
        "colorhash": str(imagehash.colorhash(im)),
        "size": list(im.size),
        "views": views,
        "orb": {
            "points": [[p.pt[0], p.pt[1]] for p in points],
            "descriptors_b64": base64.b64encode(descriptors.tobytes()).decode()
            if descriptors is not None
            else "",
            "rows": len(points),
            "columns": 32,
            "algorithm": "ORB (400 maximum keypoints)",
        },
        "libraries": {
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "imagehash": imagehash.__version__,
        },
        "interpretation": "Similarity is an investigative lead, not identity, authenticity, intention or a prediction. Crops, overlays and compression can change signatures; unrelated pictures can share coarse structure.",
    }


def decompose_panels(image, der):
    """Test a bounded four-panel layout for a two-image alpha-blending sequence.

    This tests pixel composition, never concealed-person recognition. Every endpoint
    pair is tried; middle panels must improve strongly over either unblended endpoint.
    """
    from itertools import combinations
    from PIL import Image

    im = image.convert("RGB").copy()
    im.thumbnail((1200, 1200))
    w, h = im.size
    if min(w, h) < 160:
        return {"status": "NOT_TESTED", "reason": "Image smaller than 160 pixels"}
    array = np.asarray(im)
    white = array.min(axis=2) > 235
    xs = range(int(w * 0.42), int(w * 0.58))
    ys = range(int(h * 0.42), int(h * 0.58))
    sx = max(xs, key=lambda x: float(white[:, x].mean()))
    sy = max(ys, key=lambda y: float(white[y, :].mean()))
    dividers = bool(white[:, sx].mean() > 0.75 and white[sy, :].mean() > 0.75)
    if not dividers:
        sx, sy = w // 2, h // 2
    margin = 3
    boxes = [
        (margin, margin, sx - margin, sy - margin),
        (sx + margin, margin, w - margin, sy - margin),
        (margin, sy + margin, sx - margin, h - margin),
        (sx + margin, sy + margin, w - margin, h - margin),
    ]
    panels = [im.crop(b) for b in boxes]
    samples = [
        np.asarray(p.resize((128, 128), Image.Resampling.LANCZOS), dtype=np.float64)
        / 255
        for p in panels
    ]
    experiments = []
    for a, b in combinations(range(4), 2):
        first, second = samples[a], samples[b]
        direction = second - first
        denom = float(np.square(direction).sum())
        if denom < 1e-8:
            continue
        measures = []
        for i, target in enumerate(samples):
            alpha = float(np.clip(np.sum((target - first) * direction) / denom, 0, 1))
            reconstruction = first + alpha * direction
            rmse = float(np.sqrt(np.mean((target - reconstruction) ** 2)))
            baseline = min(
                float(np.sqrt(np.mean((target - first) ** 2))),
                float(np.sqrt(np.mean((target - second) ** 2))),
            )
            measures.append(
                {
                    "panel": i,
                    "endpoint_b_weight": alpha,
                    "rmse": rmse,
                    "endpoint_baseline_rmse": baseline,
                    "error_reduction": 1 - rmse / baseline if baseline > 1e-10 else 0,
                }
            )
        mids = [x for x in measures if x["panel"] not in (a, b)]
        experiments.append(
            {
                "endpoints": [a, b],
                "rmse": sum(x["rmse"] for x in mids) / 2,
                "endpoint_rms_difference": float(np.sqrt(np.mean(direction**2))),
                "panels": measures,
            }
        )
    if not experiments:
        return {"status": "NO_MIXTURE_DETECTED", "pairs_attempted": 0}
    experiments.sort(key=lambda x: x["rmse"])
    best = experiments[0]
    a, b = best["endpoints"]
    middle = [x for x in best["panels"] if x["panel"] not in (a, b)]
    detected = best["endpoint_rms_difference"] > 0.08 and all(
        0.08 < x["endpoint_b_weight"] < 0.92
        and x["error_reduction"] > 0.5
        and x["rmse"] < 0.055
        for x in middle
    )
    result = {
        "status": "MIXTURE_SEQUENCE_DETECTED" if detected else "NO_MIXTURE_DETECTED",
        "method": "Least-squares alpha blending across all six endpoint pairs; 128×128 RGB samples",
        "partition": "Detected white row/column separators"
        if dividers
        else "Candidate equal quadrants; no separator certified",
        "grid_separator_detected": dividers,
        "pairs_attempted": len(experiments),
        "endpoint_pair_trials": experiments,
        "threshold_interpretation": "Engineering screening thresholds, not calibrated confidence or significance. Validate against independent controls before relying on a case conclusion.",
        "best": best,
        "thresholds": {
            "max_middle_rmse": 0.055,
            "min_error_reduction": 0.5,
            "middle_alpha_range": [0.08, 0.92],
            "min_endpoint_rms_difference": 0.08,
        },
        "limitations": "An approximate blend fit supports an overlay explanation, not edit chronology, authorship, identity, intent or a hidden-message claim. Endpoint naming requires independently cited source context.",
    }
    if not detected:
        return result
    descriptions = []
    for i, panel in enumerate(panels):
        panel.thumbnail((600, 600))
        name = f"visual-panel-{i}.png"
        panel.save(der / name)
        measure = best["panels"][i]
        alpha = measure["endpoint_b_weight"]
        prediction = samples[a] * (1 - alpha) + samples[b] * alpha
        Image.fromarray(np.uint8(np.clip(prediction * 255, 0, 255))).save(
            der / f"visual-fit-{i}.png"
        )
        difference = np.abs(samples[i] - prediction)
        Image.fromarray(np.uint8(np.clip(difference * 4 * 255, 0, 255))).save(
            der / f"visual-residual-{i}.png"
        )
        descriptions.append(
            {
                "panel": i,
                "box_in_processed_image": list(boxes[i]),
                "processed_image_size": [w, h],
                "file": name,
                "phash": str(imagehash.phash(panel)),
                "dhash": str(imagehash.dhash(panel)),
                "colorhash": str(imagehash.colorhash(panel)),
                "orb_features": simple_orb(panel),
                "reconstruction_file": f"visual-fit-{i}.png",
                "residual_file": f"visual-residual-{i}.png",
                **measure,
            }
        )
    result["panels"] = descriptions
    return result


def simple_orb(image):
    """Reuse bounded descriptors for source-to-panel geometric matching."""
    gray = np.asarray(image.convert("L"))
    points, descriptors = cv2.ORB_create(nfeatures=400).detectAndCompute(gray, None)
    return {
        "points": [[p.pt[0], p.pt[1]] for p in points],
        "rows": len(points),
        "columns": 32,
        "descriptors_b64": base64.b64encode(descriptors.tobytes()).decode()
        if descriptors is not None
        else "",
    }
