"""Roast safety (F6.4). Behaviour is fair game; identity is not.

1. The request is refused before any model call if it targets a protected topic or an opted-out person.
2. Every roast is checked by keywords and by a second model call that rewrites or drops unsafe lines.
3. A rewrite must pass the keyword check too, or the roast is dropped.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from backend.core.structured import structured

# English plus common Hinglish words, for each protected topic in the PRD.
PROTECTED = {
    # Common banter words ("oh god", "I'm dead", "pagal hai kya") are left out on purpose: the model check
    # judges those in context.
    "appearance or body": r"fat|fatty|obese|skinny|ugly|weight|height|bald|skin colou?r|kaala|kali|gora|mota|"
                          r"moti|motu|patla|takla|body|teeth|pimples?|acne|hair ?line",
    "health": r"sick|illness|disease|cancer|diabet\w*|mental|depress\w*|anxiety|therapy|medicine|hospital|bimar\w*",
    "religion": r"relig\w*|hindu|muslim|islam|christian|sikh|jain|buddh\w*|allah|bhagwan|dharm\w*|mandir|masjid|church",
    "caste": r"caste|jaat|jati|brahmin|dalit|obc|sc/st|reservation",
    "ethnicity or region": r"race|racial|ethnic\w*|bihari|madrasi|chinki|bong|gujju|northeast\w*|accent",
    "gender or sexuality": r"gay|lesbian|homo|trans\w*|sexual\w*|gender|girly|chhakka|meetha|feminine|masculine",
    "disability": r"disab\w*|retard\w*|cripple|blind|deaf|lame|stammer\w*|autis\w*",
    "money": r"money|poor|broke|garib|gareeb|kanjoos|salary|loan|udhaar|debt|paisa|paise|rupees?|₹\s?[\d,]+|rs\.?\s?\d+",
    "family": r"family|mother|mom|maa|mummy|father|dad|papa|sister|behen|parents?|ghar ?wale",
    "trauma": r"death|suicide|abuse|accident|funeral|divorce|breakup",
}
# Lookarounds instead of \b, so '₹2,400' (which starts with a non-word character) still matches.
_PROTECTED_RX = {k: re.compile(rf"(?<!\w)(?:{v})(?!\w)", re.I) for k, v in PROTECTED.items()}
TONES = {
    "wholesome": "Gentle and affectionate, the kind of roast a best friend says at a birthday. No sting.",
    "spicy": "Cheeky and teasing, with a clear punchline, but warm underneath.",
    "savage": "Sharp, fast and merciless about habits, like a stand-up roast. Still only about behaviour in the chat.",
}


def protected_topic(text: str) -> str | None:
    for topic, rx in _PROTECTED_RX.items():
        if rx.search(text or ""):
            return topic
    return None


def request_issue(message: str) -> str | None:
    """Why a roast request must be refused, or None."""
    topic = protected_topic(message)
    if topic:
        return (f"I roast habits from the chat, not {topic}. Try asking about something they do, "
                f"like their voice notes, late replies or catchphrases.")
    return None


class Verdict(BaseModel):
    index: int
    safe: bool = Field(description="true if the roast only mocks behaviour seen in the chat")
    problem: str = Field(description="empty if safe, else which rule it breaks")
    rewrite: str = Field(description="if unsafe: the same joke aimed only at the behaviour, same tone; else empty")


class Verdicts(BaseModel):
    verdicts: list[Verdict]


CHECK = """You review roasts written about friends from their group chat. Allowed: teasing habits seen
in the chat (voice notes, late replies, night messages, catchphrases, being late, planning, emoji, ghosting).
Not allowed: anything about appearance or body, health, religion, caste, ethnicity or region, gender or
sexuality, disability, money or what someone owes, family, or trauma. Also not allowed: slurs, threats,
sexual content, or claims that are not about the chat. Tone '{tone}' is allowed to be harsh about habits.
For each roast, say if it is safe. If not, rewrite it to keep the joke but aim it only at the behaviour."""


def check_roasts(roasts: list[str], tone: str, router=None) -> list[dict]:
    """[{text, status: ok|rewritten|dropped, problem}] in the same order."""
    out = [{"text": r, "status": "ok", "problem": ""} for r in roasts]
    if not roasts:
        return out
    listing = "\n".join(f"{i}. {r}" for i, r in enumerate(roasts))
    try:
        verdicts = structured(f"Roasts:\n{listing}", Verdicts, system=CHECK.format(tone=tone), router=router).verdicts
    except Exception:  # noqa: BLE001 - without the second check, fall back to keywords only
        verdicts = []
    by_index = {v.index: v for v in verdicts}
    for i, item in enumerate(out):
        v = by_index.get(i)
        topic = protected_topic(item["text"])
        if (v and not v.safe) or topic:
            fix = (v.rewrite if v else "").strip()
            if fix and not protected_topic(fix):
                item.update(text=fix, status="rewritten", problem=(v.problem if v else "") or topic or "")
            else:
                item.update(status="dropped", problem=(v.problem if v and v.problem else topic) or "unsafe")
    return out
