import calendar
import json
import os
import requests
from tenacity import (
    retry,
    wait_exponential,
    retry_if_exception
)
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from typing import Literal
from dataclasses import dataclass

# flake8: noqa: E501

NUM_TOURNEYS_TO_CREATE = 5
CREATE_IF_NOT_FOUND = False


@dataclass
class TournamentConfig:
    name: str
    path_param: str
    description: str
    clock_limit: float
    clock_increment: int
    hours_between_tournaments: int
    force_even_or_odd_hour: Literal['even', 'odd'] | None = None
    replace_url: str | None = None

@dataclass
class ArenaConfig(TournamentConfig):
    minutes: int = 90

@dataclass
class SwissConfig(TournamentConfig):
    nb_rounds: int = 9
    round_interval: int = 60

PROMO = requests.get("https://rentry.co/nnt3nqhc/raw").text


CLASSICAL_DESCRIPTION = PROMO + """

This team offers classical (30+0) swiss tournaments every 4 hours.

Next swiss: [https://lichess.org/team/darkonclassical/tournaments](https://lichess.org/team/darkonclassical/tournaments)

Discord: [discord.gg/cNS3u7Gnbn](https://discord.gg/cNS3u7Gnbn)
Main team: [lichess.org/team/darkonteams](https://lichess.org/team/darkonteams)
Rapid team: [lichess.org/team/darkonrapid](https://lichess.org/team/darkonrapid)"""

RAPID_DESCRIPTION = PROMO + """

This team offers Rapid swiss tournaments every 4 hours.

Next swiss: [https://lichess.org/team/darkonrapid/tournaments](https://lichess.org/team/darkonrapid/tournaments)

Discord: [discord.gg/cNS3u7Gnbn](https://discord.gg/cNS3u7Gnbn)
Main team: [lichess.org/team/darkonteams](https://lichess.org/team/darkonteams)
Classical team: [lichess.org/team/darkonclassical](https://lichess.org/team/darkonclassical)"""

MAIN_DESCRIPTION = PROMO + """

This team offers swiss tournaments EVERY HOUR!

Next swiss: [https://lichess.org/team/darkonteams/tournaments](https://lichess.org/team/darkonteams/tournaments)

Our Discord server: [discord.gg/cNS3u7Gnbn](https://discord.gg/cNS3u7Gnbn)
Rapid team: [lichess.org/team/darkonrapid](https://lichess.org/team/darkonrapid)
Classical team: [lichess.org/team/darkonclassical](https://lichess.org/team/darkonclassical)

Have fun!"""

ARENA_DESCRIPTION = PROMO + """

We host hourly Ultrabullet tournaments! (every 2 hours)

HOURLY ULTRABULLET ALL-TIME RANKING: [View Ranking Here](https://docs.google.com/spreadsheets/d/12aZszJiwVvh5RBggnbpuy4ePliJ9aJS9cCX-7UJgcX8/edit?usp=sharing](https://docs.google.com/spreadsheets/d/12aZszJiwVvh5RBggnbpuy4ePliJ9aJS9cCX-7UJgcX8/edit?usp=sharing)

Next hourly: [https://lichess.org/team/darkonteams/tournaments](https://lichess.org/team/darkonteams/tournaments)

Our Discord server: [discord.gg/cNS3u7Gnbn](https://discord.gg/cNS3u7Gnbn)"""

BLITZ_SHIELD_DESCRIPTION = """Next Shield: [https://lichess.org/team/darkonteams/tournaments](https://lichess.org/team/darkonteams/tournaments) 

Welcome to the weekly blitz shield swiss!
The winner of this swiss keeps the shield until next week, where he/she has to defend it.

Discord: [discord.gg/cNS3u7Gnbn](https://discord.gg/cNS3u7Gnbn)"""

TOURNEY_CONFIGS: list[TournamentConfig] = [
    SwissConfig(
        name="DarkOnClassical",
        path_param="darkonclassical",
        description=CLASSICAL_DESCRIPTION,
        clock_limit=1800, # 30 minutes
        clock_increment=0,
        nb_rounds=6,
        round_interval=300, # 5 minutes
        hours_between_tournaments=4,
        replace_url='https://lichess.org/team/darkonclassical/tournaments',
    ),
    SwissConfig(
        name="DarkOnRapid",
        path_param="darkonrapid",
        description=RAPID_DESCRIPTION,
        clock_limit=600, # 10 minutes
        clock_increment=0,
        nb_rounds=9,
        round_interval=60, # 1 minute
        hours_between_tournaments=4,
        replace_url='https://lichess.org/team/darkonrapid/tournaments',
    ),
    SwissConfig(
        name="Hourly Rapid",
        path_param="darkonteams",
        description=MAIN_DESCRIPTION,
        clock_limit=600, # 10 minutes
        clock_increment=0,
        nb_rounds=9,
        round_interval=120, # 2 minutes
        hours_between_tournaments=2,
        force_even_or_odd_hour='even',
        replace_url='https://lichess.org/team/darkonteams/tournaments',
    ),
    SwissConfig(
        name="Hourly Blitz",
        path_param="darkonteams",
        description=MAIN_DESCRIPTION,
        clock_limit=180, # 3 minutes
        clock_increment=0,
        nb_rounds=11,
        round_interval=60, # 1 minute
        hours_between_tournaments=2,
        force_even_or_odd_hour='odd',
        replace_url='https://lichess.org/team/darkonteams/tournaments',
    ),
    SwissConfig(
        name="Blitz Shield",
        path_param="darkonteams",
        description=BLITZ_SHIELD_DESCRIPTION,
        clock_limit=180, # 3 minutes
        clock_increment=0,
        nb_rounds=13,
        round_interval=60, # 1 minute
        hours_between_tournaments=168, # 1 week
        replace_url='https://lichess.org/team/darkonteams/tournaments',
    ),
    ArenaConfig(
        name="Hourly Ultrabullet",
        path_param="darkonteams",
        description=ARENA_DESCRIPTION,
        clock_limit=0.25, 
        clock_increment=0,
        hours_between_tournaments=2,
        force_even_or_odd_hour='even',
        replace_url='https://lichess.org/team/darkonteams/tournaments',
        minutes=90,
    )
]


