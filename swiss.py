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

# flake8: noqa: E501

description = """This team offers classical (30+0) swiss tournaments every 4 hours.

Discord: discord.gg/cNS3u7Gnbn

Main team: lichess.org/team/darkonteams
Rapid team: lichess.org/team/darkonrapid"""


def is_429(exception):
    """Check if the exception is a 429 Too Many Requests error"""
    return (isinstance(exception, requests.exceptions.HTTPError) and 
            exception.response.status_code == 429)


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=1200),
    retry=retry_if_exception(is_429)
)
def create_tournament(start_time: str, api_key: str) -> None:
    """Create a swiss tournament with automatic retries on 429 errors only."""
    response = requests.post(
        "https://lichess.org/api/swiss/new/darkonclassical",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "name": "DarkOnClassical",
            "clock.limit": 1800,  # 30 minutes in seconds
            "clock.increment": 0,
            "nbRounds": 9,
            "startsAt": start_time,  # ISO 8601 UTC datetime
            "description": description,
            "conditions": {
                "playYourGames": True
            }
        }
    )
    response.raise_for_status()
    print(f"Created tournament starting at {start_time}")


def main() -> None:
    load_dotenv()
    api_key = os.getenv("GREG_API_KEY")
    assert api_key
    dark_on_classical_swisses = requests.get(
        "https://lichess.org/api/team/darkonclassical/swiss?max=20",
        headers={"Authorization": f"Bearer {api_key}"},
        stream=True
    )

    created_count = 0
    first_start_time: str | None = None

    for line in dark_on_classical_swisses.iter_lines():
        if line:
            swiss = json.loads(line)
            if swiss['status'] == 'created':
                created_count += 1
                if first_start_time is None:
                    first_start_time = swiss['startsAt']

    if not first_start_time:
        raise ValueError("No created tournaments found")

    # Parse the ISO format string to datetime, add 4 hours, convert back to string
    start_dt = datetime.fromisoformat(first_start_time.replace('Z', '+00:00'))
    next_start = (start_dt + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%SZ')

    print(f"Found {created_count} upcoming tournaments")
    print(f"First tournament starts at: {first_start_time}")
    print(f"Next tournament should start at: {next_start}")

    # Create additional tournaments until we have 20
    tournaments_to_create = 20 - created_count
    if tournaments_to_create > 0:
        # Start with next_start and keep adding 4 hours for each new tournament
        current_start = next_start
        for _ in range(tournaments_to_create):
            create_tournament(current_start, api_key)
            
            # Calculate next tournament start time
            current_dt = datetime.fromisoformat(current_start.replace('Z', '+00:00'))
            current_start = (current_dt + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%SZ')
    else:
        print("Already have 20 tournaments, skipping creation")


if __name__ == "__main__":
    main()
