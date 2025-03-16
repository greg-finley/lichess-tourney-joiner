import json
import os
import requests
from tenacity import (
    retry,
    wait_exponential,
    retry_if_exception
)
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import Literal, NamedTuple

# flake8: noqa: E501

NUM_TOURNEYS_TO_CREATE = 10
CREATE_IF_NOT_FOUND = False


class TournamentConfig(NamedTuple):
    name: str
    path_param: str
    description: str
    clock_limit: int
    clock_increment: int
    nb_rounds: int
    round_interval: int
    hours_between_tournaments: int
    force_even_or_odd_hour: Literal['even', 'odd'] | None = None
    # Replace generic "next swiss" link with a link to the specific tournament when it's ready
    replace_url: str | None = None


CLASSICAL_DESCRIPTION = """This team offers classical (30+0) swiss tournaments every 4 hours.

Next swiss: [https://lichess.org/team/darkonclassical/tournaments](https://lichess.org/team/darkonclassical/tournaments)

Discord: [discord.gg/cNS3u7Gnbn](https://discord.gg/cNS3u7Gnbn)
Main team: [lichess.org/team/darkonteams](https://lichess.org/team/darkonteams)
Rapid team: [lichess.org/team/darkonrapid](https://lichess.org/team/darkonrapid)"""

RAPID_DESCRIPTION = """This team offers Rapid swiss tournaments every 4 hours.

Next swiss: [https://lichess.org/team/darkonrapid/tournaments](https://lichess.org/team/darkonrapid/tournaments)

Discord: [discord.gg/cNS3u7Gnbn](https://discord.gg/cNS3u7Gnbn)
Main team: [lichess.org/team/darkonteams](https://lichess.org/team/darkonteams)
Classical team: [lichess.org/team/darkonclassical](https://lichess.org/team/darkonclassical)"""

MAIN_DESCRIPTION = """This team offers swiss tournaments EVERY HOUR!

Next swiss: [https://lichess.org/team/darkonteams/tournaments](https://lichess.org/team/darkonteams/tournaments)

Our Discord server: [discord.gg/cNS3u7Gnbn](https://discord.gg/cNS3u7Gnbn)
Rapid team: [lichess.org/team/darkonrapid](https://lichess.org/team/darkonrapid)
Classical team: [lichess.org/team/darkonclassical](https://lichess.org/team/darkonclassical)

Have fun!"""

TOURNEY_CONFIGS: list[TournamentConfig] = [
    TournamentConfig(
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
    TournamentConfig(
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
    TournamentConfig(
        name="Hourly Rapid",
        path_param="darkonteams",
        description=MAIN_DESCRIPTION,
        clock_limit=600, # 10 minutes
        clock_increment=0,
        nb_rounds=9,
        round_interval=180, # 3 minutes
        hours_between_tournaments=2,
        force_even_or_odd_hour='even',
        replace_url='https://lichess.org/team/darkonteams/tournaments',
    ),
    TournamentConfig(
        name="Hourly Blitz",
        path_param="darkonteams",
        description=MAIN_DESCRIPTION,
        clock_limit=180, # 3 minutes
        clock_increment=0,
        nb_rounds=11,
        round_interval=120, # 2 minutes
        hours_between_tournaments=2,
        force_even_or_odd_hour='odd',
        replace_url='https://lichess.org/team/darkonteams/tournaments',
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
    """Create a swiss tournament with automatic retries on 429 errors only.
    https://lichess.org/api#tag/Swiss-tournaments/operation/apiSwissNew

    Returns the tournament ID
    """
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
    response.raise_for_status()
    tournament_id = response.json()['id']
    print(f"Created {tournament_config.name} tournament starting at {start_time}: https://lichess.org/swiss/{tournament_id}")
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
    response.raise_for_status()
    print(f"Updated {tournament_config.name} tournament description: https://lichess.org/swiss/{tournament_id}")


def process_tourney_config(tournament_config: TournamentConfig, api_key: str) -> None:
    """https://lichess.org/api#tag/Swiss-tournaments/operation/apiTeamSwiss

    {'id': 'T93RcMg2', 'createdBy': 'gbfgbfgbf', 'startsAt': '2025-03-12T11:00:00Z',
    'name': 'DarkOnClassical', 'clock': {'limit': 1800, 'increment': 0},
    'variant': 'standard', 'round': 0, 'nbRounds': 6, 'nbPlayers': 0, 'nbOngoing': 0,
    'status': 'created', 'nextRound': {'at': '2025-03-12T11:00:00Z', 'in': 276869},
    'verdicts': {'list': [{'condition': 'Play your games', 'verdict': 'ok'}], 'accepted': True},
    'rated': True}
    """

    swisses = requests.get(
        f"https://lichess.org/api/team/{tournament_config.path_param}/swiss?max=10&status=created&createdBy=gbfgbfgbf&name={tournament_config.name.replace(' ', '%20')}",
        headers={"Authorization": f"Bearer {api_key}"},
        stream=True
    )
    created_count = 0
    first_start_time: str | None = None
    last_tournament_id: str | None = None

    for line in swisses.iter_lines():
        if line:
            swiss = json.loads(line)
            created_count += 1
            if first_start_time is None:
                first_start_time = swiss['startsAt']
            if last_tournament_id is None:
                last_tournament_id = swiss['id']

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
