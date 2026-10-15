"""Trusted container launcher. Never falls back to executing parsers on the host."""

from __future__ import annotations
import hashlib, json, os, selectors, shutil, subprocess, tempfile, time, uuid, threading
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
import fcntl

IMAGE = os.environ.get("SHERLOCK_PROCESSOR_IMAGE", "sherlock-processor:0.4")
MAX_OUTPUT = 32 * 1024 * 1024


class SandboxError(RuntimeError):
    pass


def docker_args():
    executable = shutil.which("docker")
    if not executable:
        raise SandboxError(
            "Sandbox unavailable: install Docker and build the processing image. Host parsing is prohibited."
        )
    # Pin the daemon to a local Unix socket; never inherit a remote Docker context.
    if os.name != "posix":
        raise SandboxError("Sandbox requires a local Docker Unix socket")
    candidates = (
        [Path("/var/run/docker.sock")]
        if os.uname().sysname == "Linux"
        else [Path.home() / ".docker/run/docker.sock", Path("/var/run/docker.sock")]
    )
    socket_path = next((p for p in candidates if p.exists()), None)
    if socket_path is None:
        raise SandboxError(
            "Local Docker socket unavailable; start Docker Desktop or the local Docker service"
        )
    return [executable, "--host=unix://" + str(socket_path)]


def docker_env():
    env = dict(os.environ)
    for k in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    ):
        env.pop(k, None)
    return env


