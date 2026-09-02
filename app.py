from datetime import date
import os
import random
import unicodedata

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

import mlb_service
import nfl_service
import nba_service

app = Flask(__name__)
APP_ENV = os.environ.get("TOP_TEN_ENV", "test").lower()
app.config.update(
    ENVIRONMENT=APP_ENV,
    DEBUG=APP_ENV == "test",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "top-ten-sports-local-development")

SPORTS = {
    "mlb": {"name": "MLB", "service": mlb_service, "min": 1901, "max": lambda: date.today().year},
    "nfl": {"name": "NFL", "service": nfl_service, "min": nfl_service.MIN_SEASON, "max": lambda: nfl_service.MAX_SEASON},
    "nba": {"name": "NBA", "service": nba_service, "min": nba_service.MIN_SEASON, "max": lambda: date.today().year - 1,
            "supports_min_games": True, "default_min_games": 65, "fixed_min_games": 65},
}

for key, sport in SPORTS.items():
    sport.update({
        "home": f"{key}_home", "leaderboard": f"{key}_leaderboard", "random": f"{key}_random",
        "challenge": f"{key}_challenge", "new_challenge": f"{key}_new_challenge", "search": f"{key}_player_search",
    })


def _normalized_name(name):
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(plain.casefold().split())


def _random_selection(sport_key):
    sport, options = SPORTS[sport_key], SPORTS[sport_key]["service"].STAT_OPTIONS
    group = random.choice(list(options))
    stat_key = random.choice(list(options[group]))
    latest = sport["max"]() - (sport_key == "mlb" and stat_key == "war")
    return random.randint(sport["min"], latest), group, stat_key


def _sport_home(sport_key):
    sport = SPORTS[sport_key]
    intros = {
        "mlb": "Build baseball leaderboards or test your knowledge.",
        "nfl": "Explore NFL seasonal leaders from 1999 through 2024.",
        "nba": "Explore NBA regular-season leaders across scoring, rebounding, playmaking, and defense.",
    }
    intro = intros[sport_key]
    return render_template("home.html", sport_name=sport["name"], eyebrow=f'{sport["name"]} history, ranked', intro=intro,
                           leaderboard_endpoint=sport["leaderboard"], random_endpoint=sport["random"],
                           new_challenge_endpoint=sport["new_challenge"])


def _leaderboard(sport_key):
    sport, options = SPORTS[sport_key], SPORTS[sport_key]["service"].STAT_OPTIONS
    max_season = sport["max"]()
    season = request.args.get("season", max_season, type=int)
    group = request.args.get("group", next(iter(options)))
    if group not in options:
        group = next(iter(options))
    stat_key = request.args.get("stat", next(iter(options[group])))
    if stat_key not in options[group]:
        stat_key = next(iter(options[group]))
    season = max(sport["min"], min(season, max_season))
    min_games = sport.get("fixed_min_games", 0)
    error = None
    try:
        if sport.get("supports_min_games"):
            leaders = sport["service"].get_leaders(season, group, stat_key, min_games=min_games)
        else:
            leaders = sport["service"].get_leaders(season, group, stat_key)
    except (OSError, ValueError, KeyError) as exc:
        app.logger.warning("Could not load %s leaders: %s", sport["name"], exc)
        leaders, error = [], f'{sport["name"]} data is temporarily unavailable. Please try again.'
    return render_template("index.html", sport_name=sport["name"], season=season, min_season=sport["min"],
                           current_year=max_season, group=group, stat_key=stat_key, stat_options=options,
                           leaders=leaders, error=error, randomized=request.args.get("randomized") == "1",
                           supports_min_games=sport.get("supports_min_games", False), min_games=min_games,
                           home_endpoint=sport["home"], leaderboard_endpoint=sport["leaderboard"],
                           random_endpoint=sport["random"])


def _random_redirect(sport_key):
    sport, selection = SPORTS[sport_key], _random_selection(sport_key)
    return redirect(url_for(sport["leaderboard"], season=selection[0], group=selection[1], stat=selection[2],
                            randomized=1, min_games=sport.get("default_min_games", 0)))


def _new_challenge(sport_key):
    sport, selection = SPORTS[sport_key], _random_selection(sport_key)
    return redirect(url_for(sport["challenge"], season=selection[0], group=selection[1], stat=selection[2],
                            min_games=sport.get("default_min_games", 0)))


def _player_search(sport_key):
    sport, options = SPORTS[sport_key], SPORTS[sport_key]["service"].STAT_OPTIONS
    season = request.args.get("season", sport["max"](), type=int)
    group, query = request.args.get("group", next(iter(options))), _normalized_name(request.args.get("q", ""))
    if group not in options or not sport["min"] <= season <= sport["max"]() or len(query) < 2:
        return jsonify([])
    try:
        names = sport["service"].get_player_names(season, group)
    except (OSError, ValueError, KeyError):
        return jsonify([])
    starts, contains = [], []
    for name in names:
        normalized = _normalized_name(name)
        if normalized.startswith(query) or any(part.startswith(query) for part in normalized.split()): starts.append(name)
        elif query in normalized: contains.append(name)
    return jsonify((starts + contains)[:8])


