import json
import random
from types import SimpleNamespace

import pytest

from photostory.config import Config
from photostory.generator import TOOL_NAME, episode_tool, fake_episode, generate_episode, shuffle_quiz
from photostory.models import check_episode

from .conftest import make_photos


class FakeClient:
    """Mimics anthropic.Anthropic().messages.create, returning queued tool inputs."""

    def __init__(self, inputs):
        self.inputs = list(inputs)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[SimpleNamespace(type="tool_use", id=f"tu{len(self.calls)}", name=TOOL_NAME, input=self.inputs.pop(0))],
        )


def test_tool_schema_is_self_contained():
    s = json.dumps(episode_tool()["input_schema"])
    assert "$ref" not in s and "$defs" not in s


def test_fake_episode_is_valid():
    cfg = Config()
    ep = fake_episode(make_photos(10), cfg)
    assert check_episode(ep, 10, cfg.story.quiz_questions) == []


def test_check_episode_catches_problems():
    cfg = Config()
    ep = fake_episode(make_photos(10), cfg)
    ep.captions = ep.captions[:-1]
    ep.quiz[0].answer = 9
    problems = check_episode(ep, 10, cfg.story.quiz_questions)
    assert any("captions" in p for p in problems) and any("out of range" in p for p in problems)


def test_generate_sends_images_and_forces_tool():
    cfg, photos = Config(), make_photos(4)
    good = fake_episode(photos, cfg).model_dump()
    client = FakeClient([good])
    ep = generate_episode(photos, cfg, client, random.Random(0))
    assert ep.title == good["title"]
    call = client.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    images = [b for b in call["messages"][0]["content"] if b["type"] == "image"]
    assert len(images) == 4 and images[0]["source"]["media_type"] == "image/jpeg"


def test_generate_retries_with_feedback():
    cfg, photos = Config(), make_photos(4)
    good = fake_episode(photos, cfg).model_dump()
    bad = json.loads(json.dumps(good))
    bad["captions"] = bad["captions"][:2]  # missing captions
    client = FakeClient([bad, good])
    generate_episode(photos, cfg, client, random.Random(0))
    assert len(client.calls) == 2
    feedback = client.calls[1]["messages"][-1]["content"][0]
    assert feedback["type"] == "tool_result" and feedback["is_error"] and "captions" in feedback["content"]


def test_generate_gives_up():
    cfg, photos = Config(), make_photos(3)
    client = FakeClient([{"title": "nope"}] * 3)
    with pytest.raises(RuntimeError):
        generate_episode(photos, cfg, client, random.Random(0), max_attempts=3)


def test_shuffle_quiz_keeps_correct_answer():
    cfg = Config()
    ep = fake_episode(make_photos(5), cfg)
    before = [q.options[q.answer] for q in ep.quiz]
    shuffle_quiz(ep, random.Random(7))
    assert [q.options[q.answer] for q in ep.quiz] == before
