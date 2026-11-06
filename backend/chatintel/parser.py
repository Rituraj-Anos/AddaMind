"""Parse WhatsApp chat exports: Android and iOS, a .txt or a .zip with media.

    python -m backend.chatintel.parser "WhatsApp Chat with College Friends.zip"
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath

MAX_TXT_BYTES = 200 * 1024 * 1024

# Newer exports wrap text in invisible direction marks and put a narrow no-break space before am/pm.
_LRM = "\u200e"
_INVISIBLE = {ord(c): None for c in "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff"}
_INVISIBLE.update({0x202F: " ", 0x00A0: " ", 0x2009: " "})

_DATE = r"(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{1,4})"
_TIME = r"(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?(?:\s?([AaPp])\.?\s?[Mm]\.?)?"
_ANDROID = re.compile(rf"^{_DATE},?\s+{_TIME}\s+[-–]\s+(.*)$")
_IOS = re.compile(rf"^\[{_DATE},?\s+{_TIME}\]\s+(.*)$")
_SENDER = re.compile(r"^([^\n:]{1,80}?):(?: (.*))?$", re.S)

_SYSTEM = re.compile(
    r"end-to-end encrypted|created group|created this group|changed the subject|changed the group|"
    r"changed this group's|deleted this group's icon|\badded\b|\bleft$|\bremoved\b|joined using|"
    r"security code|changed their phone number|changed to \+?\d|pinned a message|disappearing messages|"
    r"is a contact|now an admin|no longer an admin|missed (?:voice|video) call|voice call|video call", re.I)
_GROUP_EVENT = re.compile(
    r"created group|created this group|\badded\b|\bleft$|\bremoved\b|changed the subject|changed the group|"
    r"changed this group's icon|joined using|now an admin", re.I)
_SUBJECT = re.compile(
    r"(?:created group|changed the subject (?:from .+? )?to|changed the group name (?:from .+? )?to)\s*[\"“](.+?)[\"”]", re.I)

_ATTACHED_ANDROID = re.compile(r"^(?P<file>[^\n<>\"|?*]{1,200}\.[A-Za-z0-9]{2,5}) \(file attached\)(?:\n(?P<cap>.*))?$", re.S)
_ATTACHED_IOS = re.compile(r"<attached: (?P<file>[^>]+)>")
_OMITTED_IOS = re.compile(r"^(?P<file>.*?)\s*(?P<what>image|audio|video|sticker|GIF|document|Contact card) omitted$", re.I)
_EDITED = re.compile(r"\s*<This message was edited>\s*$")
_DELETED = {"this message was deleted", "this message was deleted.", "you deleted this message",
            "you deleted this message.", "this message was deleted by admin"}
_LOCATION = re.compile(r"^(?:live )?location: https?://", re.I)
_MENTION_TAGGED = re.compile("@\u2068~?\\s?([^\u2069]{1,60})\u2069")
_MENTION_PLAIN = re.compile(r"@(\+?\d[\d ]{6,}\d|[^\s@,.!?:;()\"'\u2068\u2069]{2,40})")

_OMITTED_KIND = {"image": "image", "audio": "voice", "video": "video", "sticker": "sticker",
                 "gif": "gif", "document": "document", "contact card": "contact"}
MEDIA_KINDS = {"image", "voice", "audio", "video", "sticker", "gif", "document", "contact"}


@dataclass
class Message:
    ts: datetime
    sender: str | None  # None for system lines
    kind: str  # text | system | image | voice | audio | video | sticker | gif | document | contact |
    #            location | poll | deleted | media_omitted | call
    text: str  # message text, or the media caption
    attachment: str | None = None  # file name in the export when the media is attached
    edited: bool = False
    mentions: list[str] = field(default_factory=list)  # participant names, resolved


@dataclass
class ParsedChat:
    title: str
    kind: str  # "group" | "direct"
    source_format: str  # "android" | "ios"
    date_order: str  # "dmy" | "mdy" | "ymd"
    participants: list[str]  # most active first
    messages: list[Message]
    me_guess: str | None = None  # for direct chats titled after the other person


@dataclass
class Export:
    text: str
    title_hint: str | None
    media: dict[str, str]  # file name -> path inside the zip
    filename: str


def clean(s: str) -> str:
    return s.translate(_INVISIBLE)


def norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", clean(s)).strip().lstrip("~").strip().casefold()


def media_kind(name: str) -> str:
    up, ext = name.upper(), PurePosixPath(name).suffix.lower()
    if up.startswith("STK-") or "-STICKER-" in up or ext == ".webp":
        return "sticker"
    if up.startswith("PTT-") or "-AUDIO-" in up or ext == ".opus":
        return "voice"
    if up.startswith("AUD-") or ext in {".m4a", ".mp3", ".aac", ".ogg", ".oga", ".wav", ".amr"}:
        return "audio"
    if "-GIF-" in up or ext == ".gif":
        return "gif"
    if up.startswith("VID-") or "-VIDEO-" in up or ext in {".mp4", ".3gp", ".mov", ".mkv", ".webm", ".avi"}:
        return "video"
    if up.startswith("IMG-") or "-PHOTO-" in up or ext in {".jpg", ".jpeg", ".png", ".heic", ".bmp"}:
        return "image"
    if ext == ".vcf":
        return "contact"
    return "document"


def _classify(body: str) -> tuple[str, str, str | None, bool]:
    """Cleaned message body -> (kind, text, attachment, edited)."""
    text = body
    edited = bool(_EDITED.search(text))
    text = _EDITED.sub("", text).strip()
    low = text.casefold()
    if low in _DELETED:
        return "deleted", "", None, edited
    if low in ("<media omitted>", "null"):
        return "media_omitted", "", None, edited
    m = _ATTACHED_ANDROID.match(text)
    if m:
        name = m.group("file").strip()
        return media_kind(name), (m.group("cap") or "").strip(), name, edited
    m = _ATTACHED_IOS.search(text)
    if m:
        name = m.group("file").strip()
        caption = (text[:m.start()] + text[m.end():]).strip()
        return media_kind(name), caption, name, edited
    m = _OMITTED_IOS.match(text)
    if m:
        return _OMITTED_KIND[m.group("what").casefold()], m.group("file").strip(" •"), None, edited
    if low.startswith("poll:"):
        return "poll", text[5:].strip(), None, edited
    if _LOCATION.match(text):
        return "location", text, None, edited
    if re.fullmatch(r"(missed )?(voice|video) call.*", low):
        return "call", text, None, edited
    return "text", text, None, edited


def _date_order(heads: list[re.Match]) -> str:
    if any(len(m.group(1)) == 4 for m in heads[:100]):
        return "ymd"
    dmy = any(int(m.group(1)) > 12 for m in heads)
    mdy = any(int(m.group(2)) > 12 for m in heads)
    return "mdy" if mdy and not dmy else "dmy"


def _timestamp(m: re.Match, order: str) -> datetime:
    a, b, c = m.group(1), m.group(2), m.group(3)
    y, mo, d = (a, b, c) if order == "ymd" else (c, a, b) if order == "mdy" else (c, b, a)
    year = int(y) + (2000 if len(y) <= 2 else 0)
    h, mi, s = int(m.group(4)), int(m.group(5)), int(m.group(6) or 0)
    ap = (m.group(7) or "").lower()
    if ap == "p" and h < 12:
        h += 12
    elif ap == "a" and h == 12:
        h = 0
    return datetime(year, int(mo), int(d), h, mi, s)


def _resolve_mention(token: str, people: list[str]) -> str | None:
    t = norm_name(token)
    t_digits = re.sub(r"\D", "", t)
    for p in people:
        pn = norm_name(p)
        if pn == t or pn.replace(" ", "") == t.replace(" ", "") or pn.split(" ")[0] == t:
            return p
        p_digits = re.sub(r"\D", "", pn)
        if len(t_digits) >= 8 and len(p_digits) >= 8 and (t_digits.endswith(p_digits[-10:]) or p_digits.endswith(t_digits[-10:])):
            return p
    return None


def parse_text(text: str, title_hint: str | None = None) -> ParsedChat:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [ln.lstrip(_LRM + "\ufeff").replace("\u202f", " ").replace("\xa0", " ") for ln in lines]
    sample = lines[:400]
    fmt = "ios" if sum(bool(_IOS.match(ln)) for ln in sample) > sum(bool(_ANDROID.match(ln)) for ln in sample) else "android"
    rx = _IOS if fmt == "ios" else _ANDROID

    heads = [(i, m) for i, ln in enumerate(lines) if (m := rx.match(ln))]
    if not heads:
        raise ValueError("no WhatsApp messages found. Is this a WhatsApp chat export?")
    order = _date_order([m for _, m in heads])
    stamped = []
    for i, m in heads:
        try:
            stamped.append((i, m, _timestamp(m, order)))
        except ValueError:
            continue  # looked like a header but isn't a real date: treat as message text
    if not stamped:
        raise ValueError("no valid timestamps found in the chat export")

    messages: list[Message] = []
    tagged: list[list[str]] = []
    plain: list[list[str]] = []
    subject = None
    group_events = 0
    for n, (i, m, ts) in enumerate(stamped):
        end = stamped[n + 1][0] if n + 1 < len(stamped) else len(lines)
        body = "\n".join([m.group(8)] + lines[i + 1:end]).rstrip()
        sender, raw = None, body
        sm = _SENDER.match(body)
        if sm and '"' not in sm.group(1) and "“" not in sm.group(1):
            sender, raw = clean(sm.group(1)).strip().lstrip("~").strip(), sm.group(2) or ""
        cleaned = clean(raw).strip()
        # iOS writes system lines as messages from the group or contact, marked with a leading LRM.
        ios_system = sender and raw.startswith(_LRM) and _SYSTEM.search(cleaned) and not _OMITTED_IOS.match(cleaned) \
            and not _ATTACHED_IOS.search(cleaned)
        if sender is None or ios_system:
            messages.append(Message(ts, None, "system", clean(body if sender is None else raw).strip()))
            tagged.append([])
            plain.append([])
            sys_text = messages[-1].text
            if _GROUP_EVENT.search(sys_text):
                group_events += 1
            if sub := _SUBJECT.search(sys_text):
                subject = sub.group(1).strip()
            continue
        kind, msg_text, attachment, edited = _classify(cleaned)
        messages.append(Message(ts, sender, kind, msg_text, attachment, edited))
        tagged.append(_MENTION_TAGGED.findall(raw))
        plain.append(_MENTION_PLAIN.findall(_MENTION_TAGGED.sub("", clean(raw))) if "@" in raw else [])

    counts = Counter(m.sender for m in messages if m.sender and m.kind != "call")
    people = [p for p, _ in counts.most_common()]
    for msg, tags, toks in zip(messages, tagged, plain):
        found = []
        for t in tags + toks:
            p = _resolve_mention(t, people)
            if p and p not in found and p != msg.sender:
                found.append(p)
        msg.mentions = found

    kind = "group" if group_events or len(people) > 2 else "direct"
    title = (subject or title_hint) if kind == "group" else (title_hint or subject)
    me_guess = None
    if kind == "direct" and len(people) == 2 and title:
        others = [p for p in people if norm_name(p) != norm_name(title)]
        if len(others) == 1:
            me_guess = others[0]
    if not title:
        title = " & ".join(people[:2]) if kind == "direct" else "Group chat"
    return ParsedChat(title, kind, fmt, order, people, messages, me_guess)


_TITLE_RX = [re.compile(r"^WhatsApp Chat with (.+)$", re.I), re.compile(r"^WhatsApp Chat\s*[-–]\s*(.+)$", re.I)]


def title_from_filename(name: str) -> str | None:
    stem = PurePosixPath(name.replace("\\", "/")).name
    stem = re.sub(r"\.(txt|zip)$", "", stem, flags=re.I)
    stem = re.sub(r"\s*\(\d+\)$", "", stem)  # "... (1)" from repeated downloads
    for rx in _TITLE_RX:
        if m := rx.match(stem):
            return m.group(1).strip()
    return None


def decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_export(data: bytes, filename: str) -> Export:
    """Find the chat text (and the media list) in a .txt or .zip export. Does not extract media."""
    buf = io.BytesIO(data)
    if not zipfile.is_zipfile(buf):
        if len(data) > MAX_TXT_BYTES:
            raise ValueError("chat text is too large")
        return Export(decode(data), title_from_filename(filename), {}, filename)
    with zipfile.ZipFile(buf) as z:
        files = [i for i in z.infolist() if not i.is_dir() and not i.filename.startswith("__MACOSX")]
        txts = [i for i in files if i.filename.lower().endswith(".txt")]
        if not txts:
            raise ValueError("the zip has no chat .txt file")

        def score(info: zipfile.ZipInfo):
            base = PurePosixPath(info.filename).name.lower()
            return base == "_chat.txt" or base.startswith("whatsapp chat"), info.file_size

        chat = max(txts, key=score)
        if chat.file_size > MAX_TXT_BYTES:
            raise ValueError("chat text is too large")
        text = decode(z.read(chat))
        media = {PurePosixPath(i.filename).name: i.filename for i in files if i is not chat}
    hint = title_from_filename(filename) or title_from_filename(chat.filename)
    return Export(text, hint, media, filename)


def parse_export(data: bytes, filename: str) -> tuple[ParsedChat, Export]:
    export = read_export(data, filename)
    return parse_text(export.text, export.title_hint), export


def main(path: str) -> None:
    with open(path, "rb") as f:
        chat, export = parse_export(f.read(), path)
    kinds = Counter(m.kind for m in chat.messages)
    attached = [m.attachment for m in chat.messages if m.attachment]
    missing = [a for a in attached if a not in export.media]
    print(f"title        {chat.title}")
    print(f"kind         {chat.kind}   format {chat.source_format}   date order {chat.date_order}")
    print(f"messages     {len(chat.messages)}   {chat.messages[0].ts:%d %b %Y} to {chat.messages[-1].ts:%d %b %Y}")
    print(f"participants {len(chat.participants)}: {', '.join(chat.participants[:6])}{' ...' if len(chat.participants) > 6 else ''}")
    print(f"me (guess)   {chat.me_guess or '-'}")
    print(f"kinds        {dict(kinds.most_common())}")
    print(f"media        {len(attached)} attached, {len(attached) - len(missing)} present in export, {len(missing)} missing")


if __name__ == "__main__":
    main(sys.argv[1])
