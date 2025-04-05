import requests
import json
import os
from dotenv import load_dotenv
from dataclasses import dataclass
import csv

import psycopg

# flake8: noqa: E501

NUM_TOURNAMENTS = 100000

"""This script finds all darkonteams Hourly Ultrabullet tournaments and calculates the total points and games for each player, writing to points.tsv."""

@dataclass
class PlayerPerf:
    score: int
    games: int
    num_tournaments: int
    tournament_wins: int
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

def get_db_connection():
    conn = psycopg.connect(os.environ["NEON_DATABASE_URL"])
    return conn

def get_latest_tourney_id(cursor: psycopg.Cursor) -> str:
    """Get the ID of the latest processed tournament from the database."""
    cursor.execute("SELECT id FROM latest_tourney LIMIT 1")
    result = cursor.fetchone()
    if result is None:
        raise ValueError("No latest tournament ID found in database")
    return result[0]

def get_prior_stats(cursor: psycopg.Cursor) -> dict[str, PlayerPerf]:
    """Get the prior stats for each player from the database."""
    cursor.execute("SELECT username, score, games, num_tournaments, tournament_wins, wins, losses, draws FROM tourney_stats")
    result = cursor.fetchall()
    return {row[0]: PlayerPerf(*row[1:]) for row in result}

def update_stats(conn: psycopg.Connection, cursor: psycopg.Cursor, player_perfs: dict[str, PlayerPerf], latest_tourney_id: str) -> None:
    """
    Update player statistics and latest tournament ID in a single transaction.
    Truncates the tourney_stats table and rewrites all stats.
    """
    # Truncate the tourney_stats table
    cursor.execute("TRUNCATE TABLE tourney_stats")
    
    # Insert all player stats
    for username, perf in player_perfs.items():
        cursor.execute(
            "INSERT INTO tourney_stats (username, score, games, num_tournaments, tournament_wins, wins, losses, draws) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (username, perf.score, perf.games, perf.num_tournaments, perf.tournament_wins, perf.wins, perf.losses, perf.draws)
        )
    
    # Update the latest tournament ID
    cursor.execute("UPDATE latest_tourney SET id = %s", (latest_tourney_id,))
    
    conn.commit()
    
    print(f"Updated stats for {len(player_perfs)} players and set latest tournament ID to {latest_tourney_id}")

def get_arena_tournaments(api_key: str) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            latest_tourney_id = get_latest_tourney_id(cursor)
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
    response.raise_for_status()

    tourney_ids: list[str] = []

    for line in response.iter_lines():
        if line:
            tourney = json.loads(line)
            tourney_id = tourney['id']
            if tourney_id == latest_tourney_id:
                break
            tourney_ids.append(tourney_id)

    if not tourney_ids:
        print("No new tournaments found")
        return

    print(f"Found {len(tourney_ids)} tournaments")

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            player_perfs: dict[str, PlayerPerf] = get_prior_stats(cursor)

    for i, tourney_id in enumerate(tourney_ids):
        print(f"Processing tournament {i+1} of {len(tourney_ids)}")
        url = f"https://lichess.org/api/tournament/{tourney_id}/results?nb=1000"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            stream=True
        )
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                # {'rank': 1, 'score': 52, 'rating': 1830, 'username': 'g1my', 'flair': 'people.index-pointing-at-the-viewer-light-skin-tone', 'performance': 2084, 'sheet': {'scores': '5545432053205432'}}
                result = json.loads(line)
                username = result['username']
                if username not in player_perfs:
                    player_perfs[username] = PlayerPerf(score=0, games=0, num_tournaments=0, tournament_wins=0, wins=0, losses=0, draws=0)
                player_perfs[username].score += result['score']
                player_perfs[username].num_tournaments += 1
                if result['rank'] == 1:
                    player_perfs[username].tournament_wins += 1

        games_url = f"https://lichess.org/api/tournament/{tourney_id}/games?moves=false&tags=false"
        games_response = requests.get(
            games_url,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/x-ndjson",},
            stream=True
        )
        games_response.raise_for_status()
        for line in games_response.iter_lines():
            if line:
                game = json.loads(line)
                white = game['players']['white']['user']['name']
                black = game['players']['black']['user']['name']
                
                # Sometimes they don't exist due to players closing their account
                white_exists = white in player_perfs
                black_exists = black in player_perfs
                
                winner = game.get('winner')
                
                # Process white player if they exist
                if white_exists:
                    player_perfs[white].games += 1
                    if winner == 'white':
                        player_perfs[white].wins += 1
                    elif winner == 'black':
                        player_perfs[white].losses += 1
                    elif winner is None:
                        player_perfs[white].draws += 1
                
                # Process black player if they exist
                if black_exists:
                    player_perfs[black].games += 1
                    if winner == 'black':
                        player_perfs[black].wins += 1
                    elif winner == 'white':
                        player_perfs[black].losses += 1
                    elif winner is None:
                        player_perfs[black].draws += 1
    

    print(f"Found {len(player_perfs)} players")

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            update_stats(conn, cursor, player_perfs, latest_tourney_id)

    # Sort players by score in descending order
    sorted_players = sorted(
        player_perfs.items(),
        key=lambda x: x[1].score,
        reverse=True
    )

    with open('points.tsv', 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['Username', 'Score', 'Tournaments', 'Tournament Wins', 'Tournament Win %', 'Games', 'Wins', 'Losses', 'Draws', 'Win %', 'Loss %', 'Draw %'])
        for username, perf in sorted_players:
            win_pct = f"{round((perf.wins / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
            loss_pct = f"{round((perf.losses / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
            draw_pct = f"{round((perf.draws / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
            tournament_win_pct = f"{round((perf.tournament_wins / perf.num_tournaments) * 100, 2)}%" if perf.num_tournaments > 0 else "0.00%"
            writer.writerow([
                username, perf.score, perf.num_tournaments, perf.tournament_wins, tournament_win_pct, perf.games, 
                perf.wins, perf.losses, perf.draws,
                win_pct, loss_pct, draw_pct
            ])

    print("Wrote to points.tsv")


if __name__ == "__main__":
    api_key = get_api_key()
    get_arena_tournaments(api_key)
