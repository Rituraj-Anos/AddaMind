"""Evidence search over chats: keyword (FTS5) on messages and passages, plus embeddings on passages,
merged by reciprocal rank. Every result is a real message with its ID, scoped to one project.

    python -m backend.chatintel.retrieval <project_id> "who forgot the tickets"
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from . import db, embeddings
from .analytics import STOPWORDS

PASSAGE_GAP = timedelta(minutes=45)
PASSAGE_MAX_CHARS = 1200
PASSAGE_MAX_MSGS = 25
RRF_K = 60
_TOKEN = re.compile(r"[\w\u0900-\u097f\u0980-\u09ff]+")
_QUESTION_WORDS = {"who", "whom", "whose", "when", "which", "did", "does", "was", "were", "the", "what", "where",
                   "how", "why", "said", "say", "tell", "about", "kisne", "kaun", "kab", "kya", "kahan", "kyun"}


def _tokens(q: str) -> list[str]:
    """Query words worth matching: stopwords and question words dropped, unless nothing would be left."""
    toks = [t for t in _TOKEN.findall(q.casefold()) if len(t) > 1]
    useful = [t for t in toks if t not in STOPWORDS and t not in _QUESTION_WORDS]
    # Drop a plural 's' so the prefix match finds both forms ("tickets" -> ticket*).
    return [t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else t for t in (useful or toks)][:12]


@dataclass
class Scope:
    """What a search may read. chat_id narrows to one chat, participant_id to one person's messages."""
    project_id: int
    chat_id: int | None = None
    participant_id: int | None = None


def _line(r) -> str:
    if r["kind"] == "system":
        return f"(group event) {db.redact(r['text'])}"
    who = db.shown_name(r["sender"], r["masked"]) or "?"
    return f"{who}: {db.media_line(r['kind'], r['text'], r['media_result'])}"


# ---------------------------------------------------------------- passages
def build_passages(pid: int, cid: int, on_progress=None) -> dict:
    """Group the chat's messages without a passage into passages, then embed the new passages.
    Re-running after a merge only adds passages for the new messages."""
    with db.connect() as con:
        if not con.execute("SELECT 1 FROM chats WHERE id = ? AND project_id = ?", (cid, pid)).fetchone():
            raise ValueError("chat not found")
        rows = con.execute("""
            SELECT m.id, m.ts, m.kind, m.text, p.name AS sender, p.masked, md.result AS media_result
            FROM messages m LEFT JOIN participants p ON p.id = m.participant_id
            LEFT JOIN media md ON md.message_id = m.id
            WHERE m.chat_id = ? AND m.passage_id IS NULL
            ORDER BY m.ts, m.id""", (cid,)).fetchall()
    groups, cur, size, last = [], [], 0, None
    for r in rows:
        ts, line = datetime.fromisoformat(r["ts"]), _line(r)
        if cur and (ts - last > PASSAGE_GAP or size + len(line) > PASSAGE_MAX_CHARS or len(cur) >= PASSAGE_MAX_MSGS):
            groups.append(cur)
            cur, size = [], 0
        cur.append((r, line))
        size += len(line) + 1
        last = ts
    if cur:
        groups.append(cur)

    new_ids = []
    with db.connect() as con:
        for g in groups:
            text = "\n".join(line for _, line in g)
            pid_ = con.execute("INSERT INTO passages(chat_id, first_msg, last_msg, first_ts, last_ts, text) "
                               "VALUES (?, ?, ?, ?, ?, ?)",
                               (cid, g[0][0]["id"], g[-1][0]["id"], g[0][0]["ts"], g[-1][0]["ts"], text)).lastrowid
            con.executemany("UPDATE messages SET passage_id = ? WHERE id = ?", [(pid_, r["id"]) for r, _ in g])
            new_ids.append((pid_, text))
    vectors = embeddings.embed_documents([t for _, t in new_ids], on_progress)
    with db.connect() as con:
        con.executemany("UPDATE passages SET model = ?, embedding = ? WHERE id = ?",
                        [(mv[0], embeddings.to_blob(mv[1]), i) for (i, _), mv in zip(new_ids, vectors) if mv])
    embedded = sum(1 for v in vectors if v)
    return {"passages": len(new_ids), "embedded": embedded}


def embed_missing(pid: int, cid: int) -> int:
    """Retry embeddings for passages that have none (after a quota error). Returns how many were added."""
    with db.connect() as con:
        rows = con.execute("SELECT ps.id, ps.text FROM passages ps JOIN chats c ON c.id = ps.chat_id "
                           "WHERE ps.chat_id = ? AND c.project_id = ? AND ps.embedding IS NULL", (cid, pid)).fetchall()
    vectors = embeddings.embed_documents([r["text"] for r in rows])
    with db.connect() as con:
        con.executemany("UPDATE passages SET model = ?, embedding = ? WHERE id = ?",
                        [(mv[0], embeddings.to_blob(mv[1]), r["id"]) for r, mv in zip(rows, vectors) if mv])
    return sum(1 for v in vectors if v)


