import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
from dataclasses import dataclass
import psycopg

from googleapiclient.discovery import build  # type: ignore
from google.auth import default

# flake8: noqa: E501

NUM_TOURNAMENTS = 1000000
WRITE_ONLY = False
SPREADSHEET_ID = "12aZszJiwVvh5RBggnbpuy4ePliJ9aJS9cCX-7UJgcX8"
SHEET_NAME = "points"
LATEST_TOURNEY_SHEET = "latest tourney processed"  # Sheet name with spaces to match Google Sheets

"""This script finds all darkonteams Hourly Ultrabullet tournaments and calculates the total points and games for each player, writing to Google Sheets."""

@dataclass
class PlayerPerf:
    score: int
    highest_tourney_score: int
    highest_tourney_url: str
    games: int
    num_tournaments: int
    tournament_wins: int
    wins: int
    losses: int
    draws: int

@dataclass
class Tourney:
    id: str
    finishes_at: str

def milliseconds_to_utc_string(ms_timestamp: int) -> str:
    """Convert a millisecond timestamp to UTC time string in ISO format."""
    # Convert milliseconds to seconds
    seconds = ms_timestamp / 1000
    # Create datetime object in UTC
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    # Format as ISO string
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ').replace('Z', ' UTC')

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

def get_latest_tourney(cursor: psycopg.Cursor) -> Tourney:
    """Get the ID of the latest processed tournament from the database."""
    cursor.execute("SELECT id, finishes_at FROM latest_tourney LIMIT 1")
    result = cursor.fetchone()
    if result is None:
        raise ValueError("No latest tournament ID found in database")
    return Tourney(id=result[0], finishes_at=result[1])

def get_prior_stats(cursor: psycopg.Cursor) -> dict[str, PlayerPerf]:
    """Get the prior stats for each player from the database."""
    cursor.execute("SELECT username, score, highest_tourney_score, highest_tourney_url, games, num_tournaments, tournament_wins, wins, losses, draws FROM tourney_stats")
    result = cursor.fetchall()
    return {row[0]: PlayerPerf(*row[1:]) for row in result}

def update_stats(conn: psycopg.Connection, cursor: psycopg.Cursor, player_perfs: dict[str, PlayerPerf], latest_tourney: Tourney) -> None:
    """
    Update player statistics and latest tournament ID in a single transaction.
    Truncates the tourney_stats table and rewrites all stats.
    """
    # Truncate the tourney_stats table
    cursor.execute("TRUNCATE TABLE tourney_stats")
    
    # Batch insert all player stats
    player_data = [(username, perf.score, perf.highest_tourney_score, perf.highest_tourney_url, perf.games, perf.num_tournaments, 
                    perf.tournament_wins, perf.wins, perf.losses, perf.draws) 
                   for username, perf in player_perfs.items()]

    cursor.executemany(
        "INSERT INTO tourney_stats (username, score, highest_tourney_score, highest_tourney_url, games, num_tournaments, tournament_wins, wins, losses, draws) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        player_data
    )
    
    # Update the latest tournament ID
    cursor.execute("UPDATE latest_tourney SET id = %s, finishes_at = %s", (latest_tourney.id, latest_tourney.finishes_at))
    
    conn.commit()
    
    print(f"Updated stats for {len(player_perfs)} players and set latest tournament ID to {latest_tourney.id}")