def is_429(exception):
    """Check if the exception is a 429 Too Many Requests error"""
    is_429_error = (isinstance(exception, requests.exceptions.HTTPError) and 
                   exception.response.status_code == 429)
    if is_429_error:
        print("Hit rate limit (429). Retrying...")
    return is_429_error


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=1200),
    retry=retry_if_exception(is_429)
)
def create_tournament(start_time: str, api_key: str, tournament_config: TournamentConfig) -> str:
    """Create a tournament with automatic retries on 429 errors only.
    https://lichess.org/api#tag/Swiss-tournaments/operation/apiSwissNew

    Returns the tournament ID
    """
    if isinstance(tournament_config, SwissConfig):
        response = requests.post(
            f"https://lichess.org/api/swiss/new/{tournament_config.path_param}",
            headers={"Authorization": f"Bearer {api_key}"},
        json={
            "name": tournament_config.name,
            "clock.limit": tournament_config.clock_limit,
            "clock.increment": tournament_config.clock_increment,
            "nbRounds": tournament_config.nb_rounds,
            "startsAt": start_time,
            "description": tournament_config.description,
            "conditions.playYourGames": True,
            "roundInterval": tournament_config.round_interval
        }
    )
    elif isinstance(tournament_config, ArenaConfig):
        response = requests.post(
            "https://lichess.org/api/tournament",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "name": tournament_config.name,
                "clockTime": tournament_config.clock_limit,
                "clockIncrement": tournament_config.clock_increment,
                "conditions.teamMember.teamId": tournament_config.path_param,
                "startDate": int(calendar.timegm(datetime.fromisoformat(start_time.replace('Z', '+00:00')).timetuple()) * 1000),
                "description": tournament_config.description,
                "minutes": tournament_config.minutes,
            }
        )
    else:
        raise ValueError(f"Unknown tournament config type: {type(tournament_config)}")
    response.raise_for_status()
    tournament_id = response.json()['id']
    print(f"Created {tournament_config.name} tournament starting at {start_time}: https://lichess.org/{isinstance(tournament_config, ArenaConfig) and 'tournament' or 'swiss'}/{tournament_id}")
    return tournament_id

@retry(
    wait=wait_exponential(multiplier=1, min=1, max=1200),
    retry=retry_if_exception(is_429)
)
def update_tournament(tournament_id: str | None, next_tournament_id: str, api_key: str, tournament_config: TournamentConfig) -> None:
    """Update a tournament with automatic retries on 429 errors only.
    https://lichess.org/api#tag/Swiss-tournaments/operation/apiSwissUpdate
    """
    if not tournament_config.replace_url or not tournament_id:
        print(f"No tournament ID ({tournament_id}) or replace URL ({tournament_config.replace_url}) for {tournament_config.name}, skipping update")
        return
    if isinstance(tournament_config, SwissConfig):
        response = requests.post(
        f"https://lichess.org/api/swiss/{tournament_id}/edit",
        headers={"Authorization": f"Bearer {api_key}"},
        # Update description and set everything back again
        json={
            "description": tournament_config.description.replace(tournament_config.replace_url, f"https://lichess.org/swiss/{next_tournament_id}"),
            "name": tournament_config.name,
            "clock.limit": tournament_config.clock_limit,
            "clock.increment": tournament_config.clock_increment,
            "nbRounds": tournament_config.nb_rounds,
                "conditions.playYourGames": True,
                "roundInterval": tournament_config.round_interval
            }
        )
    elif isinstance(tournament_config, ArenaConfig):
        response = requests.post(
            f"https://lichess.org/api/tournament/{tournament_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "name": tournament_config.name,
                "clockTime": tournament_config.clock_limit,
                "clockIncrement": tournament_config.clock_increment,
                "conditions.teamMember.teamId": tournament_config.path_param,
                "description": tournament_config.description.replace(tournament_config.replace_url, f"https://lichess.org/tournament/{next_tournament_id}"),
                "minutes": tournament_config.minutes,
            }
        )
    else:
        raise ValueError(f"Unknown tournament config type: {type(tournament_config)}")
    response.raise_for_status()
    print(f"Updated {tournament_config.name} tournament description: https://lichess.org/{isinstance(tournament_config, ArenaConfig) and 'tournament' or 'swiss'}/{tournament_id}")


