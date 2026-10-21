"""Model loading: GGUF metadata probe, autoconfig, llama-server lifecycle."""

from __future__ import annotations

import shutil
import struct
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


GGUF_MAGIC = b"GGUF"


@dataclass
class GGUFMetadata:
    path: Path
    version: int = 0
    tensor_count: int = 0
    kv_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def architecture(self) -> str:
        return str(self.metadata.get("general.architecture", "unknown"))

    @property
    def context_length(self) -> int | None:
        arch = self.architecture
        for key in (f"{arch}.context_length", "llama.context_length", "context_length"):
            if key in self.metadata:
                return int(self.metadata[key])
        return None

    @property
    def size_bytes(self) -> int:
        return self.path.stat().st_size


def probe_gguf(path: Path | str) -> GGUFMetadata:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("rb") as f:
        magic = f.read(4)
        if magic != GGUF_MAGIC:
            raise ValueError(f"Not a GGUF file: {path}")
        version = struct.unpack("<I", f.read(4))[0]
        tensor_count = struct.unpack("<Q", f.read(8))[0]
        kv_count = struct.unpack("<Q", f.read(8))[0]
        metadata: dict[str, Any] = {}
        # Minimal KV reader for common types (uint32, int32, float32, string, bool, uint64)
        for _ in range(kv_count):
            key = _read_string(f)
            vtype = struct.unpack("<I", f.read(4))[0]
            val = _read_value(f, vtype)
            metadata[key] = val
    return GGUFMetadata(path=path, version=version, tensor_count=tensor_count, kv_count=kv_count, metadata=metadata)


def _read_string(f) -> str:
    n = struct.unpack("<Q", f.read(8))[0]
    return f.read(n).decode("utf-8", errors="replace")


def _read_value(f, vtype: int):
    if vtype == 8:  # string
        return _read_string(f)
    if vtype in (4, 5):  # uint32/int32
        return struct.unpack("<I" if vtype == 4 else "<i", f.read(4))[0]
    if vtype == 6:  # float32
        return struct.unpack("<f", f.read(4))[0]
    if vtype == 7:  # bool
        return bool(f.read(1)[0])
    if vtype in (10, 11):  # uint64/int64
        fmt = "<Q" if vtype == 10 else "<q"
        return struct.unpack(fmt, f.read(8))[0]
    if vtype == 12:  # float64
        return struct.unpack("<d", f.read(8))[0]
    if vtype == 0:
        return f.read(1)[0]
    if vtype == 1:
        v = f.read(1)[0]
        return v - 256 if v > 127 else v
    if vtype in (2, 3):
        fmt = "<H" if vtype == 2 else "<h"
        return struct.unpack(fmt, f.read(2))[0]
    if vtype == 9:  # array
        arr_type = struct.unpack("<I", f.read(4))[0]
        count = struct.unpack("<Q", f.read(8))[0]
        return [_read_value(f, arr_type) for _ in range(count)]
    # fallback: skip unknown
    return None


@dataclass
class ModelProfile:
    name: str
    model_path: Path
    ctx_size: int = 4096
    gpu_layers: int = 0
    cache_type: str = "f16"
    threads: int = 4
    batch_size: int = 512
    speculative_model: Path | None = None
    draft_max: int = 4
    fit: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def autoconfig(metadata: GGUFMetadata, vram_bytes: int | None = None) -> ModelProfile:
    ctx = metadata.context_length or 4096
    # clamp ctx to a sane default if huge
    if ctx > 131072:
        ctx = 32768
    gpu_layers = 0
    if vram_bytes and metadata.size_bytes < vram_bytes * 0.8:
        gpu_layers = 99  # offload all
    cache_type = "q8_0" if (vram_bytes and metadata.size_bytes > vram_bytes * 0.5) else "f16"
    name = metadata.path.stem
    return ModelProfile(name=name, model_path=metadata.path, ctx_size=ctx,
                        gpu_layers=gpu_layers, cache_type=cache_type)


class LlamaServer:
    def __init__(self, binary: str = "llama-server", host: str = "127.0.0.1", port: int = 8080):
        self.binary = binary
        self.host = host
        self.port = port
        self.process: subprocess.Popen | None = None

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def start(self, profile: ModelProfile, extra_args: list[str] | None = None) -> bool:
        if self.process is not None and self.process.poll() is None:
            return True
        if not self.is_available():
            raise RuntimeError(f"{self.binary} not found on PATH")
        args = [self.binary, "-m", str(profile.model_path), "-c", str(profile.ctx_size),
                "-ngl", str(profile.gpu_layers), "-ctk", profile.cache_type, "-ctv", profile.cache_type,
                "--host", self.host, "--port", str(self.port), "-t", str(profile.threads),
                "-b", str(profile.batch_size)]
        if profile.speculative_model:
            args.extend(["--speculative-model", str(profile.speculative_model),
                         "--draft-max", str(profile.draft_max)])
        if profile.fit:
            args.append("--fit")
        if extra_args:
            args.extend(extra_args)
        self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        # wait briefly for readiness
        for _ in range(50):
            if self.process.poll() is not None:
                return False
            try:
                import urllib.request
                urllib.request.urlopen(f"http://{self.host}:{self.port}/health", timeout=1)
                return True
            except Exception:
                time.sleep(0.2)
        return self.process.poll() is None

    def stop(self):
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
            except Exception:
                self.process.kill()
            self.process = None

    def health(self) -> bool:
        try:
            import urllib.request
            urllib.request.urlopen(f"http://{self.host}:{self.port}/health", timeout=2)
            return True
        except Exception:
            return False
