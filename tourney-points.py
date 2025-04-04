import requests
import json
import os
from dotenv import load_dotenv
from dataclasses import dataclass
import csv

# flake8: noqa: E501

NUM_TOURNAMENTS = 10000

"""This script finds all darkonteams Hourly Ultrabullet tournaments and calculates the total points and games for each player, writing to points.tsv."""

@dataclass
class PlayerPerf:
    score: int
    games: int
    num_tournaments: int
    wins: int
    losses: int
    draws: int

def get_api_key() -> str:
    # Try to load from .env file (local development)
    load_dotenv()

    api_key = os.getenv("TOURNEY_CREATOR_API_KEY")
    if not api_key:
        raise ValueError("No API key found in environment variables")
    return api_key

def parse_lichess_scoresheet(scoresheet: str) -> tuple[int, int, int, int]:
    wins = 0
    losses = 0
    draws = 0
    games = 0

    streak = 0  # consecutive wins (2 or more triggers streak)

    for char in scoresheet:
        score = int(char)
        games += 1
        if score == 0:
            losses += 1
            streak = 0  # loss breaks streak

        elif score == 1:
            draws += 1
            streak = 0  # draw breaks streak

        elif score == 2:
            if streak >= 2:
                # we're in a streak, so this must be a draw worth 2 pts
                draws += 1
                streak = 0  # draw breaks streak
            else:
                # not in streak → win worth 2 pts
                wins += 1
                streak += 1

        elif score == 3:
            # win + berserk, not in streak
            wins += 1
            streak += 1

        elif score == 4:
            # win in streak
            wins += 1
            streak += 1

        elif score == 5:
            # win in streak + berserk
            wins += 1
            streak += 1

        else:
            raise ValueError(f"Unexpected score digit: {score}")

    return wins, losses, draws, games



def get_arena_tournaments(api_key: str) -> None:
    url = (
        "https://lichess.org/api/team/darkonteams/arena"
        f"?max={NUM_TOURNAMENTS}&status=finished&createdBy=gbfgbfgbf"
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
                    player_perfs[username] = PlayerPerf(score=0, games=0, num_tournaments=0, wins=0, losses=0, draws=0)
                player_perfs[username].score += result['score']
                player_perfs[username].num_tournaments += 1
                wins, losses, draws, games = parse_lichess_scoresheet(result['sheet']['scores'])
                player_perfs[username].wins += wins
                player_perfs[username].losses += losses
                player_perfs[username].draws += draws
                player_perfs[username].games += games

    print(f"Found {len(player_perfs)} players")

    # Sort players by score in descending order
    sorted_players = sorted(
        player_perfs.items(),
        key=lambda x: x[1].score,
        reverse=True
    )

    with open('points.tsv', 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['Username', 'Score', 'Tournaments', 'Games', 'Wins', 'Losses', 'Draws', 'Win %', 'Loss %', 'Draw %'])
        for username, perf in sorted_players:
            win_pct = f"{round((perf.wins / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
            loss_pct = f"{round((perf.losses / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
            draw_pct = f"{round((perf.draws / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
            writer.writerow([
                username, perf.score, perf.num_tournaments, perf.games, 
                perf.wins, perf.losses, perf.draws,
                win_pct, loss_pct, draw_pct
            ])

    print("Wrote to points.tsv")


if __name__ == "__main__":
    api_key = get_api_key()
    get_arena_tournaments(api_key)
