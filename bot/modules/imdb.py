#!/usr/bin/env python3
from contextlib import suppress
from re import findall, search, IGNORECASE
from imdbio import search_title, get_movie, get_akas
from pycountry import countries as conn

from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex
from pyrogram.errors import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty

from bot import bot, config_dict
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage
from bot.helper.ext_utils.bot_utils import get_readable_time, sync_to_async
from bot.helper.telegram_helper.button_build import ButtonMaker

IMDB_GENRE_EMOJI = {
    "Action": "🚀",
    "Adult": "🔞",
    "Adventure": "🌋",
    "Animation": "🎠",
    "Biography": "📜",
    "Comedy": "🪗",
    "Crime": "🔪",
    "Documentary": "🎞",
    "Drama": "🎭",
    "Family": "👨‍👩‍👧‍👦",
    "Fantasy": "🫧",
    "Film Noir": "🎯",
    "Game Show": "🎮",
    "History": "🏛",
    "Horror": "🧟",
    "Musical": "🎻",
    "Music": "🎸",
    "Mystery": "🧳",
    "News": "📰",
    "Reality-TV": "🖥",
    "Romance": "🥰",
    "Sci-Fi": "🌠",
    "Short": "📝",
    "Sport": "⛳",
    "Talk-Show": "👨‍🍳",
    "Thriller": "🗡",
    "War": "⚔",
    "Western": "🪩",
}
LIST_ITEMS = 4


async def imdb_search(_, message):
    if " " in message.text:
        k = await sendMessage(message, "<code>Searching IMDB ...</code>")
        title = message.text.split(" ", 1)[1]
        user_id = message.from_user.id
        buttons = ButtonMaker()
        if result := search(r"tt(\d+)", title, IGNORECASE):
            movieid = result.group(1)
            if movie := await sync_to_async(get_movie, movieid):
                buttons.ibutton(
                    f"🎬 {movie.title} ({getattr(movie, 'year', 'N/A')})",
                    f"imdb {user_id} movie {movieid}",
                )
            else:
                return await editMessage(k, "<i>No Results Found</i>")
        elif title.lower().startswith("https://www.imdb.com/title/tt"):
            movieid = title.replace("https://www.imdb.com/title/tt", "").split("/")[0]
            if movie := await sync_to_async(get_movie, movieid):
                buttons.ibutton(
                    f"🎬 {movie.title} ({getattr(movie, 'year', 'N/A')})",
                    f"imdb {user_id} movie {movieid}",
                )
            else:
                return await editMessage(k, "<i>No Results Found</i>")
        else:
            movies = await sync_to_async(get_poster, title, bulk=True)
            if not movies:
                return await editMessage(
                    k, "<i>No Results Found</i>, Try Again or Use <b>Title ID</b>"
                )
            for movie in movies:
                buttons.ibutton(
                    f"🎬 {movie.title} ({getattr(movie, 'year', 'N/A')})",
                    f"imdb {user_id} movie {movie.id}",
                )
        buttons.ibutton("🚫 Close 🚫", f"imdb {user_id} close")
        await editMessage(
            k,
            "<b><i>Here What I found on IMDb.com</i></b>",
            buttons.build_menu(1),
        )
    else:
        await sendMessage(
            message,
            "<i>Send Movie / TV Series Name along with /imdb Command or send IMDB URL</i>",
        )


