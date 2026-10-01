# Zinnia Website

This repository now contains both:

- the permanent GitHub Pages legal URLs in the repository root; and
- the full Flask website source used for Zinnia's live site.

## Important

Do **not** upload `database.db`, Discord tokens, OAuth secrets, or the full `cards/` folder to this public repository.

GitHub stores the website code. The live host runs Flask and points the website at Zinnia's real database and card folder.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

## Environment variables

Copy `.env.example` values into your hosting panel.

Required for live Zinnia data:

- `ZINNIA_DATABASE`
- `ZINNIA_CARDS_DIR`

Required for Discord login:

- `DISCORD_CLIENT_ID`
- `FLASK_SECRET_KEY`

Optional:

- `DISCORD_REDIRECT_URI` — if omitted, the callback URL is built from the current public hostname.
- `DISCORD_INVITE_URL`

## Structure

```text
app.py
templates/
  base.html
  index.html
  collection.html
  wheel.html
  how_to_play.html
  legal.html
  oauth_not_configured.html
static/
  css/style.css
  js/main.js
  images/
```

## Live data

The site reads SQLite in read-mostly mode and exposes:

- `/api/stats`
- logged-in user collection at `/collection`
- card artwork through `/card-art`

The database and cards remain on the bot host, not GitHub.

## Deployment

The Flask app needs a Python-capable host. A typical production command is:

```bash
waitress-serve --host=0.0.0.0 --port=$PORT app:app
```

If the site is hosted beside the Discord bot, point `ZINNIA_DATABASE` and `ZINNIA_CARDS_DIR` to the bot's existing files.
