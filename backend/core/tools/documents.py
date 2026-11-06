"""Tools that let the agent use uploaded documents (see backend/core/documents.py)."""
from __future__ import annotations

from typing import Annotated

from ..documents import get_store
from .registry import tool


@tool
def list_documents() -> dict:
    """List the documents the user has uploaded, with their ids, page and chunk counts."""
    docs = get_store().list()
    return {"documents": [{"doc_id": d.id, "name": d.name, "pages": d.pages, "chunks": d.chunks} for d in docs],
            "count": len(docs)}


@tool
def search_documents(
    query: Annotated[str, "Keywords to look for: names, numbers, terms that would appear in the text"],
    k: Annotated[int, "How many passages to return, 1-8"] = 5,
    doc_id: Annotated[str | None, "Limit to one document (from list_documents); omit to search all"] = None,
) -> dict:
    """Search the uploaded documents and return the most relevant passages with document name and
    page. Use this before answering any question about an uploaded file, and cite the page."""
    store = get_store()
    if not store.list():
        raise ValueError("no documents have been uploaded")
    if doc_id and not store.get(doc_id):
        raise ValueError(f"unknown doc_id '{doc_id}'. Call list_documents for valid ids")
    hits = store.search(query, max(1, min(int(k), 8)), doc_id)
    if not hits:
        return {"query": query, "results": [], "hint": "No keyword matches. Try other words or read_document."}
    return {"query": query, "results": hits}


@tool
def read_document(
    doc_id: Annotated[str, "Document id from list_documents"],
    start_chunk: Annotated[int, "First chunk to read (0 = beginning)"] = 0,
    count: Annotated[int, "How many chunks to read, 1-6"] = 3,
) -> dict:
    """Read a document in order, a few chunks at a time. Use to summarise a whole document or read
    around a passage found by search_documents."""
    store = get_store()
    info = store.get(doc_id)
    if not info:
        raise ValueError(f"unknown doc_id '{doc_id}'. Call list_documents for valid ids")
    count = max(1, min(int(count), 6))
    parts = store.read(doc_id, max(0, int(start_chunk)), count)
    nxt = start_chunk + len(parts)
    return {"document": info.name, "total_chunks": info.chunks, "chunks": parts,
            "next_start_chunk": nxt if nxt < info.chunks else None}