def get_poster(query, bulk=False, id=False, file=None):
    if not id:
        query = (query.strip()).lower()
        title = query
        year = findall(r"[1-2]\d{3}$", query, IGNORECASE)
        if year:
            year = list_to_str(year[:1])
            title = (query.replace(year, "")).strip()
        elif file is not None:
            year = findall(r"[1-2]\d{3}", file, IGNORECASE)
            if year:
                year = list_to_str(year[:1])
        else:
            year = None
        movieid = search_title(title.lower()).titles
        if not movieid:
            return None
        if year:
            filtered = (
                list(filter(lambda k: str(k.year or "") == str(year), movieid))
                or movieid
            )
        else:
            filtered = movieid
        movieid = (
            list(filter(lambda k: k.kind in ["movie", "tvSeries"], filtered))
            or filtered
        )
        if bulk:
            return movieid
        movieid = movieid[0].id
    else:
        movieid = query
    movie = get_movie(movieid)
    if not movie:
        return None
    if getattr(movie, "release_date", None):
        date = movie.release_date
    elif getattr(movie, "year", None):
        date = movie.year
    else:
        date = "N/A"

    plot = None
    for keyword in ["plot", "summaries", "synopses"]:
        plot_data = getattr(movie, keyword, None)
        if type(plot_data) is list:
            plot = plot_data[0]
        else:
            plot = plot_data
        if plot:
            break

    plot_full = plot or ""
    if plot and len(plot) > 300:
        plot = f"{plot[:300]}..."

    trailer_list = getattr(movie, "trailers", None)
    trailer = trailer_list[-1] if trailer_list else None

    awards = getattr(movie, "awards", None)
    awards_text = "N/A"
    if awards:
        parts = []
        if getattr(awards, "wins", 0):
            parts.append(f"{awards.wins} win{'s' if awards.wins != 1 else ''}")
        if getattr(awards, "nominations", 0):
            parts.append(
                f"{awards.nominations} nominatio{'n' if awards.nominations == 1 else 'ns'}"
            )
        awards_text = ", ".join(parts) if parts else "N/A"

    company_credits = getattr(movie, "company_credits", None) or {}
    production = (
        list_to_str([c.name for c in company_credits.get("production", [])]) or "N/A"
    )

    kind = ""
    if movie.is_series():
        kind = "Series"
    elif movie.is_episode():
        kind = "Episode"
    elif getattr(movie, "kind", None):
        kind = movie.kind.capitalize()

    try:
        akas = get_akas(f"tt{movie.imdb_id}")
        seen_aka = set()
        aka_list = []
        for a in akas["akas"][: LIST_ITEMS * 2]:
            t_title = a.title
            if t_title.lower() not in seen_aka:
                seen_aka.add(t_title.lower())
                aka_list.append(t_title)
            if len(aka_list) >= LIST_ITEMS:
                break
        aka_text = list_to_str(aka_list) or "N/A"
    except Exception:
        aka_text = list_to_str(getattr(movie, "title_akas", []) or []) or "N/A"

    _box_office = getattr(movie, "box_office", None) or {}
    _end_year = getattr(movie, "year_end", None)
    _end_year_str = f"-{_end_year}" if _end_year else ""
    _certificate = (
        getattr(movie, "certificate", None) or getattr(movie, "mpaa", None) or ""
    )
    if not _certificate:
        _certs = getattr(movie, "certificates", {}) or {}
        for _key in ["US", "MPAA"]:
            if _key in _certs:
                _val = _certs[_key]
                if isinstance(_val, (list, tuple)) and len(_val) >= 2:
                    cert_val = str(_val[1]).strip() if _val[1] else ""
                    if cert_val:
                        _certificate = cert_val
                        break
        if not _certificate:
            for _val in _certs.values():
                if isinstance(_val, (list, tuple)) and len(_val) >= 2:
                    cert_val = str(_val[1]).strip() if _val[1] else ""
                    if cert_val:
                        _certificate = cert_val
                        break
    _keywords_list = getattr(movie, "storyline_keywords", []) or []
    _creators_list = (
        getattr(getattr(movie, "info_series", None), "creators", []) or []
    )
    _production_companies = (
        [c.name for c in getattr(movie, "company_credits", {}).get("production", [])]
        if getattr(movie, "company_credits", None)
        else []
    )

    return {
        "title": movie.title,
        "trailer": trailer or "https://imdb.com/",
        "votes": str(getattr(movie, "votes", "N/A") or "N/A"),
        "aka": aka_text,
        "seasons": (
            len(movie.info_series.display_seasons)
            if getattr(movie, "info_series", None)
            and getattr(movie.info_series, "display_seasons", None)
            else "N/A"
        ),
        "box_office": getattr(movie, "worldwide_gross", "N/A") or "N/A",
        "localized_title": getattr(movie, "title_localized", "N/A") or "N/A",
        "kind": kind,
        "imdb_id": f"tt{movie.imdb_id}",
        "cast": list_to_str([i.name for i in getattr(movie, "stars", [])]) or "N/A",
        "runtime": get_readable_time(int(getattr(movie, "duration", 0) or "0") * 60)
        or "N/A",
        "countries": list_to_hash(getattr(movie, "countries", []) or [], flagg=True)
        or "N/A",
        "certificates": _certificate or "N/A",
        "languages": list_to_hash(getattr(movie, "languages_text", []) or []) or "N/A",
        "director": list_to_str([i.name for i in getattr(movie, "directors", [])])
        or "N/A",
        "writer": list_to_str(
            [i.name for i in getattr(movie, "categories", {}).get("writer", [])]
        )
        or "N/A",
        "producer": list_to_str(
            [i.name for i in getattr(movie, "categories", {}).get("producer", [])]
        )
        or "N/A",
        "composer": list_to_str(
            [i.name for i in getattr(movie, "categories", {}).get("composer", [])]
        )
        or "N/A",
        "cinematographer": list_to_str(
            [
                i.name
                for i in getattr(movie, "categories", {}).get("cinematographer", [])
            ]
        )
        or "N/A",
        "music_team": list_to_str(
            [
                i.name
                for i in getattr(movie, "categories", {}).get("music_department", [])
            ]
        )
        or "N/A",
        "distributors": production,
        "release_date": getattr(movie, "release_date", "N/A") or date or "N/A",
        "year": str(getattr(movie, "year", "N/A") or "N/A"),
        "genres": list_to_hash(getattr(movie, "genres", []) or [], emoji=True) or "N/A",
        "genres_plain": list_to_plain(getattr(movie, "genres", []) or []) or "N/A",
        "countries_plain": list_to_plain(getattr(movie, "countries", []) or []) or "N/A",
        "languages_plain": list_to_plain(getattr(movie, "languages_text", []) or []) or "N/A",
        "poster": getattr(
            movie, "cover_url", "https://telegra.ph/file/5af8d90a479b0d11df298.jpg"
        )
        or "https://telegra.ph/file/5af8d90a479b0d11df298.jpg",
        "plot": plot or "N/A",
        "plot_full": plot_full or "N/A",
        "rating": str(getattr(movie, "rating", "N/A") or "N/A") + " / 10",
        "url": getattr(movie, "url", "N/A") or f"https://www.imdb.com/title/tt{movieid}",
        "url_cast": f"https://www.imdb.com/title/tt{movieid}/fullcredits#cast",
        "url_releaseinfo": f"https://www.imdb.com/title/tt{movieid}/releaseinfo",
        "awards": awards_text,
        "production": production,
        "metascore": str(getattr(movie, "metacritic_rating", "") or ""),
        "end_year": _end_year_str,
        "certificate": _certificate,
        "keywords": " · ".join(_keywords_list[:10]) or "",
        "creators": list_to_str([i.name for i in _creators_list[:3]]) or "N/A",
        "budget": getattr(movie, "production_budget", "") or "",
        "box_opening": _box_office.get("opening_weekend", "") or "",
        "box_domestic": _box_office.get("domestic", "") or "",
        "release_country": getattr(movie, "release_country", "") or "",
        "production_companies": _production_companies,
    }


