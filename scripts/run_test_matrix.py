"""Run every Python test module in a fresh process, preserving private evidence.

Several legacy tests cache a module-global app/vault. Process isolation prevents
one module's fixture from selecting another module's vault. Failures are retained
and never converted to passes or skipped assertions.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from defusedxml import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def run(output, timeout):
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    summary = output / "python-summary.json"
    if summary.exists():
        raise SystemExit("Use a new output directory to preserve earlier test results")
    modules = sorted((ROOT / "tests").glob("test_*.py"))
    # Run local modules first; external-fixture requirements remain visible last.
    modules.sort(key=lambda path: (path.stem in ("test_foundation", "test_retrieval"), path.name))
    report = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "module_count": len(modules), "modules": [], "complete": False,
              "processor_image": os.environ.get("SHERLOCK_PROCESSOR_IMAGE", "sherlock-processor:0.4"),
              "process_isolation": True}
    save(summary, report)
    for module in modules:
        if shutil.disk_usage(ROOT).free < 1536 * 1024**2:
            report["blocked"] = "Less than 1.5 GiB free; remaining modules not run"
            break
        name = module.stem
        directory = output / name
        directory.mkdir(mode=0o700)
        xml = directory / "results.xml"
        env = dict(os.environ)
        env.update(SHERLOCK_DATA=str(directory / "case"), ERPS_AUTO_INGEST="0")
        env.setdefault("SHERLOCK_PROCESSOR_IMAGE", "sherlock-processor:0.4")
        env.setdefault("SHERLOCK_CONTAINER_CREATE_TIMEOUT", "180")
        command = [sys.executable, "-m", "pytest", str(module), "-q", "--disable-warnings",
                   "--junitxml=" + str(xml), "--basetemp=" + str(directory / "pytest-temp")]
        started = time.monotonic()
        timed_out = False
        with (directory / "output.log").open("x") as log:
            (directory / "output.log").chmod(0o600)
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                for signum, grace in ((signal.SIGINT, 30), (signal.SIGTERM, 10), (signal.SIGKILL, 5)):
                    if process.poll() is not None:
                        break
                    os.killpg(process.pid, signum)
                    try:
                        process.wait(timeout=grace)
                    except subprocess.TimeoutExpired:
                        pass
                code = process.poll()
        item = {"module": module.name, "exit_code": code, "timed_out": timed_out,
                "seconds": round(time.monotonic() - started, 3), "passed": 0, "failed": 0,
                "errors": 0, "skipped": 0, "cases": 0, "failures": []}
        if xml.exists():
            xml.chmod(0o600)
            tree = ET.parse(xml)
            for case in tree.findall(".//testcase"):
                item["cases"] += 1
                result = next((kind for kind in ("failure", "error", "skipped") if case.find(kind) is not None), None)
                key = {"failure": "failed", "error": "errors", "skipped": "skipped", None: "passed"}[result]
                item[key] += 1
                if result in ("failure", "error"):
                    item["failures"].append({"name": case.attrib.get("name"), "kind": result})
        else:
            item["missing_results"] = True
        report["modules"].append(item)
        save(summary, report)
        print(json.dumps({key: value for key, value in item.items() if key != "failures"}), flush=True)
    report["complete"] = len(report["modules"]) == len(modules)
    report["totals"] = {key: sum(item[key] for item in report["modules"])
                        for key in ("cases", "passed", "failed", "errors", "skipped")}
    save(summary, report)
    return 0 if report["complete"] and all(item["exit_code"] == 0 for item in report["modules"]) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-per-module", type=int, default=1500)
    args = parser.parse_args()
    if args.timeout_per_module < 30:
        parser.error("Module timeout must allow at least 30 seconds for fixture cleanup")
    raise SystemExit(run(args.output.resolve(), args.timeout_per_module))
