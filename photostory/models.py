"""The structured episode the agent produces. Field descriptions double as model instructions."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Caption(BaseModel):
    photo: int = Field(description="1-based photo number this caption belongs to.")
    caption: str = Field(description="One funny, kind, family-friendly caption (max ~20 words).")
    emoji: str = Field(description="One or two emoji that fit the caption.")


class StoryBeat(BaseModel):
    photo: int = Field(description="1-based photo number this part of the story is built around.")
    heading: str = Field(description="A short, playful chapter heading.")
    text: str = Field(description="2-4 sentences of the imaginary story that bring this photo to life.")


class PhotoVoice(BaseModel):
    photo: int = Field(description="1-based photo number.")
    speaker: str = Field(
        description=(
            "Who or what is talking, described by role or look, never a real name: "
            "'the smiling pumpkin', 'the explorer in the bubble helmet', 'the snowy mountain', 'the dog'."
        )
    )
    line: str = Field(
        description=(
            "What the photo 'says' out loud, first person, from that speaker's point of view: "
            "playful, kind, family-friendly, max 16 words. It will be read aloud by a synthetic voice."
        )
    )


class QuizQuestion(BaseModel):
    question: str = Field(description="A fun question about the photos or the story. Answerable by looking/reading.")
    options: list[str] = Field(min_length=3, max_length=4, description="3-4 answer choices; one correct.")
    answer: int = Field(description="0-based index into options of the correct answer.")
    explanation: str = Field(description="One cheerful sentence revealing why that's the answer.")


class Song(BaseModel):
    title: str
    style: str = Field(description="Musical style, e.g. 'sea shanty', 'rap', 'lullaby', 'country ballad'.")
    tune_hint: str = Field(
        description=(
            "How to sing it. Either describe an original rhythm, or name a traditional public-domain "
            "tune (e.g. 'Twinkle Twinkle Little Star', 'Old MacDonald'). Never a modern copyrighted song."
        )
    )
    verses: list[str] = Field(min_length=2, max_length=4, description="Each verse 4 lines separated by \\n.")
    chorus: str = Field(description="A catchy 2-4 line chorus separated by \\n.")


class Episode(BaseModel):
    title: str = Field(description="The episode's title, like a storybook or cartoon episode.")
    tagline: str = Field(description="One-line teaser for the episode.")
    theme: str = Field(description="The imaginary premise tying all the photos together.")
    captions: list[Caption] = Field(description="Exactly one caption per photo.")
    story_intro: str = Field(description="2-3 sentence opening that sets up the adventure.")
    story: list[StoryBeat] = Field(
        description="One beat per photo, in story order (you may reorder photos to make the plot flow)."
    )
    story_ending: str = Field(description="2-3 sentence happy, funny ending.")
    quiz: list[QuizQuestion]
    song: Song
    voices: list[PhotoVoice] = Field(description="Talking photos: exactly one voice line per photo.")
    collage_quote_id: int = Field(
        description="id of the quote from the provided quote list that best fits the collage of all these photos."
    )
    collage_message: str = Field(
        description=(
            "One warm, sincere sentence (not a joke, max ~30 words) shown on a collage of ALL this week's photos: "
            "what these moments together say about the family, e.g. growing up, being together, adventures shared. "
            "No names, places or guesses about who is who."
        )
    )
    next_week_teaser: str = Field(description="One playful line teasing next Thursday's episode.")


MAX_VOICE_WORDS = 20


def check_episode(ep: Episode, n_photos: int, n_questions: int) -> list[str]:
    """Cross-field checks that JSON schema can't express. Returns human-readable problems."""
    problems: list[str] = []
    expected = set(range(1, n_photos + 1))

    cap_nums = [c.photo for c in ep.captions]
    if sorted(cap_nums) != sorted(expected):
        problems.append(f"captions must cover photos 1..{n_photos} exactly once; got {sorted(cap_nums)}")

    beat_nums = [b.photo for b in ep.story]
    if sorted(beat_nums) != sorted(expected):
        problems.append(f"story must have one beat per photo 1..{n_photos}; got {sorted(beat_nums)}")

    voice_nums = [v.photo for v in ep.voices]
    if sorted(voice_nums) != sorted(expected):
        problems.append(f"voices must have one line per photo 1..{n_photos}; got {sorted(voice_nums)}")
    for v in ep.voices:
        if len(v.line.split()) > MAX_VOICE_WORDS:
            problems.append(f"voice line for photo {v.photo} is too long (max {MAX_VOICE_WORDS} words)")

    from .quotes import load_quotes  # local import: keeps models importable without package data

    if ep.collage_quote_id not in load_quotes():
        problems.append(f"collage_quote_id {ep.collage_quote_id} is not in the quote list")

    if len(ep.quiz) != n_questions:
        problems.append(f"quiz must have exactly {n_questions} questions; got {len(ep.quiz)}")
    for i, q in enumerate(ep.quiz, 1):
        if not 0 <= q.answer < len(q.options):
            problems.append(f"quiz question {i}: answer index {q.answer} is out of range")
        if len(set(o.strip().lower() for o in q.options)) != len(q.options):
            problems.append(f"quiz question {i}: options must be distinct")
    return problems
