# 📸 Thursday PhotoStory

## ⬇️ Get it

| | How | |
|---|---|---|
| 📱 **Phone app** | Open **[hardikashah-eng.github.io/PhotosStory](https://hardikashah-eng.github.io/PhotosStory/)** → Share → **Add to Home Screen** | No account needed. Optional API key, or use the free built-in writer |
| 🧩 **Claude skill** | Download **[thursday-photostory-skill.zip](https://github.com/hardikashah-eng/PhotosStory/releases/latest/download/thursday-photostory-skill.zip)** → Claude → **Customize → Skills → + → Create skill → Upload a skill** → say *"make this week's PhotoStory"* | Needs a Claude plan with skills and code execution |
| 🌐 **Self-host the app** | **[photostory-webapp.zip](https://github.com/hardikashah-eng/PhotosStory/releases/latest/download/photostory-webapp.zip)**: unzip and put the folder on any static host | |
| 🐍 **Weekly automation** | Fork this repo and follow *Setup* below (GitHub Actions every Thursday) | |

Releases are built automatically when a version tag is pushed (`git tag v0.2.0 && git push origin v0.2.0`). See `.github/workflows/release.yml`. To build the same files locally, run `python scripts/package_release.py`; they land in `dist/`.

Every Thursday morning an agent picks **10 random family photos** (from OneDrive or a folder), and Claude turns them into a little show:

- 😂 **Funny, family-friendly captions** for each photo
- 📖 **An imaginary story** that weaves all 10 photos into one adventure
- 🧠 **A family quiz** (interactive in the browser, answer key in the email)
- 🎤 **An original silly sing-along song** with a shout-along chorus
- ❤️ **A family collage**: all the week's photos as a dated scrapbook timeline, with a famous quote and one heartfelt line
- 🔊 **Talking photos**: each photo "says" a funny line from the point of view of someone or something in it, spoken in the video and readable aloud on the page

Each week the episode is published as its own **web page with an unlisted link**. You get one short email with **📖 Open** and **💬 Share on WhatsApp** buttons. On your phone, tap Share and pick your family groups. The link shows a preview with the cover photo and title.
(If publishing is off or fails, the full episode is emailed instead, with photos inline and an interactive `photostory.html` attached.)

```
OneDrive / folder ──► pick 10 (varied months, no repeats for 6 months)
                  ──► Claude (vision) → captions · story · quiz · song   [validated, auto-fixed]
                  ──► render (interactive page + email)  ──► email to family
                  ──► remember what was used (hashed ids only)
```

## 📲 Use it on a phone, no install

There are three ways to use PhotoStory without touching this repo:

| | How people use it | Writes the story | Talking-photo video | Needs |
|---|---|---|---|---|
| **Inside Claude** | Open the shared PhotoStory page in the Claude app | Claude, on *their* Claude plan | Silent video; 🔊 buttons read lines aloud | A Claude account |
| **Standalone web app** | Open the GitHub Pages link → *Add to Home Screen* | Claude with their API key, **or** the free built-in writer | ✅ Spoken, made on the phone | Nothing (API key optional) |
| **Claude skill** | Say "make this week's PhotoStory" or schedule it for Thursdays | Claude in chat | ✅ Spoken (Piper) | A Claude account |

**The web app (`webapp/index.html`) is one self-contained page.** Everything happens on the phone:
- **Photos:** pick 3–40 from the gallery. It picks 10 from different years and reads the dates from the photos.
- **Writing:** Claude writes the story, or the built-in template writer does, which is free, works offline, and uses your dates and one-word tags.
- **Cards and collage:** drawn on canvas.
- **Voice:** [Piper](https://github.com/rhasspy/piper) neural TTS runs in the browser through onnxruntime-web. The 75 MB voice downloads once and is then cached.
- **Video:** encoded with WebCodecs and mp4-muxer.
- **Sharing:** the share sheet sends cards and video straight to WhatsApp.
- **Privacy:** photos never leave the phone, except to Claude when Claude is the writer.

Deploy it for free: the `Deploy web app` workflow publishes `webapp/` to GitHub Pages on every push to `main`. One-time setup: **Settings → Pages → Source: GitHub Actions**. To try it locally: `python -m http.server -d webapp`. After editing `photostory/data/quotes.yaml`, run `python webapp/sync_quotes.py`.

Browser support:
- **Video:** needs WebCodecs (Chrome/Edge on Android and desktop, Safari 16.4+).
- **Audio track:** AAC where the browser can encode it, otherwise Opus.
- **Voice:** older phones can untick talking photos and use the 🔊 buttons, which use the phone's own voice.

**For the Claude skill**, Claude writes the episode JSON in chat, then renders it with:

```bash
pip install "photostory[share,voice] @ git+https://github.com/hardikashah-eng/PhotosStory"
python -m playwright install chromium
photostory schema            # the episode JSON shape
photostory quotes            # the curated collage quotes
photostory render --episode episode.json --photos 01.jpg 02.jpg … --out out/
```

## 📱 WhatsApp pack

An `.html` file arrives in WhatsApp as a "document", so every episode also comes as formats that play right in the chat. They're attached to the weekly email and saved under `out/<date>/whatsapp/`:

| File | How to use it in WhatsApp |
|---|---|
| `photostory.mp4` | ~70 s slideshow (slow zoom, captions, dip-to-black cuts) ending on the collage, ~5 MB. Send as a video. |
| `cards/*.jpg` | 1080×1350 story cards: title, one per chapter, ending + quiz teaser, song, and the family collage. Select them all and send as one album. |
| `cards/NN_collage.jpg` | **Family collage**: every photo of the week on one scrapbook page, oldest first, each with a year sticker. Titled "17 Years of Us" (built from the photo dates), with one heartfelt line from Claude. Also the video's final scene, and a good group photo or Status. |
| `polls.txt` | The quiz as WhatsApp polls (📎 → Poll), plus an answer-reveal message for the next day. |

Rendering uses headless Chromium (for emoji and typography) and ffmpeg:

```bash
pip install ".[share]" && python -m playwright install chromium   # plus ffmpeg on PATH
```

The GitHub workflow installs both. If either is missing, the episode still goes out without the pack. To use an existing Chrome instead, set `PHOTOSTORY_CHROME=/path/to/chrome`. Configure it under `whatsapp:` in `config.yaml`.

## 🔊 Talking photos & 📜 collage quotes

**Talking photos.** Claude writes one short first-person line per photo, spoken by someone or something in it: a person described by what they're doing, a pet, an object, or the place itself. For example, *the smiling pumpkin: "Fasten your seatbelts, this pumpkin is cleared for take-off!"*

- **Video:** each line is spoken with [Piper](https://github.com/rhasspy/piper), an offline neural TTS, and shown as a speech bubble, so it also works muted. Each speaker always gets the same voice from a 904-voice model. The chapter stretches to fit the line.
- **Interactive page:** a 🔊 button per photo reads the line with the phone's own voices (Web Speech API).
- **Voices are generic and synthetic.** The project never clones or imitates real family members' voices, and never uses real names.
- **Install:** `pip install ".[voice]"`. The voice model (~135 MB) downloads once to `~/.cache/photostory/voices` (cached in Actions). If anything is missing, the video simply has no speech.

**Collage quotes.** The collage shows one famous quote. Claude picks it from a curated list in `photostory/data/quotes.yaml` (Emerson, Thoreau, Muir, Shakespeare, Santayana, Jefferson…) and never writes its own, because AI-generated "famous quotes" are often misattributed. Every entry has a checkable source. Add your own family favourites there.

## Privacy by design

This repo can be public, but **your photos and family details never go into it**:

- Photos are downloaded at run time, resized, and **EXIF/GPS is stripped** before anything is sent to Claude or emailed.
- `out/` (rendered episodes) is git-ignored. Workflow artifacts are only uploaded if the repo is **private**.
- `state/history.json` holds truncated SHA-256 hashes of photo ids — no names, no ids.
- Recipients, family name and character list can live in **secrets** (`EMAIL_TO`, `PHOTOSTORY_FAMILY_NAME`, `PHOTOSTORY_CHARACTERS`) instead of `config.yaml`.
- OneDrive access is **read-only** (`Files.Read`).
- The prompt forbids jokes about bodies, looks, age, ethnicity etc., guessing names, or mentioning locations.

> Still recommended: make the repo private (Settings → General → Danger zone → Change visibility).

## Setup (≈15 minutes, once)

### 1. Try it locally first (no accounts needed)

```bash
pip install -e ".[dev,heic]"
photostory run --source-path ~/Pictures --fake-llm --dry-run   # canned text, real photos
photostory run --no-email                                        # publish and just print the link
open out/*/photostory.html
pytest -q
```

Add `ANTHROPIC_API_KEY=...` and drop `--fake-llm` to see a real episode.

### 2. Connect OneDrive

1. Go to **portal.azure.com → App registrations → New registration**
   - Name: `PhotoStory`
   - Supported accounts: **Personal Microsoft accounts only** (or "any org + personal" for work OneDrive; then set `source.tenant: common`)
   - Redirect URI: leave empty
2. In the app: **Authentication → Advanced settings → Allow public client flows = Yes** → Save.
3. **API permissions → Add → Microsoft Graph → Delegated → `Files.Read`** (and `offline_access`).
4. Copy the **Application (client) ID**, then sign in once:

```bash
photostory onedrive-login --client-id <CLIENT_ID>
# open microsoft.com/devicelogin, enter the code, approve
gh secret set MS_CLIENT_ID --body <CLIENT_ID>
gh secret set MS_REFRESH_TOKEN < onedrive.token && rm onedrive.token
```

Pick the folder in `config.yaml` → `source.path`:
`special:cameraroll` (phone uploads), `special:photos`, or a path like `Pictures/Family`. Check what it sees with `photostory list`.

**Keeping the token alive:** Microsoft rotates refresh tokens. Create a fine-grained PAT (this repo only, *Secrets: Read and write*) and save it as `GH_SECRETS_PAT` — the workflow then stores the newest token after each run. Without it, re-run `onedrive-login` roughly every 90 days.

### 3. Weekly page link (Cloudflare R2, free tier)

1. Cloudflare dashboard → **R2** → **Create bucket** → name it `photostory`.
2. Bucket → **Settings → Public access → R2.dev subdomain → Allow**. Copy the `https://pub-….r2.dev` URL.
   *(Skip this step if you want links that **expire after 7 days** and a bucket with nothing public at all.)*
3. R2 → **Manage API tokens → Create API token**: *Object Read & Write*, limited to this bucket. Copy the Access Key ID, the Secret, and the S3 endpoint (`https://<account-id>.r2.cloudflarestorage.com`).
4. Optional: bucket → **Settings → Object lifecycle rules** → delete objects after e.g. 60 days.

```bash
gh secret set S3_BUCKET --body photostory
gh secret set S3_ENDPOINT_URL --body https://<account-id>.r2.cloudflarestorage.com
gh secret set S3_ACCESS_KEY_ID --body <key id>
gh secret set S3_SECRET_ACCESS_KEY --body <secret>
gh secret set PUBLISH_BASE_URL --body https://pub-xxxx.r2.dev   # omit for 7-day expiring links
```

How private is it? Each episode is stored under a random 128-bit folder name, so it can't be guessed or listed, and the page tells search engines not to index it. As with a Google Photos "anyone with the link" share, anyone you forward the link to can open it. The link is only ever sent by email. It is never written to the Actions log, because logs of public repos are public. Any S3-compatible store also works (AWS S3, Backblaze B2); set `publish.region` to match.

### 4. Email (Gmail example)

Turn on 2-Step Verification, create an **App password** (myaccount.google.com/apppasswords), then:

```bash
gh secret set SMTP_USERNAME --body you@gmail.com
gh secret set SMTP_PASSWORD --body "<16-char app password>"
gh secret set EMAIL_TO --body "you@gmail.com,partner@example.com"
```

### 5. Claude + personalisation

```bash
gh secret set ANTHROPIC_API_KEY --body sk-ant-...
gh secret set PHOTOSTORY_FAMILY_NAME --body "The Shah Family"
gh secret set PHOTOSTORY_CHARACTERS --body "Dad, the snack detective; Mom, captain of everything; Biscuit the dog"
```

Or put an entire private config in the `PHOTOSTORY_CONFIG_YAML` secret.

### 6. Run it

**Actions → Thursday PhotoStory → Run workflow** (tick *dry run* first). After that it runs on its own every **Thursday at 8:17am Pacific** (9:17am during daylight time — GitHub cron is UTC). The weekly history commit also keeps GitHub from pausing the schedule for inactivity.

## Secrets reference

| Secret | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude API |
| `MS_CLIENT_ID`, `MS_REFRESH_TOKEN` | OneDrive | Read-only photo access |
| `GH_SECRETS_PAT` | recommended | Saves rotated OneDrive token |
| `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | link mode | Hosts the weekly page |
| `PUBLISH_BASE_URL` | optional | Permanent unlisted links (otherwise 7-day signed links) |
| `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_TO` | email | Delivery (set `EMAIL_TO` to just you if you'll do the sharing) |
| `PHOTOSTORY_FAMILY_NAME`, `PHOTOSTORY_CHARACTERS`, `PHOTOSTORY_SOURCE_PATH` | optional | Keep personal details out of the repo |
| `PHOTOSTORY_CONFIG_YAML` | optional | Whole config as a secret |

## Config highlights (`config.yaml`)

- `story.photo_count` (10), `story.quiz_questions` (5), `story.language`, `story.audience`
- `story.themes` — rotating premises (secret mission, time-travel mix-up, dramatic owl documentary…)
- `story.avoid_repeat_days` — don't reuse a photo for this long (180)
- `source.exclude_patterns` — skip screenshots etc.; `source.min_side_px` skips tiny images
- `llm.model` — defaults to `claude-sonnet-5-5`

## How it works

| Module | Job |
|---|---|
| `sources/onedrive.py` | Graph API: token refresh + rotation, recursive paged folder walk, server-side JPEG thumbnails (handles HEIC), 429 back-off |
| `sources/local.py` | Folder source with EXIF dates |
| `selector.py` | Spreads picks across months, avoids recent repeats, tops up with least-recently-used |
| `generator.py` | One vision call with a forced `publish_episode` tool (schema = Pydantic model); validates coverage/quiz, sends problems back for a fix-up turn; shuffles quiz answers |
| `render.py` + `templates/` | Storybook-style interactive page and an email-safe version with CID images |
| `publish.py` | Uploads page + cover to S3/R2 under a random folder; public-unlisted or signed links |
| `deliver.py` | Pluggable channels: link email with WhatsApp share button, or full email |

## Roadmap ideas

- 📱 WhatsApp delivery channel (official Groups API is limited to bot-created groups of ≤8; posting into existing groups needs an unofficial bridge)
- 🔊 Read-aloud audio of the story / sung version of the song
- 🗳️ Family votes on next week's theme by replying to the email
