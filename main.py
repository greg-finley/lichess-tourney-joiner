import os
import requests
from dotenv import load_dotenv
import json
from time import sleep


def main():
    load_dotenv()

    tourney_creator = os.getenv("TOURNEY_CREATOR")
    api_key = os.getenv("API_KEY")

    print(f"Getting tourneys created by {tourney_creator}")
    # Active and future
    # https://lichess.org/api#tag/Arena-tournaments/operation/apiUserNameTournamentCreated
    tourneys = requests.get(f"https://lichess.org/api/user/{tourney_creator}/tournament/created?status=10&status=20&nb=500",
                            headers={"Authorization": f"Bearer {api_key}"},
                            stream=True)
    tourneys.raise_for_status()

    # Parse each line as a separate JSON object
    for line in tourneys.iter_lines():
        if line:
            tournament = json.loads(line)
            sleep(1)
            join_response = requests.post(f"https://lichess.org/api/tournament/{tournament['id']}/join",
                                          headers={"Authorization": f"Bearer {api_key}"},
                                          data={"pairMeAsap": True})
            join_response.raise_for_status()
            print(f"Joined {tournament['id']}: {join_response.json()}")


if __name__ == "__main__":
    main()
