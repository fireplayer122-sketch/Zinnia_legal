import base64
import hashlib
import os
import secrets
import sqlite3
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode

import requests
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix


BASE_DIR = Path(__file__).resolve().parent

DATABASE = Path(
    os.getenv(
        "ZINNIA_DATABASE",
        BASE_DIR.parent / "database.db",
    )
)

CARDS_DIR = Path(
    os.getenv(
        "ZINNIA_CARDS_DIR",
        BASE_DIR.parent / "cards",
    )
)

DISCORD_CLIENT_ID = os.getenv(
    "DISCORD_CLIENT_ID",
    "",
).strip()

DISCORD_REDIRECT_URI = os.getenv(
    "DISCORD_REDIRECT_URI",
    "",
).strip()

DISCORD_INVITE_URL = os.getenv(
    "DISCORD_INVITE_URL",
    "#",
).strip() or "#"


app = Flask(__name__)
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "change-this-before-public-launch",
)

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
)

app.permanent_session_lifetime = timedelta(days=30)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


def get_connection():
    connection = sqlite3.connect(
        DATABASE,
        timeout=10,
    )
    connection.row_factory = sqlite3.Row

    try:
        connection.execute(
            "PRAGMA journal_mode=WAL"
        )
    except sqlite3.DatabaseError:
        pass

    return connection


def table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        LIMIT 1
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def column_exists(cursor, table_name, column_name):
    cursor.execute(
        f"PRAGMA table_info({table_name})"
    )
    return any(
        row[1] == column_name
        for row in cursor.fetchall()
    )


_stats_cache = {
    "at": 0.0,
    "value": {
        "generated": 0,
        "grabbed": 0,
        "a6": 0,
    },
}


def get_bot_stats():
    now = time.time()

    if now - _stats_cache["at"] < 15:
        return _stats_cache["value"]

    stats = {
        "generated": 0,
        "grabbed": 0,
        "a6": 0,
    }

    if not DATABASE.exists():
        return stats

    connection = get_connection()
    cursor = connection.cursor()

    try:
        if table_exists(
            cursor,
            "character_stats",
        ):
            cursor.execute(
                """
                SELECT COALESCE(
                    SUM(drop_count),
                    0
                )
                FROM character_stats
                """
            )
            stats["generated"] = int(
                cursor.fetchone()[0]
                or 0
            )

        if table_exists(
            cursor,
            "owned_cards",
        ):
            item_filter = ""

            if column_exists(
                cursor,
                "owned_cards",
                "item_type",
            ):
                item_filter = (
                    "WHERE LOWER("
                    "COALESCE(item_type, 'card')"
                    ") = 'card'"
                )

            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM owned_cards
                {item_filter}
                """
            )
            stats["grabbed"] = int(
                cursor.fetchone()[0]
                or 0
            )

            if column_exists(
                cursor,
                "owned_cards",
                "ascension",
            ):
                connector = (
                    "AND"
                    if item_filter
                    else "WHERE"
                )

                cursor.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM owned_cards
                    {item_filter}
                    {connector}
                    ascension >= 6
                    """
                )
                stats["a6"] = int(
                    cursor.fetchone()[0]
                    or 0
                )

    finally:
        connection.close()

    _stats_cache["at"] = now
    _stats_cache["value"] = stats
    return stats


def get_user_collection(user_id):
    if not DATABASE.exists():
        return []

    connection = get_connection()
    cursor = connection.cursor()

    try:
        if not table_exists(
            cursor,
            "owned_cards",
        ):
            return []

        has_series = column_exists(
            cursor,
            "owned_cards",
            "series",
        )
        has_ascension = column_exists(
            cursor,
            "owned_cards",
            "ascension",
        )
        has_item_type = column_exists(
            cursor,
            "owned_cards",
            "item_type",
        )
        has_cosmetics = table_exists(
            cursor,
            "card_cosmetics",
        )
        has_levels = table_exists(
            cursor,
            "card_levels",
        )

        select_parts = [
            "oc.card_id",
            "oc.card_name",
            (
                "oc.series"
                if has_series
                else "'' AS series"
            ),
            (
                "oc.ascension"
                if has_ascension
                else "0 AS ascension"
            ),
        ]

        joins = []

        if has_cosmetics:
            select_parts.extend(
                [
                    "COALESCE(cc.rarity_tier, 'Basic') AS rarity_tier",
                    "cc.print_number",
                ]
            )
            joins.append(
                """
                LEFT JOIN card_cosmetics AS cc
                ON cc.card_id = oc.card_id
                """
            )
        else:
            select_parts.extend(
                [
                    "'Basic' AS rarity_tier",
                    "NULL AS print_number",
                ]
            )

        if has_levels:
            select_parts.append(
                "COALESCE(cl.level, 0) AS level"
            )
            joins.append(
                """
                LEFT JOIN card_levels AS cl
                ON cl.card_id = oc.card_id
                """
            )
        else:
            select_parts.append(
                "0 AS level"
            )

        item_filter = (
            """
            AND LOWER(
                COALESCE(oc.item_type, 'card')
            ) = 'card'
            """
            if has_item_type
            else ""
        )

        cursor.execute(
            f"""
            SELECT
                {", ".join(select_parts)}
            FROM owned_cards AS oc
            {" ".join(joins)}
            WHERE oc.user_id = ?
            {item_filter}
            ORDER BY
                oc.rowid DESC
            LIMIT 500
            """,
            (int(user_id),),
        )

        return [
            dict(row)
            for row in cursor.fetchall()
        ]

    finally:
        connection.close()


