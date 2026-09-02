from datetime import date
import os
import random
import unicodedata
from urllib.parse import urlencode

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

import mlb_service
import nfl_service
import nba_service
import cfb_service
import awards_service
import war_diamond_service

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
    "cfb": {"name": "College Football", "service": cfb_service, "min": cfb_service.MIN_SEASON,
            "max": lambda: min(date.today().year, cfb_service.MAX_SEASON)},
}

for key, sport in SPORTS.items():
    sport.update({
        "home": f"{key}_home", "leaderboard": f"{key}_leaderboard", "random": f"{key}_random",
        "challenge": f"{key}_challenge", "new_challenge": f"{key}_new_challenge", "search": f"{key}_player_search",
        "awards": f"{key}_awards",
    })


def _normalized_name(name):
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(plain.casefold().split())


def _random_selection(sport_key, minimum=None, maximum=None, groups=None, stats=None, excluded=None):
    sport, options = SPORTS[sport_key], SPORTS[sport_key]["service"].STAT_OPTIONS
    minimum = sport["min"] if minimum is None else max(sport["min"], minimum)
    maximum = sport["max"]() if maximum is None else min(sport["max"](), maximum)
    if minimum > maximum:
        minimum, maximum = maximum, minimum
    groups = [group for group in (groups or options) if group in options]
    selected_stats = set(stats or ())
    candidates, excluded = [], set(excluded or ())
    for group in groups:
        for stat_key in options[group]:
            if selected_stats and f"{group}:{stat_key}" not in selected_stats:
                continue
            stat_min = getattr(sport["service"], "stat_min_season", lambda _group, _stat: sport["min"])(group, stat_key)
            stat_max = maximum - (sport_key == "mlb" and stat_key == "war")
            for season in range(max(minimum, stat_min), stat_max + 1):
                if f"{season}:{group}:{stat_key}" not in excluded:
                    candidates.append((season, group, stat_key))
    if not candidates:
        raise ValueError("No statistics are available inside those parameters.")
    return random.choice(candidates)


def _load_leaders(sport, season, group, stat_key):
    min_games = sport.get("fixed_min_games", 0)
    if sport.get("supports_min_games"):
        return sport["service"].get_leaders(season, group, stat_key, min_games=min_games)
    return sport["service"].get_leaders(season, group, stat_key)


def _valid_selection(sport, season, group, stat_key):
    options = sport["service"].STAT_OPTIONS
    stat_minimum = getattr(sport["service"], "stat_min_season", lambda _group, _stat: sport["min"])
    if group in options and stat_key in options[group] and season >= stat_minimum(group, stat_key):
        return group, stat_key
    for candidate_group, stats in options.items():
        for candidate_stat in stats:
            if season >= stat_minimum(candidate_group, candidate_stat):
                return candidate_group, candidate_stat
    return next(iter(options)), next(iter(next(iter(options.values()))))


def _sport_home(sport_key):
    sport = SPORTS[sport_key]
    intros = {
        "mlb": "Build baseball leaderboards or test your knowledge.",
        "nfl": "Explore NFL seasonal leaders from 1999 through 2024.",
        "nba": "Explore NBA regular-season leaders across scoring, rebounding, playmaking, and defense.",
        "cfb": "Explore player leaders from every FBS conference and team.",
    }
    intro = intros[sport_key]
    return render_template("home.html", sport_name=sport["name"], eyebrow=f'{sport["name"]} history, ranked', intro=intro,
                           leaderboard_endpoint=sport["leaderboard"], random_endpoint=sport["random"],
                           new_challenge_endpoint=sport["new_challenge"], awards_endpoint=sport["awards"],
                           diamond_endpoint="mlb_diamond" if sport_key == "mlb" else None)