def list_to_plain(k):
    if not k:
        return ""
    return ", ".join(str(item) for item in k[:10])


def list_to_str(k):
    if not k:
        return ""
    elif len(k) == 1:
        return str(k[0])
    elif LIST_ITEMS:
        k = k[: int(LIST_ITEMS)]
        return " ".join(f"{elem}," for elem in k)[:-1] + " ..."
    else:
        return " ".join(f"{elem}," for elem in k)[:-1]


def list_to_hash(k, flagg=False, emoji=False):
    listing = ""
    if not k:
        return ""
    elif len(k) == 1:
        if not flagg:
            if emoji:
                return str(
                    IMDB_GENRE_EMOJI.get(k[0], "")
                    + " #"
                    + k[0].replace(" ", "_").replace("-", "_")
                )
            return str("#" + k[0].replace(" ", "_").replace("-", "_"))
        try:
            conflag = (conn.get(name=k[0])).flag
            return str(f"{conflag} #" + k[0].replace(" ", "_").replace("-", "_"))
        except AttributeError:
            return str("#" + k[0].replace(" ", "_").replace("-", "_"))
    elif LIST_ITEMS:
        k = k[: int(LIST_ITEMS)]
        for elem in k:
            ele = elem.replace(" ", "_").replace("-", "_")
            if flagg:
                with suppress(AttributeError):
                    conflag = (conn.get(name=elem)).flag
                    listing += f"{conflag} "
            if emoji:
                listing += f"{IMDB_GENRE_EMOJI.get(elem, '')} "
            listing += f"#{ele}, "
        return f"{listing[:-2]}"
    else:
        for elem in k:
            ele = elem.replace(" ", "_").replace("-", "_")
            if flagg:
                conflag = (conn.get(name=elem)).flag
                listing += f"{conflag} "
            listing += f"#{ele}, "
        return listing[:-2]


