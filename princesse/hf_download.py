"""Hugging Face GGUF downloader with parallel byte ranges and resume."""

from __future__ import annotations

import os
from pathlib import Path

import httpx


class HFDownloader:
    def __init__(self, token: str | None = None, chunks: int = 8):
        self.token = token or os.getenv("HF_TOKEN")
        self.chunks = max(1, chunks)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _url(self, repo_id: str, filename: str) -> str:
        return f"https://huggingface.co/{repo_id}/resolve/main/{filename}"

    async def _remote_size(self, client: httpx.AsyncClient, url: str) -> int:
        head = await client.head(url, headers=self._headers())
        head.raise_for_status()
        return int(head.headers.get("content-length", "0"))

    async def download(self, repo_id: str, filename: str, dest_dir: Path | str,
                       resume: bool = True) -> Path:
        """Single-stream download with resume support."""
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        url = self._url(repo_id, filename)
        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
            total = await self._remote_size(client, url)
            start = dest.stat().st_size if (resume and dest.exists()) else 0
            if total and start >= total:
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
        """Download in parallel byte ranges, then merge the parts.

        Each part is written to ``<dest>.partN`` and reused on the next run,
        so an interrupted download resumes per chunk instead of restarting.
        """
        import asyncio

        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        url = self._url(repo_id, filename)

        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
            total = await self._remote_size(client, url)
            if total <= 0:
                return await self.download(repo_id, filename, dest_dir)
            if dest.exists() and dest.stat().st_size >= total:
                return dest

            size = (total + self.chunks - 1) // self.chunks
            bounds = []
            for i in range(self.chunks):
                start = i * size
                end = min(total, start + size) - 1
                if start > end:
                    break
                bounds.append((i, start, end))

            async def fetch(index: int, start: int, end: int) -> None:
                part = dest_dir / f"{filename}.part{index}"
                have = part.stat().st_size if part.exists() else 0
                if have >= (end - start + 1):
                    return
                headers = dict(self._headers())
                headers["Range"] = f"bytes={start + have}-{end}"
                async with client.stream("GET", url, headers=headers) as resp:
                    resp.raise_for_status()
                    with part.open("ab") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=1 << 20):
                            f.write(chunk)

            await asyncio.gather(*[fetch(i, s, e) for i, s, e in bounds])

            # merge parts into the final file
            tmp = dest.with_suffix(dest.suffix + ".merging")
            with tmp.open("wb") as out:
                for i, _, _ in bounds:
                    part = dest_dir / f"{filename}.part{i}"
                    with part.open("rb") as src:
                        while True:
                            data = src.read(1 << 20)
                            if not data:
                                break
                            out.write(data)
            tmp.replace(dest)
            for i, _, _ in bounds:
                (dest_dir / f"{filename}.part{i}").unlink(missing_ok=True)
        return dest
