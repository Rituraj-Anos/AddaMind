import io
import zipfile
from datetime import datetime

import pytest

from backend.chatintel.parser import media_kind, parse_export, parse_text, title_from_filename

NNBSP, LRM = "\u202f", "\u200e"

ANDROID_GROUP = f"""03/02/25, 7:30{NNBSP}pm - Messages and calls are end-to-end encrypted. Only people in this chat can read, listen to, or share them. Learn more.
03/02/25, 7:30{NNBSP}pm - Priya Sen created group "College Friends"
03/02/25, 7:31{NNBSP}pm - Priya Sen added You
14/03/25, 4:12{NNBSP}am - Abhishek Kundu: BHAI TICKETS GHAR PE BHOOL GAYA
14/03/25, 4:13{NNBSP}am - Priya Sen: @\u2068Abhishek Kundu\u2069 PNR se ho jayega, chill
14/03/25, 12:40{NNBSP}pm - Priya Sen: location: https://maps.google.com/?q=15.5527,73.7517
15/03/25, 6:05{NNBSP}pm - Rohan Das: PTT-20250315-WA0004.opus (file attached)
15/03/25, 6:06{NNBSP}pm - Arjun Mehta: IMG-20250315-WA0005.jpg (file attached)
Baga beach day
15/03/25, 6:07{NNBSP}pm - Sayan Mukherjee: Packing list:
1. Aadhaar
2. Sunscreen
15/03/25, 6:08{NNBSP}pm - Kabir Malhotra: <Media omitted>
15/03/25, 6:09{NNBSP}pm - Kabir Malhotra: kal 6 baje <This message was edited>
15/03/25, 6:10{NNBSP}pm - Rohan Das: This message was deleted
14/08/25, 4:20{NNBSP}pm - Kabir Malhotra left
"""

IOS_DIRECT = f"""[10/02/25, 8:01:00{NNBSP}PM] Shrimant: {LRM}Messages and calls are end-to-end encrypted. Only people in this chat can read, listen to, or share them.
[10/02/25, 8:02:11{NNBSP}PM] Shrimant: bro kitne din baad!
[10/02/25, 8:10:40{NNBSP}PM] Suman Ghosh: pakka. 10 baje gate pe
{LRM}[16/02/25, 10:40:05{NNBSP}AM] Shrimant: {LRM}<attached: 00000003-PHOTO-2025-02-16-10-40-05.jpg>
[16/02/25, 10:41:00{NNBSP}AM] Suman Ghosh: {LRM}audio omitted
[16/02/25, 10:42:00{NNBSP}AM] Shrimant: {LRM}This message was deleted.
[16/02/25, 10:43:00{NNBSP}AM] Suman Ghosh: thik hai {LRM}<This message was edited>
"""


def by_text(chat, needle):
    return next(m for m in chat.messages if needle in m.text)


def test_android_group_basics():
    chat = parse_text(ANDROID_GROUP, "College Friends")
    assert chat.source_format == "android" and chat.date_order == "dmy" and chat.kind == "group"
    assert chat.title == "College Friends"
    assert set(chat.participants) == {"Abhishek Kundu", "Priya Sen", "Rohan Das", "Arjun Mehta", "Sayan Mukherjee", "Kabir Malhotra"}
    first = by_text(chat, "TICKETS")
    assert first.ts == datetime(2025, 3, 14, 4, 12) and first.sender == "Abhishek Kundu" and first.kind == "text"
    assert by_text(chat, "maps.google").kind == "location"
    assert sum(m.kind == "system" for m in chat.messages) == 4


def test_android_media_multiline_edits_and_mentions():
    chat = parse_text(ANDROID_GROUP)
    voice = next(m for m in chat.messages if m.attachment and m.attachment.startswith("PTT"))
    assert voice.kind == "voice" and voice.sender == "Rohan Das"
    photo = next(m for m in chat.messages if m.attachment and m.attachment.startswith("IMG"))
    assert photo.kind == "image" and photo.text == "Baga beach day"
    assert by_text(chat, "Packing list").text == "Packing list:\n1. Aadhaar\n2. Sunscreen"
    assert any(m.kind == "media_omitted" for m in chat.messages)
    edited = by_text(chat, "kal 6 baje")
    assert edited.edited and edited.text == "kal 6 baje"
    assert any(m.kind == "deleted" and m.sender == "Rohan Das" for m in chat.messages)
    assert by_text(chat, "PNR").mentions == ["Abhishek Kundu"]