def _leaderboard(sport_key):
    sport, options = SPORTS[sport_key], SPORTS[sport_key]["service"].STAT_OPTIONS
    max_season = sport["max"]()
    season = request.args.get("season", max_season, type=int)
    group = request.args.get("group", next(iter(options)))
    if group not in options:
        group = next(iter(options))
    stat_key = request.args.get("stat", next(iter(options[group])))
    season = max(sport["min"], min(season, max_season))
    group, stat_key = _valid_selection(sport, season, group, stat_key)
    min_games = sport.get("fixed_min_games", 0)
    error = None
    try:
        leaders = _load_leaders(sport, season, group, stat_key)
    except (OSError, ValueError, KeyError) as exc:
        app.logger.warning("Could not load %s leaders: %s", sport["name"], exc)
        leaders, error = [], f'{sport["name"]} data is temporarily unavailable. Please try again.'
    stat_minimums = {f"{option_group}:{key}": getattr(sport["service"], "stat_min_season", lambda _group, _stat: sport["min"])(option_group, key)
                     for option_group, stats in options.items() for key in stats}
    randomized = request.args.get("randomized") == "1"
    random_min_year = request.args.get("min_year", sport["min"], type=int)
    random_max_year = request.args.get("max_year", max_season, type=int)
    random_groups = request.args.getlist("groups") or list(options)
    random_stats = request.args.getlist("stats") or [f"{option_group}:{key}" for option_group, stats in options.items() for key in stats]
    if randomized and (error or not leaders):
        query = urlencode({"spin": 1, "min_year": random_min_year, "max_year": random_max_year,
                           "groups": random_groups, "stats": random_stats}, doseq=True)
        return redirect(f'{url_for(sport["random"])}?{query}')
    respin_url = None
    if randomized:
        query = urlencode({"spin": 1, "min_year": random_min_year, "max_year": random_max_year,
                           "groups": random_groups, "stats": random_stats}, doseq=True)
        respin_url = f'{url_for(sport["random"])}?{query}'
    return render_template("index.html", sport_name=sport["name"], season=season, min_season=sport["min"],
                           current_year=max_season, group=group, stat_key=stat_key, stat_options=options,
                           season_choices=range(max_season, sport["min"] - 1, -1), stat_minimums=stat_minimums,
                           leaders=leaders, error=error, randomized=randomized, respin_url=respin_url,
                           supports_min_games=sport.get("supports_min_games", False), min_games=min_games,
                           home_endpoint=sport["home"], leaderboard_endpoint=sport["leaderboard"],
                           random_endpoint=sport["random"])


def _random_redirect(sport_key):
    sport, options = SPORTS[sport_key], SPORTS[sport_key]["service"].STAT_OPTIONS
    minimum = request.values.get("min_year", sport["min"], type=int)
    maximum = request.values.get("max_year", sport["max"](), type=int)
    minimum, maximum = max(sport["min"], minimum), min(sport["max"](), maximum)
    if minimum > maximum:
        minimum, maximum = maximum, minimum
    groups, stats = request.values.getlist("groups"), request.values.getlist("stats")
    if request.method == "GET" and request.args.get("spin") != "1":
        return render_template("random_setup.html", sport_name=sport["name"], min_year=minimum, max_year=maximum,
                               sport_min=sport["min"], sport_max=sport["max"](), stat_options=options,
                               selected_groups=list(options), selected_stats=[], error=None,
                               home_endpoint=sport["home"], random_endpoint=sport["random"])
    groups = [group for group in groups if group in options]
    stats = [token for token in stats if ":" in token and token.split(":", 1)[0] in groups
             and token.split(":", 1)[1] in options[token.split(":", 1)[0]]]
    if not groups or not stats:
        return render_template("random_setup.html", sport_name=sport["name"], min_year=minimum, max_year=maximum,
                               sport_min=sport["min"], sport_max=sport["max"](), stat_options=options,
                               selected_groups=groups, selected_stats=stats, error="Select at least one category and one statistic.",
                               home_endpoint=sport["home"], random_endpoint=sport["random"]), 400
    excluded, selection = set(), None
    for _attempt in range(10):
        try:
            candidate = _random_selection(sport_key, minimum, maximum, groups, stats, excluded)
        except ValueError:
            break
        excluded.add(f"{candidate[0]}:{candidate[1]}:{candidate[2]}")
        try:
            if _load_leaders(sport, *candidate):
                selection = candidate
                break
        except (OSError, ValueError, KeyError) as exc:
            app.logger.warning("Randomized %s selection unavailable (%s/%s/%s): %s", sport["name"], *candidate, exc)
    if selection is None:
        return render_template("random_setup.html", sport_name=sport["name"], min_year=minimum, max_year=maximum,
                               sport_min=sport["min"], sport_max=sport["max"](), stat_options=options,
                               selected_groups=groups, selected_stats=stats,
                               error="No available leaderboard was found after validating several combinations. Try a different year range or try again.",
                               home_endpoint=sport["home"], random_endpoint=sport["random"]), 503
    query = urlencode({"season": selection[0], "group": selection[1], "stat": selection[2], "randomized": 1,
                       "min_games": sport.get("default_min_games", 0), "min_year": minimum, "max_year": maximum,
                       "groups": groups, "stats": stats}, doseq=True)
    return redirect(f'{url_for(sport["leaderboard"])}?{query}')


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
    season = max(sport["min"], min(season, sport["max"]()))
    group, stat_key = _valid_selection(sport, season, group, stat_key)
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


