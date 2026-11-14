---
name: thursday-photostory
description: Make a family PhotoStory from ~10 photos (OneDrive or uploads) with funny captions, story, quiz, song, talking photos and a dated collage, rendered as a WhatsApp pack.
---

# Thursday PhotoStory

Turn ~10 family photos into a weekly "show": captions, an imaginary story, a 5-question quiz, an original sing-along song, one talking-photo line per photo, and a collage with a curated quote. Deliver it as a WhatsApp pack (a video where the photos speak, swipeable story cards, quiz polls) plus an interactive page.

You write the episode yourself in chat. The bundled `photostory` engine renders it. Project: https://github.com/hardikashah-eng/PhotosStory

## 0. Install the engine (once per session)

```bash
pip install --break-system-packages "$(ls assets/photostory-*.whl | head -1)[share,voice]" \
  || pip install --break-system-packages "photostory[share,voice] @ git+https://github.com/hardikashah-eng/PhotosStory"
python -m playwright install chromium || true   # or set PHOTOSTORY_CHROME to an installed Chrome
```

Run these from this skill's folder. `assets/` holds the engine wheel shipped with this skill.

## 1. Get the photos

Use the first source that works. Tell the person in one line which you used.

- **Microsoft 365 connector (OneDrive):**
  - Find the phone-upload folder with `sharepoint_folder_search` ("camera roll", "SkyDrive camera roll", "Pictures"). Find older albums in a `Photos/<year>/<event>` tree by reading `drive:///users/me` with `read_resource`.
  - A folder listing shows only the first 1,000 items. To reach other years in a big camera roll, search for date-stamped filenames, e.g. `sharepoint_search` with query `20191225`.
  - `read_resource` on a file URI returns the image and saves it under `/tmp/claude-tool-results/...`. Copy those files into a working folder as `01.jpg`, `02.jpg`, ….
  - Images over 5 MB can't be read. Pick another photo.
- **Photos the person attached**, or a connected folder on their computer.
- If there's no source, ask them to attach 10 photos.

## 2. Pick ~10 good photos

- **Spread them out:** different years and events. A mix of older albums and recent phone photos works well. If the person names a folder for older photos, use it.
- **Skip** screenshots, receipts and documents, videos, near-duplicates and very blurry shots.
- **Also skip anything private or awkward to post in a family group:** bedroom, bathroom or swimwear shots, people crying, medical settings. If the person asked you to skip something before, honor it.
- **Look at every chosen photo** before writing about it.
- **Number the photos in date order (oldest = 1),** and note each one's date from the filename, EXIF, or the album year.

## 3. Write `episode.json`

Run `photostory schema` for the exact shape and `photostory quotes` for the quote list. Then write:

- `title`, `tagline`, `theme` (an imaginary premise tying all the photos together, e.g. "a time-travel mix-up")
- `captions`: exactly one per photo (`photo`, `caption` ≤ ~20 words, `emoji`)
- `story_intro`, `story` (one beat per photo: `photo`, `heading`, `text` of 2–4 sentences), `story_ending`
- `quiz`: exactly 5, answerable from the photos or the story (`options` 3–4, `answer` = 0-based index, `explanation`)
- `song`: `title`, `style`, `tune_hint`, 2–4 `verses` (4 lines each, `\n`-separated), `chorus`
- `voices`: one per photo (`photo`, `speaker`, `line` ≤ 16 words, first person)
- `collage_quote_id`: an id from `photostory quotes`. **Never invent or alter quotes.**
- `collage_message`: one sincere sentence about the family, not a joke.
- `next_week_teaser`

House rules, which matter more than being funny:
- Laugh WITH people, never AT them. No jokes about bodies, weight, looks, age, hair, skin, disability, ethnicity or religion.
- No real names unless the person gave them. No guessing who is who. No locations or schools.
- Give talking-photo voices to objects, pets and places by preference ("the smiling pumpkin", "the striped fish"). Describe people by role, never by name, and keep every line kind.
- Song lyrics must be 100% original. For the tune, use only an original rhythm or a public-domain melody (e.g. "Row, Row, Row Your Boat").

## 4. Render

```bash
photostory render --episode episode.json --photos 01.jpg 02.jpg ... \
  --dates 2009-10-18,2009-09-05,... --out out/
```

- If it reports episode problems, fix the JSON and run it again.
- The first run downloads a ~135 MB voice once. If that's blocked, add `--no-voice` and tell the person the video is silent.
- Output:
  - `out/photostory.html` (interactive page)
  - `out/whatsapp/photostory.mp4` (video where the photos speak)
  - `out/whatsapp/cards/*.jpg` (album, collage last)
  - `out/whatsapp/polls.txt`

## 5. Check, then deliver

- Look at the collage card and one chapter card. Grab one video frame with ffmpeg and look at it too.
- Send the video, the cards (in order) and `polls.txt`. Offer the interactive page as a file or a shareable page.
- In one line, explain how to share: save the cards, then in WhatsApp tap + → Photos, pick them in order and send. Then send the video, then paste the polls.
- Treat it as a dry run unless the person asked to send it somewhere. Never post to a group or email anyone yourself.

## 6. Every Thursday (optional)

If they want it weekly, offer a scheduled task for Thursday morning in their time zone whose prompt says to use this skill. Each run should avoid photos used in recent weeks (keep a short list of used filenames in memory or a notes file) and deliver the pack to the person for review.

## Phone alternative

For people who'd rather tap than chat, the project's phone web app (`webapp/index.html`) does the same on a phone. It runs inside Claude as a shared page, or standalone through GitHub Pages with Add to Home Screen.