def refresh_passages(pid: int, cid: int, passage_ids: list[int]) -> int:
    """Rebuild the text of passages whose messages changed (media results arrived), then re-embed them."""
    with db.connect() as con:
        for ps in passage_ids:
            rows = con.execute(f"""
                SELECT m.id, m.ts, m.kind, m.text, p.name AS sender, p.masked, md.result AS media_result
                FROM messages m JOIN chats c ON c.id = m.chat_id AND c.project_id = ?
                LEFT JOIN participants p ON p.id = m.participant_id LEFT JOIN media md ON md.message_id = m.id
                WHERE m.passage_id = ? AND m.chat_id = ? ORDER BY m.ts, m.id""", (pid, ps, cid)).fetchall()
            if not rows:
                continue
            text = "\n".join(_line(r) for r in rows)
            con.execute("UPDATE passages SET text = ?, model = NULL, embedding = NULL WHERE id = ?", (text, ps))
            con.execute("UPDATE passages_fts SET text = ? WHERE rowid = ?", (text, ps))
    return embed_missing(pid, cid)


# ---------------------------------------------------------------- search
def _fts_query(tokens: list[str]) -> str | None:
    """Words to an FTS5 OR query with prefix matching. Quoting each token keeps user input inert."""
    return " OR ".join(f'"{t}"*' for t in tokens) or None


def _filters(scope: Scope, alias: str, since: str | None, until: str | None) -> tuple[str, list]:
    sql, args = ["c.project_id = ?"], [scope.project_id]
    if scope.chat_id is not None:
        sql.append(f"{alias}.chat_id = ?")
        args.append(scope.chat_id)
    if since:
        sql.append(f"{alias}.{'ts' if alias == 'm' else 'last_ts'} >= ?")
        args.append(since)
    if until:
        sql.append(f"{alias}.{'ts' if alias == 'm' else 'first_ts'} < ?")
        args.append(until)
    return " AND ".join(sql), args


def _hits(text: str, tokens: list[str]) -> int:
    text = text.casefold()
    return sum(1 for t in tokens if t in text)


def _rerank(rows, tokens: list[str], k: int) -> list[int]:
    # bm25 punishes length hard and chat messages are short, so "ok goa" beats a message naming
    # every query word. Matching more distinct query words comes first; bm25 breaks ties.
    return [r["id"] for r in sorted(rows, key=lambda r: (-_hits(r["text"], tokens), r["score"]))[:k]]


def _keyword_messages(con, scope, fq, tokens, since, until, k) -> list[int]:
    where, args = _filters(scope, "m", since, until)
    if scope.participant_id is not None:
        where += " AND m.participant_id = ?"
        args.append(scope.participant_id)
    rows = con.execute(f"SELECT m.id, f.text, bm25(messages_fts) AS score FROM messages_fts f "
                       f"JOIN messages m ON m.id = f.rowid JOIN chats c ON c.id = m.chat_id "
                       f"WHERE messages_fts MATCH ? AND {where} ORDER BY score LIMIT 300", [fq, *args]).fetchall()
    return _rerank(rows, tokens, k)


def _keyword_passages(con, scope, fq, tokens, since, until, k) -> list[int]:
    where, args = _filters(scope, "ps", since, until)
    rows = con.execute(f"SELECT ps.id, f.text, bm25(passages_fts) AS score FROM passages_fts f "
                       f"JOIN passages ps ON ps.id = f.rowid JOIN chats c ON c.id = ps.chat_id "
                       f"WHERE passages_fts MATCH ? AND {where} ORDER BY score LIMIT 300", [fq, *args]).fetchall()
    return _rerank(rows, tokens, k)


def _vector_passages(con, scope, query, since, until, k) -> tuple[list[tuple[int, int]], list[str]]:
    """[(passage id, rank)] ranked separately per embedding model, since vectors from different models
    can't be compared. A quota fallback can leave one chat with passages from both."""
    where, args = _filters(scope, "ps", since, until)
    rows = con.execute(f"SELECT ps.id, ps.model, ps.embedding FROM passages ps JOIN chats c ON c.id = ps.chat_id "
                       f"WHERE ps.embedding IS NOT NULL AND {where}", args).fetchall()
    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append(r)
    ranked, used = [], []
    for model, group in by_model.items():
        try:
            q = embeddings.embed([query], model, query=True)[0]
        except embeddings.EmbeddingError:
            continue
        sims = np.stack([embeddings.from_blob(r["embedding"]) for r in group]) @ q
        ranked += [(group[i]["id"], rank) for rank, i in enumerate(np.argsort(-sims)[:k])]
        used.append(model)
    return ranked, sorted(used)