def process_tourney_config(tournament_config: TournamentConfig, api_key: str) -> None:
    """https://lichess.org/api#tag/Swiss-tournaments/operation/apiTeamSwiss

Swiss:
{
  'id': 'T93RcMg2',
  'createdBy': 'gbfgbfgbf',
  'startsAt': '2025-03-12T11:00:00Z',
  'name': 'DarkOnClassical',
  'clock': {
    'limit': 1800,
    'increment': 0
  },
  'variant': 'standard',
  'round': 0,
  'nbRounds': 6,
  'nbPlayers': 0,
  'nbOngoing': 0,
  'status': 'created',
  'nextRound': {
    'at': '2025-03-12T11:00:00Z',
    'in': 276869
  },
  'verdicts': {
    'list': [
      {
        'condition': 'Play your games',
        'verdict': 'ok'
      }
    ],
    'accepted': True
  },
  'rated': True
}

Arena:
{
  'id': 'smwurWQO',
  'createdBy': 'gbfgbfgbf',
  'system': 'arena',
  'minutes': 90,
  'clock': {
    'limit': 900,
    'increment': 0
  },
  'rated': True,
  'fullName': 'Hourly Ultrabullet Arena',
  'nbPlayers': 0,
  'variant': {
    'key': 'standard',
    'short': 'Std',
    'name': 'Standard'
  },
  'startsAt': 1742969700000,
  'finishesAt': 1742975100000,
  'status': 10,
  'perf': {
    'key': 'rapid',
    'name': 'Rapid',
    'position': 2,
    'icon': '#'
  },
  'secondsToStart': 7947,
  'teamMember': 'darkonteams'
}
    """

    
    tourneys = requests.get(
        f"https://lichess.org/api/team/{tournament_config.path_param}/{'arena' if isinstance(tournament_config, ArenaConfig) else 'swiss'}?max=10&status=created&createdBy=gbfgbfgbf&name={tournament_config.name.replace(' ', '%20')}",
        headers={"Authorization": f"Bearer {api_key}"},
        stream=True
    )
    created_count = 0
    first_start_time: str | None = None
    last_tournament_id: str | None = None

    for line in tourneys.iter_lines():
        if line:
            tourney = json.loads(line)
            created_count += 1
            if first_start_time is None:
                if isinstance(tournament_config, ArenaConfig):
                    first_start_time = datetime.fromtimestamp(tourney['startsAt']/1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                else:
                    first_start_time = tourney['startsAt']
            if last_tournament_id is None:
                last_tournament_id = tourney['id']

    if not first_start_time:
        if CREATE_IF_NOT_FOUND:
            current = datetime.utcnow()
            first_start_time = current.replace(minute=15, second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M:%SZ')
        else:
            raise ValueError("No created tournaments found")

    print(f"Found {created_count} upcoming {tournament_config.name} tournaments")
    print(f"First tournament starts at: {first_start_time}")

    next_start_str = first_start_time

    # Create additional tournaments until we have NUM_TOURNEYS_TO_CREATE
    tournaments_to_create = NUM_TOURNEYS_TO_CREATE - created_count
    if tournaments_to_create > 0:
        current_dt = datetime.fromisoformat(next_start_str.replace('Z', '+00:00'))
        
        for _ in range(tournaments_to_create):
            next_start = (current_dt + timedelta(hours=tournament_config.hours_between_tournaments))
            if tournament_config.force_even_or_odd_hour:
                if tournament_config.force_even_or_odd_hour == 'even' and next_start.hour % 2 == 1:
                    next_start = next_start + timedelta(hours=1)
                elif tournament_config.force_even_or_odd_hour == 'odd' and next_start.hour % 2 == 0:
                    next_start = next_start + timedelta(hours=1)
            next_start_str = next_start.strftime('%Y-%m-%dT%H:%M:%SZ')
            next_tournament_id = create_tournament(next_start_str, api_key, tournament_config)
            update_tournament(last_tournament_id, next_tournament_id, api_key, tournament_config)
            current_dt = next_start
            last_tournament_id = next_tournament_id
    else:
        print(f"Already have {NUM_TOURNEYS_TO_CREATE} {tournament_config.name} tournaments, skipping creation")


def get_api_key() -> str:
    """Get API key from environment variables, supporting both local and Cloud Function environments"""
    # Try to load from .env file (local development)
    load_dotenv()
    
    api_key = os.getenv("TOURNEY_CREATOR_API_KEY")
    if not api_key:
        raise ValueError("No API key found in environment variables")
    return api_key

def main(event, context) -> None:
    api_key = get_api_key()
    for tournament_config in TOURNEY_CONFIGS:
        process_tourney_config(tournament_config, api_key)

if __name__ == "__main__":
    main(None, None)