@app.context_processor
def inject_global_template_data():
    return {
        "discord_user": session.get(
            "discord_user"
        ),
        "invite_url": DISCORD_INVITE_URL,
    }


@app.get("/")
def home():
    return render_template(
        "index.html"
    )


@app.get("/collection")
def collection_page():
    user = session.get(
        "discord_user"
    )

    cards = []

    if user is not None:
        cards = get_user_collection(
            user["id"]
        )

    return render_template(
        "collection.html",
        cards=cards,
    )


@app.get("/wheel")
def wheel_page():
    return render_template(
        "wheel.html"
    )


@app.get("/how-to-play")
def how_to_play():
    return render_template(
        "how_to_play.html"
    )


@app.get("/legal")
def legal():
    return render_template(
        "legal.html"
    )


@app.get("/terms")
def terms():
    return redirect(
        url_for("legal")
        + "#terms"
    )


@app.get("/privacy")
def privacy():
    return redirect(
        url_for("legal")
        + "#privacy"
    )


@app.get("/api/stats")
def stats_api():
    return jsonify(
        get_bot_stats()
    )


@app.get("/card-art")
def card_art():
    series = request.args.get(
        "series",
        "",
    )
    card_name = request.args.get(
        "name",
        "",
    )

    if (
        not series
        or not card_name
    ):
        abort(404)

    candidate = (
        CARDS_DIR
        / series
        / f"{card_name}.png"
    ).resolve()

    cards_root = CARDS_DIR.resolve()

    try:
        candidate.relative_to(
            cards_root
        )
    except ValueError:
        abort(403)

    if not candidate.exists():
        abort(404)

    return send_file(
        candidate
    )


def get_redirect_uri():
    if DISCORD_REDIRECT_URI:
        return DISCORD_REDIRECT_URI

    return url_for(
        "oauth_callback",
        _external=True,
        _scheme="https"
        if request.is_secure
        else request.scheme,
    )


@app.get("/login")
def login():
    if not DISCORD_CLIENT_ID:
        return render_template(
            "oauth_not_configured.html"
        ), 503

    code_verifier = secrets.token_urlsafe(
        64
    )

    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(
                code_verifier.encode(
                    "utf-8"
                )
            ).digest()
        )
        .decode("ascii")
        .rstrip("=")
    )

    state = secrets.token_urlsafe(
        32
    )

    session[
        "discord_oauth_state"
    ] = state
    session[
        "discord_code_verifier"
    ] = code_verifier

    redirect_uri = get_redirect_uri()

    query = urlencode(
        {
            "client_id":
                DISCORD_CLIENT_ID,
            "response_type":
                "code",
            "redirect_uri":
                redirect_uri,
            "scope":
                "identify",
            "state":
                state,
            "code_challenge":
                challenge,
            "code_challenge_method":
                "S256",
        }
    )

    return redirect(
        "https://discord.com/oauth2/authorize?"
        + query
    )


@app.get("/callback")
def oauth_callback():
    expected_state = session.pop(
        "discord_oauth_state",
        None,
    )

    state = request.args.get(
        "state"
    )

    if (
        not expected_state
        or state != expected_state
    ):
        abort(400)

    code = request.args.get(
        "code"
    )

    code_verifier = session.pop(
        "discord_code_verifier",
        None,
    )

    if (
        not code
        or not code_verifier
    ):
        return redirect(
            url_for("home")
        )

    redirect_uri = get_redirect_uri()

    token_response = requests.post(
        "https://discord.com/api/v10/oauth2/token",
        data={
            "client_id":
                DISCORD_CLIENT_ID,
            "grant_type":
                "authorization_code",
            "code":
                code,
            "redirect_uri":
                redirect_uri,
            "code_verifier":
                code_verifier,
        },
        headers={
            "Content-Type":
                "application/x-www-form-urlencoded"
        },
        timeout=10,
    )

    if not token_response.ok:
        print(
            "[Discord OAuth] Token exchange failed:",
            token_response.status_code,
            token_response.text,
            flush=True,
        )
        return (
            "Discord login failed.",
            502,
        )

    access_token = (
        token_response
        .json()
        .get("access_token")
    )

    if not access_token:
        return redirect(
            url_for("home")
        )

    user_response = requests.get(
        "https://discord.com/api/v10/users/@me",
        headers={
            "Authorization":
                f"Bearer {access_token}"
        },
        timeout=10,
    )

    if not user_response.ok:
        return redirect(
            url_for("home")
        )

    user = user_response.json()

    avatar = None

    if user.get("avatar"):
        avatar = (
            "https://cdn.discordapp.com/avatars/"
            f"{user['id']}/{user['avatar']}.png"
        )

    session.permanent = True
    session["discord_user"] = {
        "id":
            int(user["id"]),
        "username":
            (
                user.get("global_name")
                or user.get("username")
                or "Discord User"
            ),
        "avatar":
            avatar,
    }

    return redirect(
        url_for(
            "collection_page"
        )
    )


@app.get("/logout")
def logout():
    session.clear()

    return redirect(
        url_for("home")
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "5000",
            )
        ),
        debug=False,
    )