async def imdb_callback(_, query):
    message = query.message
    user_id = query.from_user.id
    data = query.data.split()
    if len(data) < 4:
        await query.answer()
        await deleteMessage(message)
        return
    if user_id != int(data[1]):
        await query.answer("Not Yours!", show_alert=True)
    elif data[2] == "movie":
        await query.answer("Processing...")
        imdb = await sync_to_async(get_poster, query=data[3], id=True)
        if not imdb:
            await query.answer("Not Found!", show_alert=True)
            await deleteMessage(message)
            return
        reply_to = getattr(message, "reply_to_message", None)
        if not reply_to:
            await deleteMessage(message)
            return
        buttons = ButtonMaker()
        if imdb["trailer"]:
            if isinstance(imdb["trailer"], list):
                buttons.ubutton("▶️ IMDb Trailer ", str(imdb["trailer"][-1]))
                imdb["trailer"] = list_to_str(imdb["trailer"])
            else:
                buttons.ubutton("▶️ IMDb Trailer ", str(imdb["trailer"]))
        buttons.ibutton("🚫 Close 🚫", f"imdb {user_id} close")

        template = config_dict.get("IMDB_TEMPLATE", "")
        if imdb and template != "":
            cap = template.format(
                title=imdb["title"],
                trailer=imdb["trailer"],
                votes=imdb["votes"],
                aka=imdb["aka"],
                seasons=imdb["seasons"],
                box_office=imdb["box_office"],
                localized_title=imdb["localized_title"],
                kind=imdb["kind"],
                imdb_id=imdb["imdb_id"],
                cast=imdb["cast"],
                runtime=imdb["runtime"],
                countries=imdb["countries"],
                certificates=imdb["certificates"],
                languages=imdb["languages"],
                director=imdb["director"],
                writer=imdb["writer"],
                producer=imdb["producer"],
                composer=imdb["composer"],
                cinematographer=imdb["cinematographer"],
                music_team=imdb["music_team"],
                distributors=imdb["distributors"],
                release_date=imdb["release_date"],
                year=imdb["year"],
                genres=imdb["genres"],
                poster=imdb["poster"],
                plot=imdb["plot"],
                rating=imdb["rating"],
                url=imdb["url"],
                url_cast=imdb["url_cast"],
                url_releaseinfo=imdb["url_releaseinfo"],
                **locals(),
            )
        else:
            cap = f"🎬 <b>{imdb['title']}</b> ({imdb['year']})\n\n<b>Rating:</b> {imdb['rating']}\n<b>Genres:</b> {imdb['genres']}\n\n<b>Plot:</b> {imdb['plot']}"

        if imdb.get("poster"):
            try:
                await bot.send_photo(
                    chat_id=reply_to.chat.id,
                    caption=cap,
                    photo=imdb["poster"],
                    reply_to_message_id=reply_to.id,
                    reply_markup=buttons.build_menu(1),
                )
            except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
                poster = imdb.get("poster").replace(".jpg", "._V1_UX360.jpg")
                await sendMessage(
                    reply_to, cap, buttons.build_menu(1), poster
                )
        else:
            await sendMessage(
                reply_to,
                cap,
                buttons.build_menu(1),
                "https://telegra.ph/file/5af8d90a479b0d11df298.jpg",
            )
        await deleteMessage(message)
    else:
        await query.answer()
        await deleteMessage(message)
        if reply_to := getattr(message, "reply_to_message", None):
            await deleteMessage(reply_to)


bot.add_handler(
    MessageHandler(
        imdb_search,
        filters=command(BotCommands.IMDBCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(CallbackQueryHandler(imdb_callback, filters=regex(r"^imdb")))