def test_ios_direct_chat_and_me_guess():
    chat = parse_text(IOS_DIRECT, "Shrimant")
    assert chat.source_format == "ios" and chat.kind == "direct"
    assert set(chat.participants) == {"Shrimant", "Suman Ghosh"}
    assert chat.me_guess == "Suman Ghosh"
    assert chat.messages[0].kind == "system"  # LRM-marked encryption notice from the contact
    photo = next(m for m in chat.messages if m.attachment)
    assert photo.kind == "image" and photo.ts == datetime(2025, 2, 16, 10, 40, 5)
    assert any(m.kind == "voice" and m.attachment is None for m in chat.messages)  # "audio omitted"
    assert any(m.kind == "deleted" for m in chat.messages)
    assert by_text(chat, "thik hai").edited


def test_ios_group_system_messages_are_not_participants():
    text = (f"[03/02/25, 7:30:00 PM] College Friends: {LRM}Priya Sen created group “College Friends”\n"
            f"[03/02/25, 7:30:05 PM] College Friends: {LRM}Priya Sen added Rohan Das\n"
            "[03/02/25, 7:31:00 PM] Priya Sen: welcome\n"
            "[03/02/25, 7:32:00 PM] Rohan Das: thanks\n")
    chat = parse_text(text)
    assert chat.kind == "group" and chat.title == "College Friends"
    assert "College Friends" not in chat.participants


def test_us_month_first_dates_and_24h_and_4_digit_years():
    us = "3/14/25, 9:05 PM - Ann: hi\n3/15/25, 10:00 AM - Bob: yo\n"
    chat = parse_text(us)
    assert chat.date_order == "mdy" and chat.messages[0].ts == datetime(2025, 3, 14, 21, 5)
    eu = "14.03.2025, 21:05 - Ann: hi\n15.03.2025, 09:00 - Bob: yo\n"
    assert parse_text(eu).messages[1].ts == datetime(2025, 3, 15, 9, 0)


def test_direct_chat_with_two_senders_is_not_a_group():
    chat = parse_text("01/01/25, 10:00 - A: hi\n01/01/25, 10:01 - B: hey\n", "A")
    assert chat.kind == "direct" and chat.me_guess == "B"


def test_header_looking_text_inside_a_message_stays_text():
    chat = parse_text("01/01/25, 10:00 - A: note:\n99/99/99, 10:00 - not a real date\n01/01/25, 10:01 - B: ok\n")
    assert len(chat.messages) == 2 and "99/99/99" in chat.messages[0].text


def test_rejects_non_exports():
    with pytest.raises(ValueError):
        parse_text("just some notes\nnothing here")


@pytest.mark.parametrize("name,kind", [
    ("IMG-20250315-WA0005.jpg", "image"), ("PTT-20250315-WA0004.opus", "voice"), ("AUD-20250101-WA0001.m4a", "audio"),
    ("VID-20250315-WA0002.mp4", "video"), ("STK-20250315-WA0009.webp", "sticker"), ("OS_Unit3_Notes.pdf", "document"),
    ("00000012-PHOTO-2025-03-14-21-05-33.jpg", "image"), ("00000013-AUDIO-2025-03-14-21-05-33.opus", "voice"),
    ("Rohan.vcf", "contact"),
])
def test_media_kind(name, kind):
    assert media_kind(name) == kind


def test_titles_from_file_names():
    assert title_from_filename("WhatsApp Chat with College Friends.txt") == "College Friends"
    assert title_from_filename("WhatsApp Chat - Shrimant.zip") == "Shrimant"
    assert title_from_filename("WhatsApp Chat with Mom (1).zip") == "Mom"
    assert title_from_filename("_chat.txt") is None


def test_zip_export_finds_chat_text_and_media():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("_chat.txt", IOS_DIRECT)
        z.writestr("00000003-PHOTO-2025-02-16-10-40-05.jpg", b"\xff\xd8fake")
    chat, export = parse_export(buf.getvalue(), "WhatsApp Chat - Shrimant.zip")
    assert chat.title == "Shrimant"
    assert "00000003-PHOTO-2025-02-16-10-40-05.jpg" in export.media


DEMO = __import__("pathlib").Path(__file__).resolve().parents[2] / "data" / "demo"


@pytest.mark.skipif(not (DEMO / "facts.json").exists(), reason="run scripts/make_demo_data.py first")
def test_generated_demo_exports_parse():
    import json
    facts = json.loads((DEMO / "facts.json").read_text(encoding="utf-8"))
    group, export = parse_export((DEMO / "WhatsApp Chat with College Friends.zip").read_bytes(), "WhatsApp Chat with College Friends.zip")
    assert group.kind == "group" and group.title == "College Friends"
    assert len(group.participants) == facts["group"]["members"] == 20
    attached = [m.attachment for m in group.messages if m.attachment]
    assert len(attached) == facts["counts"]["group_media"] and all(a in export.media for a in attached)
    direct, _ = parse_export((DEMO / "WhatsApp Chat - Shrimant.zip").read_bytes(), "WhatsApp Chat - Shrimant.zip")
    assert direct.kind == "direct" and direct.source_format == "ios" and direct.me_guess == facts["me"]
