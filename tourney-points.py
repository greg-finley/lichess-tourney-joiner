import requests
import json
import os
from dotenv import load_dotenv
from dataclasses import dataclass
import csv

# flake8: noqa: E501

"""This script finds all darkonteams Hourly Ultrabullet tournaments and calculates the total points and games for each player, writing to points.csv."""

@dataclass
class PlayerPerf:
    score: int
    games: int

def get_api_key() -> str:
    # Try to load from .env file (local development)
    load_dotenv()

    api_key = os.getenv("TOURNEY_CREATOR_API_KEY")
    if not api_key:
        raise ValueError("No API key found in environment variables")
    return api_key


def get_arena_tournaments(api_key: str) -> None:
    url = (
        "https://lichess.org/api/team/darkonteams/arena"
        "?max=10000&status=finished&createdBy=gbfgbfgbf"
        "&name=Hourly%20Ultrabullet"
    )
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        stream=True
    )

    tourney_ids: list[str] = []
    player_perfs: dict[str, PlayerPerf] = {}

    for line in response.iter_lines():
        if line:
            tourney = json.loads(line)
            tourney_ids.append(tourney['id'])

    print(f"Found {len(tourney_ids)} tournaments")

    for tourney_id in tourney_ids:
        url = f"https://lichess.org/api/tournament/{tourney_id}/results?nb=1000&sheet=true"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        for line in response.iter_lines():
            if line:
                # {'rank': 1, 'score': 52, 'rating': 1830, 'username': 'g1my', 'flair': 'people.index-pointing-at-the-viewer-light-skin-tone', 'performance': 2084, 'sheet': {'scores': '5545432053205432'}}
                result = json.loads(line)
                username = result['username']
                if username not in player_perfs:
                    player_perfs[username] = PlayerPerf(score=0, games=0)
                player_perfs[username].score += result['score']
                player_perfs[username].games += len(result['sheet']['scores'])

    print(f"Found {len(player_perfs)} players")

    # Sort players by score in descending order
    sorted_players = sorted(
        player_perfs.items(),
        key=lambda x: x[1].score,
        reverse=True
    )

    # Write to CSV
    with open('points.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Username', 'Score', 'Games'])
        for username, perf in sorted_players:
            writer.writerow([username, perf.score, perf.games])

    print("Wrote to points.csv")


if __name__ == "__main__":
    api_key = get_api_key()
    get_arena_tournaments(api_key)
