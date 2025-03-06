import os
import requests
from dotenv import load_dotenv
import json


def main():
    load_dotenv()

    tourney_creator = os.getenv("TOURNEY_CREATOR")
    api_key = os.getenv("API_KEY")

    print(f"Getting tourneys created by {tourney_creator}")
    # Active and future
    # https://lichess.org/api#tag/Arena-tournaments/operation/apiUserNameTournamentCreated
    tourneys = requests.get(f"https://lichess.org/api/user/{tourney_creator}/tournament/created?status=10&status=20",
                            headers={"Authorization": f"Bearer {api_key}"},
                            stream=True)

    # Parse each line as a separate JSON object
    for line in tourneys.iter_lines():
        if line:
            tournament = json.loads(line)
            requests.post(f"https://lichess.org/api/tournament/{tournament['id']}/join",
                          headers={"Authorization": f"Bearer {api_key}"},
                          data={"pairMeAsap": True})
            print(f"Joined {tournament['id']}")


if __name__ == "__main__":
    main()