def _challenge(sport_key):
    sport, options = SPORTS[sport_key], SPORTS[sport_key]["service"].STAT_OPTIONS
    season = request.values.get("season", sport["max"](), type=int)
    group, stat_key = request.values.get("group", next(iter(options))), request.values.get("stat", "")
    if group not in options or stat_key not in options[group]: return redirect(url_for(sport["new_challenge"]))
    season = max(sport["min"], min(season, sport["max"]()))
    min_games = sport.get("fixed_min_games", 0)
    game_key = f"{sport_key}:{season}:{group}:{stat_key}:{min_games}"
    if session.get("challenge_key") != game_key:
        session["challenge_key"], session["challenge_guesses"] = game_key, []
        session["challenge_forfeited"] = False
    message = message_type = None
    try:
        if sport.get("supports_min_games"):
            leaders = sport["service"].get_leaders(season, group, stat_key, min_games=min_games)
        else:
            leaders = sport["service"].get_leaders(season, group, stat_key)
    except (OSError, ValueError, KeyError) as exc:
        app.logger.warning("Could not load challenge data: %s", exc)
        leaders, message, message_type = [], "Challenge data is temporarily unavailable. Try a new challenge.", "error"
    guessed = set(session.get("challenge_guesses", []))
    forfeited = session.get("challenge_forfeited", False)
    if request.method == "POST" and request.form.get("action") == "forfeit":
        forfeited = True
        session["challenge_forfeited"] = True
        message, message_type = "Game over — the remaining answers are shown in red.", "error"
    elif request.method == "POST" and leaders and not forfeited:
        submitted, matches = _normalized_name(request.form.get("player", "")), []
        for player in leaders:
            full = _normalized_name(player["name"])
            if submitted and submitted in {full, full.rsplit(" ", 1)[-1]}: matches.append(player)
        if len(matches) == 1:
            name = matches[0]["name"]
            if name in guessed: message, message_type = f"You already found {name}.", "neutral"
            else:
                guessed.add(name); session["challenge_guesses"] = list(guessed)
                message, message_type = f"Correct — {name} is on the list!", "success"
        elif len(matches) > 1: message, message_type = "That last name matches more than one player. Enter the full name.", "neutral"
        else: message, message_type = "Not on this top ten. Try another player.", "error"
    completed = bool(leaders) and len(guessed) == len(leaders)
    return render_template("challenge.html", sport_name=sport["name"], season=season, group=group, stat_key=stat_key,
                           definition=options[group][stat_key], leaders=leaders, guessed=guessed, message=message,
                           message_type=message_type, completed=completed, forfeited=forfeited,
                           finished=completed or forfeited, final_score=len(guessed),
                           supports_min_games=sport.get("supports_min_games", False), min_games=min_games,
                           home_endpoint=sport["home"], new_challenge_endpoint=sport["new_challenge"],
                           challenge_endpoint=sport["challenge"], search_endpoint=sport["search"])


@app.route("/")
def home(): return render_template("sports_home.html")
@app.route("/mlb")
def mlb_home(): return _sport_home("mlb")
@app.route("/mlb/leaderboard")
def mlb_leaderboard(): return _leaderboard("mlb")
@app.route("/mlb/random")
def mlb_random(): return _random_redirect("mlb")
@app.route("/mlb/challenge/new")
def mlb_new_challenge(): return _new_challenge("mlb")
@app.route("/mlb/challenge", methods=["GET", "POST"])
def mlb_challenge(): return _challenge("mlb")
@app.route("/mlb/api/player-search")
def mlb_player_search(): return _player_search("mlb")
@app.route("/nfl")
def nfl_home(): return _sport_home("nfl")
@app.route("/nfl/leaderboard")
def nfl_leaderboard(): return _leaderboard("nfl")
@app.route("/nfl/random")
def nfl_random(): return _random_redirect("nfl")
@app.route("/nfl/challenge/new")
def nfl_new_challenge(): return _new_challenge("nfl")
@app.route("/nfl/challenge", methods=["GET", "POST"])
def nfl_challenge(): return _challenge("nfl")
@app.route("/nfl/api/player-search")
def nfl_player_search(): return _player_search("nfl")
@app.route("/nba")
def nba_home(): return _sport_home("nba")
@app.route("/nba/leaderboard")
def nba_leaderboard(): return _leaderboard("nba")
@app.route("/nba/random")
def nba_random(): return _random_redirect("nba")
@app.route("/nba/challenge/new")
def nba_new_challenge(): return _new_challenge("nba")
@app.route("/nba/challenge", methods=["GET", "POST"])
def nba_challenge(): return _challenge("nba")
@app.route("/nba/api/player-search")
def nba_player_search(): return _player_search("nba")

if __name__ == "__main__":
    app.run(
        host=os.environ.get("TOP_TEN_HOST", "127.0.0.1"),
        port=int(os.environ.get("TOP_TEN_PORT", "5000")),
        debug=app.config["DEBUG"],
    )