def _best_in_passage(con, passage_id: int, tokens: list[str], participant_id: int | None) -> list[int]:
    """The messages of a passage that share the most query words (at least one message)."""
    rows = con.execute("SELECT m.id, m.text, m.participant_id, md.result FROM messages m "
                       "LEFT JOIN media md ON md.message_id = m.id WHERE m.passage_id = ? ORDER BY m.ts, m.id",
                       (passage_id,)).fetchall()
    if participant_id is not None:
        rows = [r for r in rows if r["participant_id"] == participant_id]
    if not rows:
        return []

    def hits(r):
        return _hits(f"{r['text'] or ''} {r['result'] or ''}", tokens)

    best = max(hits(r) for r in rows)
    if best == 0:
        # shortcut: a semantic match with no shared words anchors on the longest message; the context lines
        # still carry every nearby ID. Upgrade to per-message embeddings if anchors look wrong on real chats.
        return [max(rows, key=lambda r: (len(r["text"] or "") + len(r["result"] or ""), -r["id"]))["id"]]
    return [r["id"] for r in rows if hits(r) == best][:3]


def _context(con, pid: int, mid: int, passage_id: int | None, n: int = 4) -> str | None:
    """Up to n messages either side of `mid` from its passage, one per line as '[m:ID] Name: text'."""
    if not passage_id:
        return None
    rows = con.execute(db.MSG_SELECT + " WHERE m.passage_id = ? ORDER BY m.ts, m.id", (pid, passage_id)).fetchall()
    i = next((i for i, r in enumerate(rows) if r["id"] == mid), 0)
    lines = [f"[m:{r['id']}] {_line(r)[:160]}" for r in rows[max(i - n, 0): i + n + 1]]
    return "\n".join(lines)


def search(scope: Scope, query: str, k: int = 8, since: str | None = None, until: str | None = None) -> dict:
    """Top-k messages for `query` within `scope`, each with its passage for context.
    since/until are 'YYYY-MM-DD' (until is exclusive). Methods used are reported so the UI can show them."""
    query = (query or "").strip()
    if not query:
        raise ValueError("query is empty")
    tokens = _tokens(query)
    fq = _fts_query(tokens)
    ranks: dict[int, float] = defaultdict(float)
    via: dict[int, set] = defaultdict(set)
    methods = []
    with db.connect() as con:
        if fq:
            methods.append("keyword")
            for rank, mid in enumerate(_keyword_messages(con, scope, fq, tokens, since, until, 3 * k)):
                ranks[mid] += 1 / (RRF_K + rank)
                via[mid].add("keyword")
            for rank, ps in enumerate(_keyword_passages(con, scope, fq, tokens, since, until, 2 * k)):
                for mid in _best_in_passage(con, ps, tokens, scope.participant_id):
                    ranks[mid] += 0.5 / (RRF_K + rank)
                    via[mid].add("keyword")
        vec_ids, models = _vector_passages(con, scope, query, since, until, 2 * k)
        if models:
            methods.append(f"semantic ({', '.join(models)})")
        for ps, rank in vec_ids:
            for mid in _best_in_passage(con, ps, tokens, scope.participant_id):
                ranks[mid] += 1 / (RRF_K + rank)
                via[mid].add("semantic")
        top = sorted(ranks, key=lambda m: (-ranks[m], m))[:k]
        results = []
        for mid in top:
            row = con.execute(db.MSG_SELECT + " WHERE m.id = ?", (scope.project_id, mid)).fetchone()
            if not row:
                continue
            msg = db.message_json(row)
            ps_id = con.execute("SELECT passage_id FROM messages WHERE id = ?", (mid,)).fetchone()[0]
            title = con.execute("SELECT title FROM chats WHERE id = ?", (msg["chat_id"],)).fetchone()["title"]
            results.append({**msg, "chat_title": title, "score": round(ranks[mid] * 1000, 2),
                            "matched_by": sorted(via[mid]), "context": _context(con, scope.project_id, mid, ps_id)})
    return {"query": query, "methods": methods or ["none"], "results": results}


def messages_around(pid: int, message_id: int, n: int = 5) -> dict | None:
    """The n messages before and after one message, within the same chat and project."""
    return db.get_message(pid, message_id, n)


def main(argv: list[str]) -> None:
    pid, query = int(argv[0]), " ".join(argv[1:])
    out = search(Scope(pid), query)
    print("methods:", ", ".join(out["methods"]))
    for r in out["results"]:
        body = db.media_line(r["kind"], r["text"], (r["media"] or {}).get("result"))
        print(f"[[m:{r['id']}]] {r['ts']} {r['chat_title']} | {r['sender']}: {body[:110]}  {r['matched_by']} {r['score']}")


if __name__ == "__main__":
    main(sys.argv[1:])