def _award_game(sport_key):
    sport = SPORTS[sport_key]
    award_options = awards_service.AWARDS[sport_key]
    award_key = request.values.get("award", next(iter(award_options)))
    if award_key not in award_options:
        award_key = next(iter(award_options))
    try:
        decades = awards_service.get_decades(sport_key, award_key)
        decade = request.values.get("decade", decades[0], type=int)
        if decade not in decades:
            decade = decades[0]
        winners = awards_service.get_decade_winners(sport_key, award_key, decade)
        player_names = awards_service.get_player_names(sport_key, award_key)
        error = None
    except (OSError, ValueError, KeyError, awards_service.requests.RequestException) as exc:
        app.logger.warning("Could not load %s award history: %s", sport["name"], exc)
        decades, decade, winners, player_names = (), None, [], ()
        error = "Award history is temporarily unavailable. Please try again."

    game_key = f"award:{sport_key}:{award_key}:{decade}"
    if session.get("award_game_key") != game_key:
        session["award_game_key"], session["award_guesses"] = game_key, []
        session["award_forfeited"] = False
    guessed = set(session.get("award_guesses", []))
    forfeited = session.get("award_forfeited", False)
    message = message_type = None
    if request.method == "POST" and request.form.get("action") == "forfeit":
        forfeited = True
        session["award_forfeited"] = True
        message, message_type = "Game over — the remaining winners are shown in red.", "error"
    elif request.method == "POST" and winners and not forfeited:
        submitted = _normalized_name(request.form.get("player", ""))
        matching_names = {winner["name"] for winner in winners
                          if submitted in {_normalized_name(winner["name"]), _normalized_name(winner["name"]).rsplit(" ", 1)[-1]}}
        if len(matching_names) == 1:
            name = matching_names.pop()
            if name in guessed:
                message, message_type = f"You already found {name}.", "neutral"
            else:
                guessed.add(name)
                session["award_guesses"] = list(guessed)
                seasons_won = sum(winner["name"] == name for winner in winners)
                suffix = f" ({seasons_won} winning seasons)" if seasons_won > 1 else ""
                message, message_type = f"Correct — {name}{suffix}!", "success"
        elif len(matching_names) > 1:
            message, message_type = "That last name matches multiple winners. Choose the full name.", "neutral"
        else:
            message, message_type = "Not an award winner in this decade. Try again.", "error"
    guessed_slots = sum(winner["name"] in guessed for winner in winners)
    completed = bool(winners) and guessed_slots == len(winners)
    return render_template(
        "awards.html", sport_name=sport["name"], decade=decade, decades=decades, winners=winners,
        award=award_options[award_key], award_key=award_key, award_options=award_options,
        player_names=player_names, guessed=guessed,
        forfeited=forfeited, finished=completed or forfeited, completed=completed,
        final_score=guessed_slots, message=message, message_type=message_type, error=error,
        home_endpoint=sport["home"], awards_endpoint=sport["awards"],
    )


def _war_diamond():
    team_key = request.values.get("team", "ATL")
    if team_key not in war_diamond_service.TEAMS:
        team_key = "ATL"
    era = request.values.get("era", "medium")
    era = {"modern": "medium", "all_time": "hard"}.get(era, era)
    if era not in war_diamond_service.ERA_OPTIONS:
        era = "medium"
    try:
        lineup = [dict(player) for player in war_diamond_service.get_lineup(team_key, era)]
        player_names = war_diamond_service.get_player_names(team_key, era)
        error = None
    except (OSError, ValueError, KeyError) as exc:
        app.logger.warning("Could not load WAR diamond: %s", exc)
        lineup, player_names, error = [], (), "WAR data is temporarily unavailable. Please try again."
    game_key = f"war-diamond:{team_key}:{era}"
    if session.get("diamond_game_key") != game_key:
        session["diamond_game_key"], session["diamond_guesses"] = game_key, []
        session["diamond_forfeited"] = False
    guessed = set(session.get("diamond_guesses", []))
    forfeited = session.get("diamond_forfeited", False)
    message = message_type = None
    if request.method == "POST" and request.form.get("action") == "forfeit":
        forfeited = True; session["diamond_forfeited"] = True
        message, message_type = "Game over — the remaining positions are shown in red.", "error"
    elif request.method == "POST" and lineup and not forfeited:
        submitted = _normalized_name(request.form.get("player", ""))
        matches = [player for player in lineup if submitted in {_normalized_name(player["name"]), _normalized_name(player["name"]).rsplit(" ", 1)[-1]}]
        if len(matches) == 1:
            position = matches[0]["position"]
            if position in guessed: message, message_type = f"You already filled {position}.", "neutral"
            else:
                guessed.add(position); session["diamond_guesses"] = list(guessed)
                message, message_type = f"Correct — {matches[0]['name']} owns the {position} season!", "success"
        elif len(matches) > 1: message, message_type = "Enter the player's full name.", "neutral"
        else: message, message_type = "That player does not own a position record for this franchise.", "error"
    completed = bool(lineup) and len(guessed) == len(lineup)
    return render_template("war_diamond.html", team_key=team_key, teams=war_diamond_service.TEAMS,
                           era=era, era_options=war_diamond_service.ERA_OPTIONS,
                           team_name=war_diamond_service.TEAMS[team_key][0], lineup=lineup,
                           player_names=player_names,
                           guessed=guessed, forfeited=forfeited, finished=completed or forfeited,
                           final_score=len(guessed), message=message, message_type=message_type,
                           error=error)


