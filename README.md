# 📸 Thursday PhotoStory

Every Thursday morning an agent picks **10 random family photos** (from OneDrive or a folder), and Claude turns them into a little show:

- 😂 **Funny, family-friendly captions** for each photo
- 📖 **An imaginary story** that weaves all 10 photos into one adventure
- 🧠 **A family quiz** (interactive in the browser, answer key in the email)
- 🎤 **An original silly sing-along song** with a shout-along chorus

It arrives as an email with the photos inline, plus an attached `photostory.html` you can open on any phone or TV to play the quiz.

```
OneDrive / folder ──► pick 10 (varied months, no repeats for 6 months)
                  ──► Claude (vision) → captions · story · quiz · song   [validated, auto-fixed]
                  ──► render (interactive page + email)  ──► email to family
                  ──► remember what was used (hashed ids only)
```

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

### 3. Email (Gmail example)

Turn on 2-Step Verification, create an **App password** (myaccount.google.com/apppasswords), then:

```bash
gh secret set SMTP_USERNAME --body you@gmail.com
gh secret set SMTP_PASSWORD --body "<16-char app password>"
gh secret set EMAIL_TO --body "you@gmail.com,partner@example.com"
```

### 4. Claude + personalisation

```bash
gh secret set ANTHROPIC_API_KEY --body sk-ant-...
gh secret set PHOTOSTORY_FAMILY_NAME --body "The Shah Family"
gh secret set PHOTOSTORY_CHARACTERS --body "Dad, the snack detective; Mom, captain of everything; Biscuit the dog"
```

Or put an entire private config in the `PHOTOSTORY_CONFIG_YAML` secret.

### 5. Run it

**Actions → Thursday PhotoStory → Run workflow** (tick *dry run* first). After that it runs on its own every **Thursday at 8:17am Pacific** (9:17am during daylight time — GitHub cron is UTC). The weekly history commit also keeps GitHub from pausing the schedule for inactivity.

## Secrets reference

| Secret | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude API |
| `MS_CLIENT_ID`, `MS_REFRESH_TOKEN` | OneDrive | Read-only photo access |
| `GH_SECRETS_PAT` | recommended | Saves rotated OneDrive token |
| `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_TO` | email | Delivery |
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
| `deliver.py` | Pluggable channels (email today) |

## Roadmap ideas

- 📱 WhatsApp delivery channel (official Groups API is limited to bot-created groups of ≤8; posting into existing groups needs an unofficial bridge)
- 🔊 Read-aloud audio of the story / sung version of the song
- 🗳️ Family votes on next week's theme by replying to the email
