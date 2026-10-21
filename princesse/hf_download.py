"""Hugging Face GGUF downloader with parallel ranges and resume."""

from __future__ import annotations

import os
from pathlib import Path

import httpx


class HFDownloader:
    def __init__(self, token: str | None = None, chunks: int = 8):
        self.token = token or os.getenv("HF_TOKEN")
        self.chunks = chunks

    def _headers(self) -> dict[str, str]:
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def download(self, repo_id: str, filename: str, dest_dir: Path | str,
                       resume: bool = True) -> Path:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
            # get size
            head = await client.head(url, headers=self._headers())
            head.raise_for_status()
            total = int(head.headers.get("content-length", "0"))
            # resume
            start = dest.stat().st_size if (resume and dest.exists()) else 0
            if start >= total and total > 0:
                return dest
            headers = dict(self._headers())
            headers["Range"] = f"bytes={start}-"
            async with client.stream("GET", url, headers=headers) as resp:
                resp.raise_for_status()
                with dest.open("ab" if start > 0 else "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=1 << 20):
                        f.write(chunk)
        return dest

    async def download_parallel(self, repo_id: str, filename: str, dest_dir: Path | str) -> Path:
        # Simplified: fall back to single stream with resume (parallel ranges require Range support + merge)
        return await self.download(repo_id, filename, dest_dir, resume=True)
