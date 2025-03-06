import os
import requests
from dotenv import load_dotenv
import json
import logging
from tenacity import (
    retry,
    wait_exponential,
    retry_if_exception
)

# Setup basic logging with timestamp
logging.basicConfig(
    format='%(asctime)s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)


def is_429(exception):
    """Check if the exception is a 429 Too Many Requests error"""
    return (isinstance(exception, requests.exceptions.HTTPError) and 
            exception.response.status_code == 429)


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=1200),
    retry=retry_if_exception(is_429)
)
def join_tournament(tournament_id: str, api_key: str) -> None:
    """Join a tournament with automatic retries on 429 errors only."""
    join_response = requests.post(
        f"https://lichess.org/api/tournament/{tournament_id}/join",
        headers={"Authorization": f"Bearer {api_key}"},
        data={"pairMeAsap": True}
    )
    join_response.raise_for_status()
    logging.info(f"Successfully joined {tournament_id}: {join_response.json()}")


def main():
    load_dotenv()

    tourney_creator = os.getenv("TOURNEY_CREATOR")
    api_key = os.getenv("API_KEY")

    logging.info(f"Getting tourneys created by {tourney_creator}")
    # Active and future
    # https://lichess.org/api#tag/Arena-tournaments/operation/apiUserNameTournamentCreated
    tourneys = requests.get(
        f"https://lichess.org/api/user/{tourney_creator}/tournament/created"
        f"?status=10&status=20&nb=500",
        headers={"Authorization": f"Bearer {api_key}"},
        stream=True
    )
    tourneys.raise_for_status()

    # Parse each line as a separate JSON object
    for line in tourneys.iter_lines():
        if line:
            tournament = json.loads(line)
            try:
                join_tournament(tournament['id'], api_key)
            except Exception as e:
                logging.error(f"Failed to join {tournament['id']} after all retries: {str(e)}")
                raise e


if __name__ == "__main__":
    main()