def write_to_sheets(player_perfs: dict[str, PlayerPerf], latest_tourney: Tourney) -> None:
    """Write player stats to Google Sheets."""
    # Sort players by score in descending order
    sorted_players = sorted(
        player_perfs.items(),
        key=lambda x: x[1].score,
        reverse=True
    )
    
    # Prepare the data for Google Sheets
    header = ['Username', 'Score', 'Highest Tourney Score', 'Highest Tourney Score URL', 'Tournaments', 'Tournament Wins', 'Tournament Win %', 'Games', 'Wins', 'Losses', 'Draws', 'Win %', 'Loss %', 'Draw %']
    rows = [header]
    
    for username, perf in sorted_players:
        win_pct = f"{round((perf.wins / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
        loss_pct = f"{round((perf.losses / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
        draw_pct = f"{round((perf.draws / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
        tournament_win_pct = f"{round((perf.tournament_wins / perf.num_tournaments) * 100, 2)}%" if perf.num_tournaments > 0 else "0.00%"
        
        rows.append([
            username, str(perf.score), str(perf.highest_tourney_score), str(perf.highest_tourney_url),
            str(perf.num_tournaments), str(perf.tournament_wins), tournament_win_pct, str(perf.games), 
            str(perf.wins), str(perf.losses), str(perf.draws),
            win_pct, loss_pct, draw_pct
        ])
    
    # Load service account credentials
    # When running in Cloud Functions, use default credentials
    creds, _ = default()
    
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    
    # No longer clear the main sheet - this preserves formatting
    # Instead, just update the values directly
    
    # Write new data
    sheet.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": rows}
    ).execute()
    
    tourney_url = f"https://lichess.org/tournament/{latest_tourney.id}"
    sheet.values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{LATEST_TOURNEY_SHEET}!A1:Z10",
    ).execute()
    
    # Use the HYPERLINK formula to make it clickable and include the time
    hyperlink_formula = f'=HYPERLINK("{tourney_url}", "{tourney_url}")'
    sheet.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{LATEST_TOURNEY_SHEET}!A1:B1",
        valueInputOption="USER_ENTERED",
        body={"values": [
            [hyperlink_formula, f"Tournament ended: {latest_tourney.finishes_at}"]
        ]}
    ).execute()
    
    print(f"Successfully wrote {len(rows)-1} players to Google Sheet")

def get_arena_tournaments() -> None:
    if WRITE_ONLY:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                player_perfs = get_prior_stats(cursor)
                latest_tourney = get_latest_tourney(cursor)
        write_to_sheets(player_perfs, latest_tourney)
        return
    
    api_key = get_api_key()

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            old_latest_tourney = get_latest_tourney(cursor)
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

    tourneys: list[Tourney] = []

    for line in response.iter_lines():
        if line:
            tourney_data = json.loads(line)
            tourney_id = tourney_data['id']
            if tourney_id == old_latest_tourney.id:
                break
            tourneys.append(Tourney(id=tourney_id, finishes_at=milliseconds_to_utc_string(tourney_data['finishesAt'])))

    if not tourneys:
        print("No new tournaments found")
        return

    print(f"Found {len(tourneys)} tournaments")

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            player_perfs = get_prior_stats(cursor)

    for i, tourney in enumerate(tourneys):
        print(f"Processing tournament {i+1} of {len(tourneys)}")
        url = f"https://lichess.org/api/tournament/{tourney.id}/results?nb=1000"
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
                    player_perfs[username] = PlayerPerf(score=0, highest_tourney_score=0, highest_tourney_url="", games=0, num_tournaments=0, tournament_wins=0, wins=0, losses=0, draws=0)
                player_perfs[username].score += result['score']
                player_perfs[username].num_tournaments += 1
                if result['rank'] == 1:
                    player_perfs[username].tournament_wins += 1
                if result['score'] > player_perfs[username].highest_tourney_score:
                    player_perfs[username].highest_tourney_score = result['score']
                    player_perfs[username].highest_tourney_url = f"https://lichess.org/tournament/{tourney.id}"

        games_url = f"https://lichess.org/api/tournament/{tourney.id}/games?moves=false&tags=false"
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
 
    new_latest_tourney = tourneys[0]

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            update_stats(conn, cursor, player_perfs, new_latest_tourney)

    write_to_sheets(player_perfs, new_latest_tourney)


def run(event, context) -> None:
    get_arena_tournaments()
