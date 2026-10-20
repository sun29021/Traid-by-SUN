"""Model registry: manifest, checksums, lazy ONNX sessions and device selection.

ARCHITECTURE.md §10.4. Sessions are created on first use and kept for the process.
On the owner's dual-GPU laptop, DirectML's "high_performance" preference selects the
discrete NVIDIA GPU. Any GPU failure (creation or run, e.g. out of memory) falls back
to the CPU for that model and is reported in `status()`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray

logger = logging.getLogger("traid.engine.models")

DevicePreference = Literal["auto", "cpu", "directml", "cuda"]
Device = Literal["cpu", "directml", "cuda"]

_PROVIDERS: dict[Device, str] = {
    "directml": "DmlExecutionProvider",
    "cuda": "CUDAExecutionProvider",
    "cpu": "CPUExecutionProvider",
}
_CHUNK = 1024 * 1024


class ModelUnavailableError(RuntimeError):
    """A required model file is missing or fails its checksum."""


@dataclass(frozen=True)
class ModelSpec:
    name: str
    role: str
    version: str
    file: str
    sha256: str
    license: str
    required: bool
    cpu_only: bool = False  # e.g. ops the GPU provider cannot run


@dataclass(frozen=True)
class ModelStatus:
    name: str
    role: str
    version: str
    present: bool
    checksum_ok: bool
    loaded: bool
    device: Device | None


@dataclass
class _Checksum:
    size: int
    mtime_ns: int
    ok: bool


@dataclass
class ModelSession:
    """An ONNX session that downgrades itself to CPU if the GPU fails at run time."""

    spec: ModelSpec
    path: Path
    device: Device
    _session: ort.InferenceSession
    _gpu_options: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def input_names(self) -> list[str]:
        return [i.name for i in self._session.get_inputs()]

    def metadata(self) -> Mapping[str, str]:
        meta: Mapping[str, str] = self._session.get_modelmeta().custom_metadata_map
        return meta

    def run(self, feeds: Mapping[str, NDArray[np.float32]]) -> list[NDArray[np.float32]]:
        try:
            return self._session.run(None, dict(feeds))  # type: ignore[no-any-return]
        except Exception as exc:  # ORT raises its own exception types
            if self.device == "cpu":
                raise
            logger.warning(
                "GPU run failed; switching model to CPU",
                extra={"model": self.spec.name, "error": type(exc).__name__},
            )
            with self._lock:
                self._session = _create_session(self.path, "cpu", {})
                self.device = "cpu"
            return self._session.run(None, dict(feeds))  # type: ignore[no-any-return]


def _create_session(
    path: Path, device: Device, gpu_options: dict[str, Any]
) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.log_severity_level = 3  # errors only
    providers: list[str | tuple[str, dict[str, Any]]] = ["CPUExecutionProvider"]
    if device != "cpu":
        providers.insert(0, (_PROVIDERS[device], gpu_options))
    if device == "directml":
        # DirectML requires sequential execution without memory pattern optimisation.
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return ort.InferenceSession(str(path), sess_options=options, providers=providers)


def available_devices() -> list[Device]:
    providers = set(ort.get_available_providers())
    return [device for device, name in _PROVIDERS.items() if name in providers]


def resolve_device(preference: DevicePreference) -> Device:
    """The device to try first. Falls back to CPU when the requested one is missing."""
    available = available_devices()
    if preference == "auto":
        gpus: tuple[Device, ...] = ("directml", "cuda")
        return next((device for device in gpus if device in available), "cpu")
    if preference not in available:
        logger.warning("Requested device unavailable; using CPU", extra={"device": preference})
        return "cpu"
    return preference


def gpu_options(device: Device, gpu_device_id: str) -> dict[str, Any]:
    if device == "cpu":
        return {}
    if gpu_device_id != "auto":
        return {"device_id": int(gpu_device_id)}
    if device == "directml":
        return {"performance_preference": "high_performance", "device_filter": "gpu"}
    return {}


class ModelRegistry:
    def __init__(
        self,
        model_dir: Path,
        specs: list[ModelSpec],
        *,
        device: DevicePreference = "auto",
        gpu_device_id: str = "auto",
    ) -> None:
        self.model_dir = model_dir
        self.specs = {spec.name: spec for spec in specs}
        self.device_preference = device
        self.gpu_device_id = gpu_device_id
        self._sessions: dict[str, ModelSession] = {}
        self._checksums: dict[str, _Checksum] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_manifest(
        cls, model_dir: Path, *, device: DevicePreference = "auto", gpu_device_id: str = "auto"
    ) -> ModelRegistry:
        manifest = model_dir / "manifest.json"
        specs: list[ModelSpec] = []
        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            specs = [
                ModelSpec(
                    name=m["name"],
                    role=m["role"],
                    version=m["version"],
                    file=m["file"],
                    sha256=m["sha256"],
                    license=m["license"],
                    required=bool(m.get("required", True)),
                    cpu_only=bool(m.get("cpu_only", False)),
                )
                for m in data.get("models", [])
            ]
        else:
            logger.warning("Model manifest not found", extra={"path": str(manifest)})
        return cls(model_dir, specs, device=device, gpu_device_id=gpu_device_id)

    # ------------------------------------------------------------ files

    def _path(self, spec: ModelSpec) -> Path:
        return self.model_dir / spec.file

    def checksum_ok(self, name: str) -> bool:
        """SHA-256 check, cached until the file's size or mtime changes."""
        spec = self.specs[name]
        path = self._path(spec)
        try:
            stat = path.stat()
        except FileNotFoundError:
            return False
        cached = self._checksums.get(name)
        if cached and cached.size == stat.st_size and cached.mtime_ns == stat.st_mtime_ns:
            return cached.ok
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(_CHUNK), b""):
                digest.update(block)
        ok = digest.hexdigest() == spec.sha256
        self._checksums[name] = _Checksum(stat.st_size, stat.st_mtime_ns, ok)
        return ok

    @property
    def ready(self) -> bool:
        required = [s for s in self.specs.values() if s.required]
        return bool(required) and all(self.checksum_ok(s.name) for s in required)

    # ------------------------------------------------------------ sessions

    def session(self, name: str) -> ModelSession:
        with self._lock:
            existing = self._sessions.get(name)
            if existing is not None:
                return existing
            spec = self.specs.get(name)
            if spec is None:
                raise ModelUnavailableError(f"Model '{name}' is not in the manifest")
            if not self.checksum_ok(name):
                raise ModelUnavailableError(
                    f"Model '{name}' is missing or damaged; run scripts/fetch_models.py"
                )
            path = self._path(spec)
            device = "cpu" if spec.cpu_only else resolve_device(self.device_preference)
            options = gpu_options(device, self.gpu_device_id)
            try:
                raw = _create_session(path, device, options)
            except Exception as exc:  # GPU init can fail on drivers; CPU always works
                if device == "cpu":
                    raise
                logger.warning(
                    "GPU session failed; using CPU",
                    extra={"model": name, "error": type(exc).__name__},
                )
                device, options, raw = "cpu", {}, _create_session(path, "cpu", {})
            if device != "cpu" and _PROVIDERS[device] not in raw.get_providers():
                device = "cpu"
            created = ModelSession(spec, path, device, raw, options)
            self._sessions[name] = created
            logger.info("Model loaded", extra={"model": name, "device": device})
            return created

    def status(self) -> list[ModelStatus]:
        statuses = []
        for spec in self.specs.values():
            loaded = self._sessions.get(spec.name)
            statuses.append(
                ModelStatus(
                    name=spec.name,
                    role=spec.role,
                    version=spec.version,
                    present=self._path(spec).is_file(),
                    checksum_ok=self.checksum_ok(spec.name),
                    loaded=loaded is not None,
                    device=loaded.device if loaded else None,
                )
            )
        return statuses
