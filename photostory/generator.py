"""Ask Claude (with vision) to turn the photos into an Episode.

Uses a forced tool call whose input schema is the Pydantic Episode schema, then
validates the result and, if needed, sends the problems back for one fix-up turn.
"""

from __future__ import annotations

import base64
import copy
import logging
import random
from typing import Any

from pydantic import ValidationError

from .config import Config
from .models import Caption, Episode, QuizQuestion, Song, StoryBeat, check_episode
from .sources.base import Photo

log = logging.getLogger(__name__)
TOOL_NAME = "publish_episode"

SYSTEM_PROMPT = """You are the head writer of "Thursday PhotoStory", a weekly family show made from a family's own photos.

Each week you receive a random set of photos and turn them into ONE imaginary, funny adventure that the whole family can enjoy together on a Thursday evening.

House rules — these matter more than being funny:
- Family-friendly, warm and inclusive. Laugh WITH people, never AT them.
- Never joke about anyone's body, weight, looks, age, skin, hair, clothing size, disability, ethnicity or religion.
- Never guess real names, relationships, or ages of people in the photos. Refer to people by what they're doing ("the hat-wearing hero", "the snack guardian") unless a character list is provided — and even then only use a name when a hint makes the match obvious.
- Don't mention or infer locations, addresses, schools, or anything identifying.
- If a photo is unclear, boring (a receipt, a blurry wall), or sensitive, give it a gentle, imaginative role in the story (a "mysterious map", a "portal") instead of describing it literally.
- Pets, food, weather and objects are excellent comedy material.
- Song lyrics must be 100% original. For the tune, describe an original rhythm or use a traditional public-domain melody only.
- Quiz questions should be answerable by looking at the photos or reading the story, with a mix of easy questions for kids and trickier ones for adults.

Deliver everything by calling the publish_episode tool exactly once."""


def _inline_refs(schema: dict) -> dict:
    """Resolve $ref/$defs so the tool schema is self-contained."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def episode_tool() -> dict:
    return {
        "name": TOOL_NAME,
        "description": "Publish this week's PhotoStory episode.",
        "input_schema": _inline_refs(Episode.model_json_schema()),
    }


def build_user_content(photos: list[Photo], cfg: Config, theme: str | None) -> list[dict]:
    s = cfg.story
    content: list[dict] = []
    for i, p in enumerate(photos, 1):
        when = p.ref.taken_at.strftime("%B %Y") if p.ref.taken_at else "unknown date"
        content.append({"type": "text", "text": f"Photo {i} (taken {when}):"})
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(p.jpeg).decode()},
            }
        )
    cast = "\n".join(f"- {c}" for c in s.characters) or "(none provided — don't invent real names)"
    content.append(
        {
            "type": "text",
            "text": (
                f"This week's family: {s.family_name}\n"
                f"Audience: {s.audience}\n"
                f"Write in: {s.language}\n"
                f"Optional characters you may use:\n{cast}\n"
                f"Suggested premise: {theme or 'your choice — surprise us'}\n\n"
                f"Create the episode for these {len(photos)} photos: one caption per photo, one story beat per "
                f"photo, exactly {s.quiz_questions} quiz questions, and an original silly song with a chorus "
                f"everyone can shout along to."
            ),
        }
    )
    return content


def generate_episode(photos: list[Photo], cfg: Config, client: Any, rng: random.Random, max_attempts: int = 3) -> Episode:
    theme = rng.choice(cfg.story.themes) if cfg.story.themes else None
    messages: list[dict] = [{"role": "user", "content": build_user_content(photos, cfg, theme)}]
    kwargs: dict[str, Any] = dict(
        model=cfg.llm.model,
        max_tokens=cfg.llm.max_tokens,
        system=SYSTEM_PROMPT,
        tools=[episode_tool()],
        tool_choice={"type": "tool", "name": TOOL_NAME},
    )
    if cfg.llm.temperature is not None:
        kwargs["temperature"] = cfg.llm.temperature

    problems: list[str] = []
    for attempt in range(1, max_attempts + 1):
        resp = client.messages.create(messages=messages, **kwargs)
        tool_use = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
        if tool_use is None:
            raise RuntimeError(f"Model did not call {TOOL_NAME} (stop_reason={resp.stop_reason}).")
        if resp.stop_reason == "max_tokens":
            problems = ["Output was cut off — keep each field shorter."]
            ep = None
        else:
            try:
                ep = Episode.model_validate(tool_use.input)
                problems = check_episode(ep, len(photos), cfg.story.quiz_questions)
            except ValidationError as e:
                ep, problems = None, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()][:15]
        if ep is not None and not problems:
            return ep
        log.warning("Attempt %d produced an invalid episode: %s", attempt, problems)
        messages += [
            {"role": "assistant", "content": resp.content},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "is_error": True,
                        "content": "Please fix these problems and call publish_episode again:\n- " + "\n- ".join(problems),
                    }
                ],
            },
        ]
    raise RuntimeError(f"Could not get a valid episode after {max_attempts} attempts: {problems}")


def shuffle_quiz(ep: Episode, rng: random.Random) -> Episode:
    """Shuffle answer options so the right answer isn't always 'A'."""
    for q in ep.quiz:
        correct = q.options[q.answer]
        rng.shuffle(q.options)
        q.answer = q.options.index(correct)
    return ep


def fake_episode(photos: list[Photo], cfg: Config) -> Episode:
    """Deterministic placeholder episode for dry runs and tests (no API call)."""
    n, q = len(photos), cfg.story.quiz_questions
    return Episode(
        title="The Case of the Vanishing Cookie",
        tagline="Ten photos. One crumb trail. Zero suspects (allegedly).",
        theme="a mystery: who ate the last cookie?",
        captions=[Caption(photo=i, caption=f"Exhibit #{i}: suspiciously innocent.", emoji="🍪🔍") for i in range(1, n + 1)],
        story_intro="It was a quiet Thursday until someone noticed the cookie jar was empty. Detectives were summoned.",
        story=[
            StoryBeat(photo=i, heading=f"Clue #{i}", text=f"Photo {i} revealed a crumb. Or was it glitter? The plot thickened.")
            for i in range(1, n + 1)
        ],
        story_ending="In the end, the culprit was the dog. It is always the dog. Everyone shared a fresh batch.",
        quiz=[
            QuizQuestion(
                question=f"Which clue number is #{i}?",
                options=[str(i), str(i + 1), str(i + 2)],
                answer=0,
                explanation="Because clues are numbered in order!",
            )
            for i in range(1, q + 1)
        ],
        song=Song(
            title="The Crumb Trail Blues",
            style="slow blues",
            tune_hint="Stomp-stomp-clap, nice and slow.",
            verses=[
                "Woke up this morning\nThe jar was bare\nJust a single crumb\nOn the kitchen stair",
                "Asked the cat\nAsked the hen\nThe dog just smiled\nAnd did it again",
            ],
            chorus="Oh the crumb trail blues\nGot cookie on my shoes",
        ),
        next_week_teaser="Next Thursday: the great sock disappearance.",
    )
