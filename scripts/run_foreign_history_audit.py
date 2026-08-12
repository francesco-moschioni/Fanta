#!/usr/bin/env python3
"""Read-only discovery audit: for players flagged `no_history_transfer`/
`no_history_new_team` in the M3 output (zero Serie A history in this
pipeline), checks whether API-Football's free plan (100 req/day, seasons
2022-2024 only, verified 2026-08-10, docs/SOURCE_REGISTER.md) can find their
prior-league history.

**Real finding (2026-08-12)**: API-Football's `players` search endpoint
rejects a name-only global search -- it requires a `team`/`league`. Hints
below were researched via 14 bounded Haiku web-search subagents (2026-08-12,
public news/official-club sources only, never scraping ToS-blocked sites),
covering all 82 players not yet resolved (5 sampled earlier; 2 -- Ramos G.,
Stones -- already found real data).

**Important pattern the agents surfaced**: many `no_history_new_team`
players are NOT recent transfers -- they've been at their club for years,
and only show zero Serie A history because the *club* is newly promoted
(Frosinone, Como, Monza, Venezia this season). For those, `hint` points at
the same club in a lower division (where they'd actually have minutes), not
a different "prior club" -- flagged per-entry below with a note.

Every hint here is a web-search finding from an LLM agent, not a verified
fact -- re-check before trusting it for a real bid, per CLAUDE.md's
provenance requirements. `search_team`/`search_player` results are raw API
matches for a human to look at; nothing here writes to the domain pipeline
or joins by name into player_code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from fantacalcio.ingest.api_football import FREE_PLAN_DAILY_LIMIT, ApiFootballError, RequestBudget, search_player, search_team

M3_CSV = Path("data/staged/fantacalcio_voti_manual/_m3_replacement_values.csv")
REPORT_PATH = Path("data/staged/fantacalcio_voti_manual/_foreign_history_audit.md")
SEASON = 2023  # free-plan seasons are 2022-2024 only


@dataclass(frozen=True)
class Hint:
    search_name: str  # first token used for the player-search query
    club: str  # club to resolve via search_team
    note: str = ""


# display_name -> Hint. Researched via 14 Haiku web-search subagents,
# 2026-08-12, sources cited in the git history of this file. Sorted by
# quotazione_asta descending (highest-stakes players first) so a limited
# daily API budget covers the players that matter most for a real bid.
HINTS: dict[str, Hint] = {
    "Kevin Carlos": Hint("Kevin", "Basel", "loan chain via Nice; real 2022-24 minutes at Basel"),
    "Mastantuono": Hint("Franco", "River Plate", "Real Madrid spell too recent (2025-26) for free-plan window"),
    "Adams A.": Hint("Akor", "Lillestrom", "direct move from Sevilla; real 2022-24 minutes at Lillestrom"),
    "Alajbegovic": Hint("Kerim", "Red Bull Salzburg", "loan spell with real senior minutes"),
    "Chalobah T.": Hint("Trevoh", "Chelsea", ""),
    "Geubbels": Hint("Willem", "St Gallen", "most recent club Paris FC too recent"),
    "Couto": Hint("Yan", "Girona", "Dortmund loan chain; real minutes at Girona"),
    "Rrahmani Al.": Hint("Albion", "Rapid 1923", "most recent club Sparta Prague too recent"),
    "Koulierakis": Hint("Konstantinos", "Wolfsburg", ""),
    "Daffara": Hint("Giovanni", "Avellino", "Serie C loan, may not be in API-Football at this level"),
    "Doekhi": Hint("Danilho", "Union Berlin", ""),
    "Calò": Hint("Giacomo", "Genoa", "older spell 2019-23; most recent (Cesena) too recent"),
    "Unai Gomez": Hint("Unai", "Athletic Bilbao", ""),
    "Sow": Hint("Djibril", "Eintracht Frankfurt", "older spell 2019-23; most recent (Sevilla) too recent"),
    "Kaiki": Hint("Kaiki", "Cruzeiro", "Brazilian league, likely not covered by API-Football"),
    "Mangas": Hint("Ricardo", "Sporting CP", ""),
    "Oulai": Hint("Christ", "Bastia", "low confidence, limited senior history found"),
    "Valdepenas": Hint("Victor", "Real Madrid", "very low confidence, youth player, minimal senior minutes"),
    "Viery": Hint("Viery", "Gremio", "Brazilian league, likely not covered"),
    "Kofler": Hint("Raphael", "Sudtirol", "Serie B, may not be covered"),
    "Frigan": Hint("Matija", "Westerlo", ""),
    "Thiam": Hint("Demba", "SPAL", "Serie B, may not be covered"),
    "Adorante": Hint("Andrea", "Juve Stabia", "Serie B, may not be covered"),
    "Amondarain": Hint("Mikel", "Estudiantes", "Argentine league, likely not covered"),
    "Milla": Hint("Luis", "Getafe", ""),
    "Meichtry": Hint("Franz", "Thun", ""),
    "Pedraza": Hint("Alfonso", "Villarreal", ""),
    "Halhal": Hint("Redouane", "Atletico Madrid", "loan spell 2023-24; most recent club Mechelen too recent"),
    "Bracaglia": Hint("Gabriele", "Frosinone", "DATA ISSUE: agent found him at Frosinone since mid-2024, not a 2026 transfer -- likely no_history_new_team because Frosinone itself lacks Serie A history, not because he's new"),
    "Cichella": Hint("Matteo", "Frosinone", "DATA ISSUE: same pattern as Bracaglia"),
    "Mitaj": Hint("Mario", "Lokomotiv Moscow", "Russian league, likely not covered; most recent club Al-Ittihad too recent"),
    "Comert": Hint("Eray", "Valencia", ""),
    "Lucchesi": Hint("Lorenzo", "Reggiana", "Serie B, may not be covered"),
    "Palmisani": Hint("Lorenzo", "Frosinone", "DATA ISSUE: agent found him at Frosinone since 2023, uncertain transfer status"),
    "Robinson J.": Hint("Jay", "Southampton", "young player, limited pre-2024 history"),
    "Fitz-Jim": Hint("Kian", "Ajax", ""),
    "Calvani": Hint("Gabriele", "Frosinone", "loan from Genoa but real minutes at Frosinone itself"),
    "Havel": Hint("Elias", "Hartberg", "Austrian league, may not be covered"),
    "Koutsoupias": Hint("Ilias", "Catanzaro", "Serie B, medium confidence, limited pre-2025 data"),
    "Correia T.": Hint("Thierry", "Valencia", ""),
    "Varela G.": Hint("Gustavo", "Gil Vicente", "loan from Benfica, Portuguese league"),
    "Stankovic A.": Hint("Aleksandar", "Club Brugge", "buyback from Inter; was previously on Inter's books"),
    "Diallo O.": Hint("Ousmane", "Alaves", "medium confidence; most recent club Dortmund youth too recent"),
    "Colombo L.": Hint("Leonardo", "Monza", "DATA ISSUE: likely a Monza academy graduate, not an external transfer"),
    "Akpoguma": Hint("Kevin", "Hoffenheim", "very high confidence, 175 Bundesliga apps"),
    "Hasa": Hint("Luis", "Napoli", "limited history, youth/fringe player"),
    "Puczka": Hint("David", "Admira Wacker", "Austrian 2. Liga, may not be covered"),
    "Franjic": Hint("Bartol", "Darmstadt", ""),
    "Chakvetadze": Hint("Giorgi", "Watford", "EFL Championship"),
    "Desplanches": Hint("Sebastiano", "Vicenza", "Serie B 2022-23; most recent club Palermo loan too recent"),
    "Alhassane": Hint("Rahim", "Real Oviedo", "LaLiga2"),
    "Diawara S.": Hint("Sankhoun", "Troyes", "limited history, only 14 league apps"),
    "Aurelio": Hint("Giuseppe", "Spezia", "Serie B"),
    "Tornqvist": Hint("Noel", "Mjallby", "Swedish league, may not be covered"),
    "Lauberbach": Hint("Lion", "Mechelen", "Belgian league"),
    "Lisman": Hint("Kornel", "Lech Poznan", "Polish league"),
    "Vigorito": Hint("Mauro", "Como", "DATA ISSUE: agent found him already at Como, transfer status unclear"),
    "Azon": Hint("Ivan", "Real Zaragoza", "Spanish second division"),
    "Stolz": Hint("Franz", "St Polten", "DATA ISSUE: agent found he joined Genoa Jan 2024, not a fresh 2026 arrival"),
    "Gelli J.": Hint("Jacopo", "Messina", "DATA ISSUE: agent found he joined Frosinone in 2025"),
    "Piana": Hint("Edoardo", "Monopoli", "still loaned from Udinese, Serie C"),
    "Renzetti": Hint("Davide", "Bra", "Serie C"),
    "Dagasso": Hint("Matteo", "Pescara", "Serie C"),
    "Torriani": Hint("Lorenzo", "Milan", "DATA ISSUE: AC Milan academy product, not an external signing"),
    "Samooja": Hint("Jasper", "Honka", "DATA ISSUE: agent found he joined in 2022, Finnish league"),
    "Happonen": Hint("Ukko", "Keski-Uusimaa", "DATA ISSUE: agent found he joined in 2023, Finnish league"),
    "Siviero": Hint("Lapo", "Vicenza", "DATA ISSUE: agent found he joined Torino's youth system in 2024"),
    "El Azzouzi A.": Hint("Anouar", "Fortuna Dusseldorf", "Bundesliga"),
    "Mascardi": Hint("Diego", "Spezia", "Serie B"),
    "Strajnar": Hint("Aljaz", "Mura", "DATA ISSUE: agent found he joined in 2025, Slovenian league"),
    "Lolic": Hint("Eldin", "Sloboda Tuzla", "DATA ISSUE: agent found he joined in 2025, Bosnian league"),
    "Lahdo": Hint("Adrian", "Hammarby", "winter 2026 transfer, Swedish league"),
    "Vismara": Hint("Paolo", "Sampdoria", "loan, Serie A/B"),
    "Grandi": Hint("Matteo", "Sangiuliano City", "DATA ISSUE: agent found he joined in 2023, Serie C"),
    "Pozzi": Hint("Alessio", "Vis Pesaro", "lower Italian division, may not be covered"),
    "De Marzi": Hint("Giorgio", "Roma", "DATA ISSUE: Roma youth academy product, no external prior club"),
    "Corrado": Hint("Niccolo", "Brescia", "Serie B"),
    "Oyono J.": Hint("Jeremy", "Boulogne", "French Ligue 2"),
    "Pieragnolo": Hint("Edoardo", "Reggiana", "Serie B"),
    "Bakoune": Hint("Adam", "Milan", "AC Milan Primavera youth, unlikely to be in senior stats"),
    "Cuenca A.": Hint("Andres", "Barcelona", "La Masia academy, unlikely senior minutes"),
    "Gomes": Hint("Alejandro", "Real Zaragoza", "Spanish second division"),
}


def main() -> None:
    df = pd.read_csv(M3_CSV)
    no_history = df[df["data_quality_tier"].isin(["no_history_transfer", "no_history_new_team"])]
    order = no_history.set_index("display_name")["quotazione_asta"].to_dict()
    ordered_names = sorted(HINTS.keys(), key=lambda n: order.get(n, 0), reverse=True)

    # RequestBudget resets per-process, but the real API account already used 10
    # requests today in the earlier 5-player run (2026-08-12) -- cap this run at
    # the true remaining daily allowance, not the full 100.
    budget = RequestBudget(limit=FREE_PLAN_DAILY_LIMIT - 10)
    lines = [
        "# Foreign-league history discovery audit (API-Football free plan)",
        "",
        f"{len(no_history)} players in `_m3_replacement_values.csv` have zero Serie A "
        f"history. {len(HINTS)} hints researched via 14 Haiku web-search subagents "
        "2026-08-12 (public news only, no scraping of ToS-blocked sites), sorted by "
        f"quotazione_asta descending. Season {SEASON} (free plan restricts seasons to "
        "2022-2024). **Discovery only** -- nothing written to the domain pipeline.",
        "",
        f"Daily budget: {budget.limit} requests, ~2 per player (team search + player "
        "search) -- stops early if the budget would be exceeded, prioritizing the "
        "highest-quotazione players first.",
        "",
    ]

    team_id_cache: dict[str, int | None] = {}
    found_count = 0
    for name in ordered_names:
        hint = HINTS[name]
        if budget.used + 2 > budget.limit:
            lines.append(f"## {name} — stopped: daily budget exhausted ({budget.used}/{budget.limit})")
            lines.append("")
            continue

        lines.append(f"## {name} — hint: {hint.club}" + (f" ({hint.note})" if hint.note else ""))
        lines.append("")

        if hint.club not in team_id_cache:
            try:
                team_result = search_team(hint.club, budget)
                team_id_cache[hint.club] = (
                    team_result.matches[0].get("team", {}).get("id") if team_result.matches else None
                )
            except ApiFootballError as e:
                lines.append(f"Team search failed: `{e}`")
                lines.append("")
                team_id_cache[hint.club] = None
                continue
        team_id = team_id_cache[hint.club]
        if team_id is None:
            lines.append(f"No team found for {hint.club!r} on the free plan.")
            lines.append("")
            continue

        try:
            player_result = search_player(hint.search_name, SEASON, budget, team_id=team_id)
        except ApiFootballError as e:
            lines.append(f"Player search failed: `{e}`")
            lines.append("")
            continue

        if not player_result.matches:
            lines.append(f"No player match at team_id={team_id}, season {SEASON}.")
        else:
            found_count += 1
            lines.append("| Name | Team (that season) | Position | Goals | Assists | Games |")
            lines.append("|---|---|---|---:|---:|---:|")
            for m in player_result.matches[:3]:
                player = m.get("player", {})
                stats = m.get("statistics", [{}])
                s0 = stats[0] if stats else {}
                team_name = s0.get("team", {}).get("name", "?")
                games = s0.get("games", {})
                goals = s0.get("goals", {})
                lines.append(
                    f"| {player.get('name', '?')} | {team_name} | {games.get('position', '?')} | "
                    f"{goals.get('total', '?')} | {goals.get('assists', '?')} | {games.get('appearences', '?')} |"
                )
        lines.append("")

    lines.append(f"## Summary: {found_count} players with real stats found, {budget.used}/{budget.limit} requests used")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nRequests used: {budget.used}/{budget.limit}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
