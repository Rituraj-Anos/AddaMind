"""Uploaded documents: text extraction, chunking, and BM25 keyword search. No external services.

Files live in .cache/documents/<doc_id>/ (original + chunks.json). BM25 handles names, numbers
and exact terms well and needs no embedding API calls, which keeps it fast and quota-free on
the day. If a problem needs semantic search, add an embedding score next to bm25 in search().
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import CACHE_DIR

DOC_DIR = CACHE_DIR / "documents"
ALLOWED = {".pdf", ".txt", ".md", ".csv", ".json", ".html", ".htm", ".log", ".xml", ".yaml", ".yml", ".py"}
MAX_BYTES = 15 * 1024 * 1024
CHUNK_CHARS = 900
OVERLAP = 150
_WORD = re.compile(r"[a-z0-9]+(?:[.'-][a-z0-9]+)*")
_ID = re.compile(r"^[a-f0-9]{12}$")
_STOP = set("a an and are as at be by for from has have in is it its of on or that the this to was were with".split())


@dataclass
class Chunk:
    doc_id: str
    index: int
    page: int | None
    text: str


@dataclass
class DocInfo:
    id: str
    name: str
    size: int
    pages: int | None
    chunks: int
    chars: int
    uploaded_at: float


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


def extract_text(name: str, data: bytes) -> list[tuple[int | None, str]]:
    """Return [(page_number or None, text)]."""
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        from io import BytesIO
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:  # noqa: BLE001
                raise ValueError("the PDF is password-protected")
        pages = [(i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(reader.pages)]
        if not any(t for _, t in pages):
            raise ValueError("no text found in the PDF (it may be a scanned image; OCR is not set up)")
        return pages
    text = data.decode("utf-8", errors="replace")
    if ext in (".html", ".htm"):
        from .tools.web import _TextExtractor
        ex = _TextExtractor()
        ex.feed(text)
        text = ex.text()
    return [(None, text)]


def chunk_pages(doc_id: str, pages: list[tuple[int | None, str]]) -> list[Chunk]:
    """Split on paragraph boundaries into ~CHUNK_CHARS pieces with OVERLAP, keeping page numbers."""
    chunks: list[Chunk] = []
    for page, text in pages:
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        buf = ""
        for para in paras:
            while len(para) > CHUNK_CHARS:  # very long paragraph: hard split
                head, para = para[:CHUNK_CHARS], para[CHUNK_CHARS - OVERLAP:]
                if buf:
                    chunks.append(Chunk(doc_id, len(chunks), page, buf))
                    buf = ""
                chunks.append(Chunk(doc_id, len(chunks), page, head))
            if len(buf) + len(para) + 2 > CHUNK_CHARS and buf:
                chunks.append(Chunk(doc_id, len(chunks), page, buf))
                buf = buf[-OVERLAP:] + "\n\n" + para  # carry a little context forward
            else:
                buf = f"{buf}\n\n{para}" if buf else para
        if buf.strip():
            chunks.append(Chunk(doc_id, len(chunks), page, buf))
    return chunks


class DocumentStore:
    def __init__(self, directory: Path = DOC_DIR):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._chunks: list[Chunk] = []
        self._tf: list[Counter] = []
        self._df: Counter = Counter()
        self._avg_len = 0.0
        self._docs: dict[str, DocInfo] = {}
        self._load()

    # ---------- persistence ----------
    def _load(self):
        for d in sorted(self.dir.iterdir()):
            meta, chunks = d / "meta.json", d / "chunks.json"
            if meta.exists() and chunks.exists():
                try:
                    info = DocInfo(**json.loads(meta.read_text(encoding="utf-8")))
                    self._docs[info.id] = info
                    self._chunks += [Chunk(**c) for c in json.loads(chunks.read_text(encoding="utf-8"))]
                except (ValueError, TypeError):
                    continue
        self._reindex()

    def _reindex(self):
        self._tf = [Counter(tokenize(c.text)) for c in self._chunks]
        self._df = Counter(t for tf in self._tf for t in tf)
        self._avg_len = (sum(sum(tf.values()) for tf in self._tf) / len(self._tf)) if self._tf else 0.0

    # ---------- public ----------
    def add(self, name: str, data: bytes) -> DocInfo:
        name = Path(name or "upload.txt").name[:120]
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED:
            raise ValueError(f"unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED))}")
        if len(data) > MAX_BYTES:
            raise ValueError(f"file is larger than {MAX_BYTES // 1024 // 1024} MB")
        if not data:
            raise ValueError("the file is empty")
        pages = extract_text(name, data)
        doc_id = uuid.uuid4().hex[:12]
        chunks = chunk_pages(doc_id, pages)
        if not chunks:
            raise ValueError("no text found in the file")
        info = DocInfo(doc_id, name, len(data), len(pages) if ext == ".pdf" else None, len(chunks),
                       sum(len(t) for _, t in pages), time.time())
        d = self.dir / doc_id
        d.mkdir()
        (d / ("original" + ext)).write_bytes(data)
        (d / "chunks.json").write_text(json.dumps([asdict(c) for c in chunks], ensure_ascii=False), encoding="utf-8")
        (d / "meta.json").write_text(json.dumps(asdict(info)), encoding="utf-8")
        with self._lock:
            self._docs[doc_id] = info
            self._chunks += chunks
            self._reindex()
        return info

    def list(self) -> list[DocInfo]:
        return sorted(self._docs.values(), key=lambda d: d.uploaded_at, reverse=True)

    def get(self, doc_id: str) -> DocInfo | None:
        return self._docs.get(doc_id)

    def delete(self, doc_id: str) -> bool:
        if not _ID.match(doc_id or "") or doc_id not in self._docs:
            return False
        with self._lock:
            d = self.dir / doc_id
            for f in d.iterdir():
                f.unlink()
            d.rmdir()
            self._docs.pop(doc_id)
            self._chunks = [c for c in self._chunks if c.doc_id != doc_id]
            self._reindex()
        return True

    def search(self, query: str, k: int = 5, doc_id: str | None = None) -> list[dict]:
        """BM25 (k1=1.5, b=0.75) over all chunks, or one document's chunks."""
        terms = tokenize(query)
        if not terms or not self._chunks:
            return []
        n = len(self._chunks)
        scored = []
        for i, (c, tf) in enumerate(zip(self._chunks, self._tf)):
            if doc_id and c.doc_id != doc_id:
                continue
            length = sum(tf.values()) or 1
            s = 0.0
            for t in terms:
                f = tf.get(t)
                if not f:
                    continue
                idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                s += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * length / (self._avg_len or 1)))
            if s > 0:
                scored.append((s, i))
        scored.sort(reverse=True)
        out = []
        for s, i in scored[:k]:
            c = self._chunks[i]
            out.append({"document": self._docs[c.doc_id].name, "doc_id": c.doc_id, "chunk": c.index,
                        "page": c.page, "score": round(s, 2), "text": c.text})
        return out

    def read(self, doc_id: str, start: int = 0, count: int = 3) -> list[dict]:
        chunks = [c for c in self._chunks if c.doc_id == doc_id]
        return [{"chunk": c.index, "page": c.page, "text": c.text} for c in chunks[start:start + count]]


_store: DocumentStore | None = None


def get_store() -> DocumentStore:
    global _store
    if _store is None:
        _store = DocumentStore()
    return _store
