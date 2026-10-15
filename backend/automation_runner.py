"""Fixed analytical subprocess entrypoint; accepts JSON tool inputs, never code or commands."""

import json
import sys


def main() -> None:
    """Limit CPU/address space on Linux and execute exactly one registered callable."""
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    raw = sys.stdin.buffer.read(256001)
    if len(raw) > 256000:
        raise ValueError("Input exceeds 256 KB")
    from .automation_tools import execute

    value = json.loads(raw)
    result = execute(value["tool"], value["inputs"])
    sys.stdout.write(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        sys.stdout.write(
            json.dumps({"error": str(ex)[:800], "type": type(ex).__name__})
        )
        sys.exit(1)
