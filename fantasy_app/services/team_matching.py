"""
Club-name normalization, used wherever two data sources need to be joined on a team name
instead of a shared numeric ID (FPL's team IDs and football-data.org's team IDs are in
different namespaces; football-data.org uses full official names like "Manchester City FC"
where FPL uses "Man City").
"""

from __future__ import annotations

_SUFFIXES = (" fc", " cf", " afc", " sad", " cd")
# "AFC " as a PREFIX (AFC Bournemouth) is a different club-naming convention than the "afc"
# SUFFIX case above (a club that plays as "X AFC") -- confirmed real bug: this wasn't handled at
# all, so "AFC Bournemouth" (football-data.org's name) normalized to "afc bournemouth" while
# FPL's plain "Bournemouth" normalized to "bournemouth" -- two different strings for the same
# club, silently dropping Bournemouth's entire historical-season match history from the ratings
# fit's likelihood (see NOTES-model-improvements.md).
_PREFIXES = ("afc ",)

# FPL's shortened display names -> the normalized form we key everything on.
_ALIASES = {
    "man city": "manchester city",
    "man utd": "manchester united",
    "man united": "manchester united",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "nott'm forest": "nottingham forest",
    "nottm forest": "nottingham forest",
    "leeds": "leeds united",
    "newcastle": "newcastle united",
    "brighton": "brighton hove albion",
    "west ham": "west ham united",
    "west brom": "west bromwich albion",
    "sheffield utd": "sheffield united",
    "atletico madrid": "atletico de madrid",
    "atleti": "atletico de madrid",
    "real sociedad": "real sociedad",
    "athletic bilbao": "athletic club",
    "athletic club bilbao": "athletic club",
}


def normalize_team_name(name: str) -> str:
    n = name.strip().lower()
    # "&" vs "and" vs dropped entirely is the other real mismatch this fixes: football-data.org's
    # "Brighton & Hove Albion FC" kept its ampersand after suffix-stripping ("brighton & hove
    # albion"), while the "brighton" alias below maps FPL's plain "Brighton" to "brighton hove
    # albion" (no ampersand) -- two different strings for the same club. Stripping "&" uniformly,
    # before suffix/prefix handling or the alias lookup, makes both sides converge regardless of
    # which one (if either) happens to spell it out.
    n = " ".join(n.replace("&", " ").split())
    for suffix in _SUFFIXES:
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
    for prefix in _PREFIXES:
        if n.startswith(prefix):
            n = n[len(prefix) :].strip()
    return _ALIASES.get(n, n)


def names_match(a: str, b: str) -> bool:
    na, nb = normalize_team_name(a), normalize_team_name(b)
    return na == nb or na in nb or nb in na


def find_best_match(name: str, candidates: list[str]) -> str | None:
    """Best-effort match of `name` against a list of candidate team names; None if nothing close."""
    target = normalize_team_name(name)
    for c in candidates:
        if normalize_team_name(c) == target:
            return c
    for c in candidates:
        if names_match(name, c):
            return c
    return None
