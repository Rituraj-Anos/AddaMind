import pytest

from backend.core import keys
from backend.core.llm import AllModelsFailed, LLMError, LLMResponse, Message, LLMRouter, build_chain
from backend.core.llm.base import Provider


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    keys.reset()
    for name in ("DEMO_API_KEY", "DEMO_API_KEYS", "GEMINI_API_KEY", "GEMINI_API_KEYS", "GROQ_API_KEY", "GROQ_API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    yield
    keys.reset()


def test_keys_come_from_both_variables_in_order_without_duplicates(monkeypatch):
    assert keys.env_keys("DEMO_API_KEY") == []
    monkeypatch.setenv("DEMO_API_KEY", " a ")
    monkeypatch.setenv("DEMO_API_KEYS", 'b, "c" ;a\nd,,')
    assert keys.env_keys("DEMO_API_KEY") == ["a", "b", "c", "d"]


class Resp:
    def __init__(self, status, headers=None, text=""):
        self.status_code, self.headers, self.text = status, headers or {}, text
        self.ok = status < 400


def test_rate_limited_key_rests_and_the_next_key_answers(monkeypatch):
    monkeypatch.setenv("DEMO_API_KEYS", "k1,k2,k3")
    used = []

    def send(key):
        used.append(key)
        return Resp(429, {"retry-after": "30"}) if key == "k1" else Resp(200)

    assert keys.request_with_keys("DEMO_API_KEY", send).status_code == 200
    assert used == ["k1", "k2"]
    used.clear()
    keys.request_with_keys("DEMO_API_KEY", send)
    assert used == ["k2"]  # k1 is resting, so it isn't even tried
    assert keys.status("DEMO_API_KEY") == {"configured": 3, "ready": 2, "resting": 1, "rejected": 0}


def test_rejected_key_is_dropped_and_all_failing_returns_the_last_response(monkeypatch):
    monkeypatch.setenv("DEMO_API_KEYS", "bad,good")
    used = []
    send = lambda key: used.append(key) or (Resp(400, text='{"message": "API key not valid"}') if key == "bad" else Resp(200))  # noqa: E731
    assert keys.request_with_keys("DEMO_API_KEY", send).status_code == 200
    used.clear()
    keys.request_with_keys("DEMO_API_KEY", send)
    assert used == ["good"]
    assert keys.status("DEMO_API_KEY")["rejected"] == 1

    keys.reset()
    monkeypatch.setenv("DEMO_API_KEYS", "x,y")
    assert keys.request_with_keys("DEMO_API_KEY", lambda k: Resp(429)).status_code == 429


def test_no_key_still_makes_the_call_once(monkeypatch):
    seen = []
    assert keys.request_with_keys("DEMO_API_KEY", lambda k: seen.append(k) or Resp(401)).status_code == 401
    assert seen == [""]


class Fake(Provider):
    """Answers or fails depending on which key it holds, and records who was asked."""
    provider = "gemini"
    asked: list[str] = []
    outcome: dict[str, str] = {}

    def chat(self, messages, tools=None, **kw):
        key = self._api_key()
        Fake.asked.append(f"{self.model}/{key}")
        verdict = Fake.outcome.get(f"{self.model}/{key}", "ok")
        if verdict != "ok":
            raise self._err(verdict, verdict, status={"rate_limit": 429, "auth": 401}.get(verdict))
        return LLMResponse(text=f"from {self.model}/{key}", tool_calls=[], provider="gemini", model=self.model, latency_ms=1)


def fake_chain(monkeypatch, models=("m1", "m2")):
    Fake.asked, Fake.outcome = [], {}
    monkeypatch.setattr("backend.core.llm.router.GeminiProvider",
                        lambda model, key_env, timeout_s, key_index=0: Fake(model, key_env=key_env, timeout_s=timeout_s, key_index=key_index))
    return build_chain(",".join(f"gemini:{m}" for m in models))


def test_chain_has_one_entry_per_model_and_key_with_the_keys_of_one_model_together(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "k1,k2")
    chain = fake_chain(monkeypatch)
    assert [p.key for p in chain] == ["gemini:m1", "gemini:m1#2", "gemini:m2", "gemini:m2#2"]


def test_a_rate_limited_key_hands_over_to_the_next_key_of_the_same_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "k1,k2")
    router = LLMRouter(fake_chain(monkeypatch), persist=False, rounds=1)
    Fake.outcome["m1/k1"] = "rate_limit"
    out = router.chat([Message("user", "hi")])
    assert out.text == "from m1/k2" and Fake.asked == ["m1/k1", "m1/k2"]  # same model, second key; m2 untouched
    Fake.asked.clear()
    assert router.chat([Message("user", "again")]).text == "from m1/k2"
    assert Fake.asked == ["m1/k2"]  # the resting key isn't retried, the working key stays sticky
    status = router.status()
    assert next(c for c in status["chain"] if c["key"] == "gemini:m1")["cooldown_s"] > 0
    assert "k1" not in str(status) and "k2" not in str(status)  # counts and names only


def test_a_rejected_key_is_dropped_but_other_keys_of_that_provider_keep_working(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "bad,good")
    router = LLMRouter(fake_chain(monkeypatch), persist=False, rounds=1)
    Fake.outcome.update({"m1/bad": "auth", "m2/bad": "auth"})
    assert router.chat([Message("user", "hi")]).text == "from m1/good"
    Fake.asked.clear()
    router.chat([Message("user", "again")])
    assert "m1/bad" not in Fake.asked and "m2/bad" not in Fake.asked
    assert router.status()["keys"] == {"gemini": {"configured": 2, "rejected": 1}}


def test_one_key_behaves_as_before(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "only")
    chain = fake_chain(monkeypatch)
    assert [p.key for p in chain] == ["gemini:m1", "gemini:m2"]
    router = LLMRouter(chain, persist=False, rounds=1)
    Fake.outcome["m1/only"] = "auth"
    assert router.chat([Message("user", "hi")]).text == "from m2/only"  # this call still reaches m2
    with pytest.raises(AllModelsFailed):  # but the only key was refused, so the provider is out, as before
        router.chat([Message("user", "again")])