@app.route("/")
def home(): return render_template("sports_home.html")
@app.route("/mlb")
def mlb_home(): return _sport_home("mlb")
@app.route("/mlb/leaderboard")
def mlb_leaderboard(): return _leaderboard("mlb")
@app.route("/mlb/random", methods=["GET", "POST"])
def mlb_random(): return _random_redirect("mlb")
@app.route("/mlb/challenge/new")
def mlb_new_challenge(): return _new_challenge("mlb")
@app.route("/mlb/challenge", methods=["GET", "POST"])
def mlb_challenge(): return _challenge("mlb")
@app.route("/mlb/api/player-search")
def mlb_player_search(): return _player_search("mlb")
@app.route("/mlb/awards", methods=["GET", "POST"])
def mlb_awards(): return _award_game("mlb")
@app.route("/mlb/war-diamond", methods=["GET", "POST"])
def mlb_diamond(): return _war_diamond()
@app.route("/nfl")
def nfl_home(): return _sport_home("nfl")
@app.route("/nfl/leaderboard")
def nfl_leaderboard(): return _leaderboard("nfl")
@app.route("/nfl/random", methods=["GET", "POST"])
def nfl_random(): return _random_redirect("nfl")
@app.route("/nfl/challenge/new")
def nfl_new_challenge(): return _new_challenge("nfl")
@app.route("/nfl/challenge", methods=["GET", "POST"])
def nfl_challenge(): return _challenge("nfl")
@app.route("/nfl/api/player-search")
def nfl_player_search(): return _player_search("nfl")
@app.route("/nfl/awards", methods=["GET", "POST"])
def nfl_awards(): return _award_game("nfl")
@app.route("/nba")
def nba_home(): return _sport_home("nba")
@app.route("/nba/leaderboard")
def nba_leaderboard(): return _leaderboard("nba")
@app.route("/nba/random", methods=["GET", "POST"])
def nba_random(): return _random_redirect("nba")
@app.route("/nba/challenge/new")
def nba_new_challenge(): return _new_challenge("nba")
@app.route("/nba/challenge", methods=["GET", "POST"])
def nba_challenge(): return _challenge("nba")
@app.route("/nba/api/player-search")
def nba_player_search(): return _player_search("nba")
@app.route("/nba/awards", methods=["GET", "POST"])
def nba_awards(): return _award_game("nba")
@app.route("/college-football")
def cfb_home(): return _sport_home("cfb")
@app.route("/college-football/leaderboard")
def cfb_leaderboard(): return _leaderboard("cfb")
@app.route("/college-football/random", methods=["GET", "POST"])
def cfb_random(): return _random_redirect("cfb")
@app.route("/college-football/challenge/new")
def cfb_new_challenge(): return _new_challenge("cfb")
@app.route("/college-football/challenge", methods=["GET", "POST"])
def cfb_challenge(): return _challenge("cfb")
@app.route("/college-football/api/player-search")
def cfb_player_search(): return _player_search("cfb")
@app.route("/college-football/awards", methods=["GET", "POST"])
def cfb_awards(): return _award_game("cfb")

if __name__ == "__main__":
    app.run(
        host=os.environ.get("TOP_TEN_HOST", "127.0.0.1"),
        port=int(os.environ.get("TOP_TEN_PORT", "5000")),
        debug=app.config["DEBUG"],
    )
