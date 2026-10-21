from pathlib import Path
import struct
from princesse.models import probe_gguf, autoconfig

def _make_gguf(path: Path):
    # minimal GGUF with one kv string
    with path.open("wb") as f:
        f.write(b"GGUF")
        f.write(struct.pack("<I", 3))  # version
        f.write(struct.pack("<Q", 0))  # tensors
        f.write(struct.pack("<Q", 1))  # kv count
        # key string
        key = b"general.architecture"
        f.write(struct.pack("<Q", len(key)))
        f.write(key)
        f.write(struct.pack("<I", 8))  # type string
        val = b"llama"
        f.write(struct.pack("<Q", len(val)))
        f.write(val)

def test_probe(tmp_path):
    p = tmp_path/"m.gguf"
    _make_gguf(p)
    meta = probe_gguf(p)
    assert meta.version == 3
    assert meta.metadata.get("general.architecture") == "llama"

def test_autoconfig(tmp_path):
    p = tmp_path/"m.gguf"
    _make_gguf(p)
    meta = probe_gguf(p)
    prof = autoconfig(meta, vram_bytes=10**9)
    assert prof.name == "m"
    assert prof.ctx_size >= 1
