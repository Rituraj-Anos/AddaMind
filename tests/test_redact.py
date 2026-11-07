from backend.chatintel.db import media_line, redact


def test_redact_personal_data():
    assert redact("call me on +91 98311 45678") == "call me on +•• ••••• ••678"
    assert redact("mail rohan.das@gmail.com") == "mail [email]"
    assert redact("pay rohan@okaxis bro") == "pay [upi id] bro"
    assert redact("OTP is 482913, don't share") == "OTP is [code], don't share"
    assert redact("aadhaar 1234 5678 9012") == "aadhaar •••• •••• •012"


def test_redact_keeps_normal_chat():
    for s in ("₹2,400 for Goa", "meet at 10:30 on 2026-11-07", "@Rohan ek minute", "batch of 2024", "", None):
        assert redact(s) == s


def test_media_line_redacts_transcripts():
    assert media_line("voice", None, "my number is 9831145678") == '[voice note] "my number is •••••••678"'