def command(args, timeout=15):
    try:
        r = subprocess.run(
            docker_args() + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=docker_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SandboxError("Sandbox daemon unavailable or timed out") from e
    if r.returncode:
        raise SandboxError((r.stderr or r.stdout or "Container command failed")[-1500:])
    return r.stdout


def availability():
    try:
        image = json.loads(command(["image", "inspect", IMAGE]))[0]
        return {
            "available": True,
            "mode": "docker",
            "image": IMAGE,
            "image_id": image["Id"],
            "network": "none",
            "memory_mb": 768,
            "cpu": 1,
            "wall_seconds": 90,
            "read_only_input": True,
            "read_only_root": True,
        }
    except SandboxError as e:
        return {"available": False, "mode": "docker", "image": IMAGE, "reason": str(e)}


def policy(host):
    required = (
        host.get("NetworkMode") == "none"
        and host.get("ReadonlyRootfs") is True
        and host.get("Memory") == 768 * 1024 * 1024
        and host.get("NanoCpus") == 1_000_000_000
        and host.get("PidsLimit") == 64
        and "ALL" in host.get("CapDrop", [])
        and any(x.startswith("no-new-privileges") for x in host.get("SecurityOpt", []))
    )
    if not required:
        raise SandboxError(
            "Container isolation policy verification failed; worker was not started"
        )
    return {
        "network": "none",
        "root_filesystem": "read-only",
        "memory_bytes": host["Memory"],
        "cpus": 1,
        "pids_limit": 64,
        "capabilities": "all dropped",
        "no_new_privileges": True,
        "wall_seconds": 90,
    }


def stream_bounded(args, timeout=90):
    child = subprocess.Popen(
        docker_args() + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=docker_env(),
        start_new_session=True,
    )
    chunks = []
    size = 0
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    selector.register(child.stdout, selectors.EVENT_READ)
    try:
        while selector.get_map():
            if time.monotonic() > deadline:
                raise SandboxError("Processing exceeded 90-second wall-time limit")
            for key, _ in selector.select(0.2):
                piece = os.read(key.fd, 8192)
                if not piece:
                    selector.unregister(key.fileobj)
                    break
                size += len(piece)
                if size > 128 * 1024:
                    raise SandboxError("Worker log output exceeded 128 KB limit")
                chunks.append(piece)
        code = child.wait(timeout=max(0.1, deadline - time.monotonic()))
        log = b"".join(chunks).decode("utf-8", "replace")
        if code:
            raise SandboxError("Isolated processor failed: " + log[-1500:])
        return log
    finally:
        selector.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.stdout.close()


def read_result(output):
    total = 0
    for p in output.iterdir():
        if (
            p.is_symlink()
            or not p.is_file()
            or p.name
            not in {
                "result.json",
                "text.txt",
                "preview.png",
                "red.png",
                "green.png",
                "blue.png",
                "lsb.png",
                "ela.png",
                "visual-blur-0.png",
                "visual-blur-2.png",
                "visual-blur-8.png",
                "visual-blur-24.png",
                "visual-panel-0.png",
                "visual-panel-1.png",
                "visual-panel-2.png",
                "visual-panel-3.png",
                "visual-fit-0.png",
                "visual-fit-1.png",
                "visual-fit-2.png",
                "visual-fit-3.png",
                "visual-residual-0.png",
                "visual-residual-1.png",
                "visual-residual-2.png",
                "visual-residual-3.png",
            }
        ):
            raise SandboxError("Worker produced an unsafe derivative path")
        if p.suffix == ".png" and not p.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise SandboxError("Invalid diagnostic PNG")
        total += p.stat().st_size
    if total > MAX_OUTPUT:
        raise SandboxError("Derivative output exceeds 32 MB limit")
    path = output / "result.json"
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise SandboxError("Worker result missing or oversized")
    result = json.loads(path.read_bytes())
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("text"), str)
        or not isinstance(result.get("metadata"), dict)
    ):
        raise SandboxError("Invalid worker result schema")
    if result.get("preview") and (
        not (output / "preview.png").is_file()
        or not (output / "preview.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    ):
        raise SandboxError("Invalid preview derivative")
    return result


PROCESSING_SLOTS = threading.BoundedSemaphore(2)


@contextmanager
def processing_admission(timeout=120, directory=None):
    """Reserve parser slots across processes and preserve filesystem headroom.

    Docker VFS can physically copy a gigabyte per parser. Thread-only semaphores
    cannot coordinate the API, tests and independent workers sharing this host.
    Kernel locks release automatically after a crashed owner exits.
    """
    folder = (
        Path(directory)
        if directory
        else Path(__file__).resolve().parents[1] / "data/processing-admission"
    )
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if folder.is_symlink() or folder.stat().st_uid != os.getuid():
        raise SandboxError("Unsafe processor admission directory")

    def lockfile(name):
        """Never follow a symlink when opening an admission lock."""
        return os.fdopen(
            os.open(folder / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "r+"
        )

    deadline = time.monotonic() + timeout
    chosen = None
    while chosen is None:
        with lockfile("admission.lock") as gate:
            fcntl.flock(gate, fcntl.LOCK_EX)
            free, busy = [], 0
            try:
                for index in range(2):
                    candidate = lockfile(f"slot-{index}.lock")
                    try:
                        fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        free.append(candidate)
                    except BlockingIOError:
                        busy += 1
                        candidate.close()
                # Conservatively count an in-flight VFS copy even before disk usage reflects it.
                required = 2 * 1024**3 + busy * (1200 * 1024**2)
                if free and shutil.disk_usage(folder).free >= required:
                    chosen = free.pop(0)
            finally:
                for candidate in free:
                    fcntl.flock(candidate, fcntl.LOCK_UN)
                    candidate.close()
                fcntl.flock(gate, fcntl.LOCK_UN)
        if chosen is None:
            if time.monotonic() >= deadline:
                raise SandboxError(
                    "Processor waiting for a shared slot or safe disk headroom; no container was created"
                )
            time.sleep(0.25)
    try:
        yield
    finally:
        fcntl.flock(chosen, fcntl.LOCK_UN)
        chosen.close()


def run(original: Path, mime: str, expected_sha: str, derivative: Path, probe=False):
    """Bound large VFS parser copies independently of parallel analytical actions."""
    with PROCESSING_SLOTS, processing_admission():
        return _run(original, mime, expected_sha, derivative, probe)


def _run(original: Path, mime: str, expected_sha: str, derivative: Path, probe=False):
    original = original.resolve(strict=True)
    derivative = derivative.resolve()
    derivative.mkdir(parents=True, exist_ok=True)
    if hashlib.sha256(original.read_bytes()).hexdigest() != expected_sha:
        raise SandboxError("Original integrity failure before isolated processing")
    name = "sherlock-process-" + uuid.uuid4().hex[:16]
    # Only a single preserved original and a fresh derivative directory are mounted.
    with tempfile.TemporaryDirectory(prefix=".sandbox-", dir=derivative.parent) as temp:
        output = Path(temp)
        args = [
            "create",
            "--name",
            name,
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=64",
            "--memory=768m",
            "--memory-swap=768m",
            "--cpus=1",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--tmpfs",
            f"/tmp:rw,nosuid,nodev,noexec,size=67108864,uid={os.getuid()},gid={os.getgid()},mode=700",
            "--mount",
            f"type=bind,src={original},dst=/input/original,readonly",
            "--mount",
            f"type=bind,src={output},dst=/output",
            "--env",
            "HTTP_PROXY=",
            "--env",
            "HTTPS_PROXY=",
            "--env",
            "ALL_PROXY=",
            "--env",
            "NO_PROXY=",
            IMAGE,
            "--mime=" + mime,
            "--sha256=" + expected_sha,
        ]
        if probe:
            args.append("--probe")
        try:
            command(args, timeout=45)
            inspected = json.loads(command(["inspect", name]))[0]
            manifest = policy(inspected["HostConfig"])
            mounts = inspected["Mounts"]
            if len(mounts) != 2 or not any(
                m["Destination"] == "/input/original" and m["RW"] is False
                for m in mounts
            ):
                raise SandboxError("Read-only evidence mount policy failed")
            if inspected["Config"]["User"] != f"{os.getuid()}:{os.getgid()}":
                raise SandboxError("Worker user policy failed")
            manifest.update(
                {
                    "image_id": inspected["Image"],
                    "image": IMAGE,
                    "container_id": inspected["Id"],
                    "started_utc": datetime.now(timezone.utc).isoformat(),
                }
            )
            worker_log = stream_bounded(["start", "--attach", name])
            result = read_result(output)
            if hashlib.sha256(original.read_bytes()).hexdigest() != expected_sha:
                raise SandboxError(
                    "Original integrity failure after isolated processing"
                )
            for p in output.iterdir():
                destination = derivative / p.name
                if destination.is_symlink():
                    raise SandboxError(
                        "Existing derivative destination is a symbolic link"
                    )
                os.replace(p, destination)
            result["sandbox"] = manifest
            result["worker_log"] = worker_log[-1500:]
            return result
        finally:
            # Docker may finish creating a container even when the CLI timed out.
            # Always clean up this unique owned name, including failed creation.
            try:
                command(["rm", "--force", name], timeout=20)
            except SandboxError:
                pass
