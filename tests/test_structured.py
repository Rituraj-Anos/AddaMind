from pydantic import BaseModel

from backend.core.structured import inline_schema


class Event(BaseModel):
    title: str
    ids: list[int]


class Month(BaseModel):
    events: list[Event]
    best: Event | None = None


def test_field_named_title_survives_and_metadata_titles_go():
    s = inline_schema(Month)
    item = s["properties"]["events"]["items"]
    assert set(item["properties"]) == {"title", "ids"} and item["required"] == ["title", "ids"]
    assert "title" not in s and "title" not in item and "title" not in item["properties"]["title"]
    assert "$ref" not in str(s) and "$defs" not in s
