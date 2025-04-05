import requests
import json
import os
from dotenv import load_dotenv
from dataclasses import dataclass
import psycopg

# type: ignore
from googleapiclient.discovery import build  # type: ignore
from google.oauth2 import service_account  # type: ignore

# flake8: noqa: E501

NUM_TOURNAMENTS = 1000000
WRITE_ONLY = True
SPREADSHEET_ID = "12aZszJiwVvh5RBggnbpuy4ePliJ9aJS9cCX-7UJgcX8"
SHEET_NAME = "points"
LATEST_TOURNEY_SHEET = "latest tourney processed"  # Sheet name with spaces to match Google Sheets

"""This script finds all darkonteams Hourly Ultrabullet tournaments and calculates the total points and games for each player, writing to Google Sheets."""

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

def write_to_sheets(player_perfs: dict[str, PlayerPerf], latest_tourney_id: str) -> None:
    """Write player stats to Google Sheets."""
    # Sort players by score in descending order
    sorted_players = sorted(
        player_perfs.items(),
        key=lambda x: x[1].score,
        reverse=True
    )
    
    # Prepare the data for Google Sheets
    header = ['Username', 'Score', 'Tournaments', 'Tournament Wins', 'Tournament Win %', 'Games', 'Wins', 'Losses', 'Draws', 'Win %', 'Loss %', 'Draw %']
    rows = [header]
    
    for username, perf in sorted_players:
        win_pct = f"{round((perf.wins / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
        loss_pct = f"{round((perf.losses / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
        draw_pct = f"{round((perf.draws / perf.games) * 100, 2)}%" if perf.games > 0 else "0.00%"
        tournament_win_pct = f"{round((perf.tournament_wins / perf.num_tournaments) * 100, 2)}%" if perf.num_tournaments > 0 else "0.00%"
        
        rows.append([
            username, str(perf.score), str(perf.num_tournaments), str(perf.tournament_wins), tournament_win_pct, str(perf.games), 
            str(perf.wins), str(perf.losses), str(perf.draws),
            win_pct, loss_pct, draw_pct
        ])
    
    # Set up Google Sheets API
    try:
        # Load service account credentials
        # The credentials.json file should be in the same directory as this script
        creds = service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        
        service = build('sheets', 'v4', credentials=creds)
        sheet = service.spreadsheets()
        
        # Clear existing data
        sheet.values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A1:Z1000",
        ).execute()
        
        # Write new data
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": rows}
        ).execute()
        
        tourney_url = f"https://lichess.org/tournament/{latest_tourney_id}"
        sheet.values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{LATEST_TOURNEY_SHEET}!A1:Z10",
        ).execute()
        
        # Use the HYPERLINK formula to make it clickable
        hyperlink_formula = f'=HYPERLINK("{tourney_url}", "{tourney_url}")'
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{LATEST_TOURNEY_SHEET}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [[hyperlink_formula]]}
        ).execute()
        
        print(f"Successfully wrote {len(rows)-1} players to Google Sheet")
    
    except Exception as e:
        print(f"Error writing to Google Sheets: {e}")

def get_arena_tournaments() -> None:
    if WRITE_ONLY:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                player_perfs = get_prior_stats(cursor)
                latest_tourney_id = get_latest_tourney_id(cursor)
        write_to_sheets(player_perfs, latest_tourney_id)
        return
    
    api_key = get_api_key()

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            old_latest_tourney_id = get_latest_tourney_id(cursor)
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
            if tourney_id == old_latest_tourney_id:
                break
            tourney_ids.append(tourney_id)

    if not tourney_ids:
        print("No new tournaments found")
        return

    print(f"Found {len(tourney_ids)} tournaments")

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            player_perfs = get_prior_stats(cursor)

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

    new_latest_tourney_id = tourney_ids[0]

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            update_stats(conn, cursor, player_perfs, new_latest_tourney_id)

    write_to_sheets(player_perfs, new_latest_tourney_id)


if __name__ == "__main__":
    get_arena_tournaments()
