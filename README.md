# inkd

Two-way sync between a **reMarkable 2**, **Dropbox / Google Drive** and **Obsidian**, without a
reMarkable Connect subscription.

```
reMarkable 2 ──sync──► rmfakecloud (self-hosted, replaces the reMarkable cloud)
                              │
                         inkd (this project)
                     ┌────────┴─────────┐
              rclone ▼                  ▼ Markdown + page images
     Dropbox / Google Drive          Obsidian vault
```

| Direction | What happens |
| --- | --- |
| Tablet → cloud | Every notebook is rendered to PDF and copied to `storage.remote`, mirroring the tablet's folders. Imported PDFs/EPUBs are copied as they are, plus `… (ink).pdf` with your handwriting. |
| Tablet → Obsidian | Every written notebook becomes a note in `reMarkable/…`: one section per page with the page image and its transcription (handwriting recognised by Claude, typed text taken as is). |
| Cloud → tablet | PDF and EPUB files dropped into `storage.inbox` are sent to the tablet's `/Inbox` and moved to `inbox/sent/`. |
| Obsidian → tablet | Notes with `remarkable: true` in the frontmatter are laid out as a PDF for the tablet's screen (wide right margin) and sent to `/Obsidian/…`. Handwriting you add to that PDF on the tablet comes back into **the same note**, under "Handwritten on the reMarkable". |

### What "two-way" means here

Handwriting and typed text cannot be merged line by line, so each side owns its part:

- inkd only writes between `<!-- inkd:begin … -->` and `<!-- inkd:end -->` and its own `inkd_*`
  frontmatter keys. Anything you write outside that block, in any note, is never touched.
- Edit a published note in Obsidian and it is sent to the tablet again. If the tablet copy has
  handwriting on it, the old copy stays and the new one is added next to it with a date, so no ink
  is ever overwritten.
- Pages are only transcribed again when they change (inkd keeps a hash of every page).
- Nothing is deleted anywhere: a notebook deleted on the tablet keeps its note and PDF.

## Setup

You need an always-on machine that the tablet can reach: a NAS, a Raspberry Pi, a home server or
a small VPS, with Docker.

### 1. Run the server

```bash
git clone https://github.com/kpricorn/inkd && cd inkd
cp .env.example .env                       # fill in the values
mkdir -p config && cp config.example.toml config/inkd.toml
docker compose up -d rmfakecloud
```

Open `RMFAKECLOUD_URL` in a browser and create a user.

### 2. Point the tablet at it

Follow the [rmfakecloud documentation](https://ddvk.github.io/rmfakecloud/) to install its
redirect on the tablet over SSH (the root password is under *Settings → Help → Copyright and
licenses*), then pair the tablet with a code from the rmfakecloud web interface.

- **Turn off automatic updates on the tablet.** A firmware update can remove the redirect or
  change the sync protocol. Check that rmfakecloud supports a new firmware before you update, and
  re-run the installer afterwards.
- The tablet's own Dropbox / Google Drive buttons need reMarkable's paid cloud; inkd replaces them.
- For "Convert to text" on the tablet itself, add MyScript keys to `.env` (free developer account).

### 3. Pair inkd

```bash
docker compose run --rm inkd login           # rmapi asks for a one-time code from the rmfakecloud web UI
docker compose run --rm --entrypoint rclone inkd config   # add a "dropbox" or "gdrive" remote
```

rclone needs a browser for the Dropbox/Google login. On a headless server choose "No" for
auto config and run the `rclone authorize …` command it prints on a computer with a browser.

### 4. Start syncing

```bash
docker compose run --rm inkd sync     # one cycle, to check the output
docker compose up -d                  # then every 5 minutes
docker compose logs -f inkd
docker compose run --rm inkd status   # what inkd knows about
```

## Configuration

See [`config.example.toml`](config.example.toml). The main choices:

- `storage.remote` / `storage.inbox`: any rclone remote (`dropbox:…`, `gdrive:…`, `onedrive:…`).
  The inbox must not lie inside the export folder.
- `obsidian.vault`: the vault on disk. If it lives in Dropbox or Google Drive, mount the synced
  folder (`VAULT_PATH` in `.env`), or run Obsidian Sync / git on the server.
- `ocr.backend`: `claude` needs `ANTHROPIC_API_KEY` and costs roughly a few cents per page, only
  for new or changed pages. `none` keeps images and typed text only. `ocr.instructions` is added
  to the prompt, e.g. `"Notes are in German and English."`

## Running without Docker

Needs Python 3.11+, [rmapi (ddvk fork)](https://github.com/ddvk/rmapi), rclone, pandoc and the
Cairo/Pango libraries.

```bash
pip install -e '.[dev]'
RMAPI_HOST=http://your-server:3000 inkd -c config/inkd.toml sync
pytest
```

## Limitations

- Ink on imported PDFs is exported as a separate `(ink).pdf`, not drawn onto the original pages.
- Highlights on PDFs/EPUBs are included as text when the tablet stores them as text.
- Deletions and moves are not propagated; a moved notebook keeps writing to its existing note.
- Needs firmware 3.x documents (`.rm` v6), via `rmc`/`rmscene`.
