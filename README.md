# Lichess Tourney Joiner

This is a script that can be used to join many tournaments.

## Setup

1. Create virtual environment

```bash
python -m venv venv
```

2. Activate virtual environment

```bash
source venv/bin/activate
```

3. Install dependencies

```bash
pip install -r requirements.txt
```

## Parameters

You need to make a [Lichess Personal Access Token](https://lichess.org/api#section/Introduction/Authentication) with the `Create, update, and join tournaments (tournament:write)` scope.

```bash
cp .env.example .env
```

Set `TOURNEY_CREATOR` and `API_KEY` in `.env` as appropriate

- `TOURNEY_CREATOR`: Find all future and current tourneys created by this user (doesn't have to be you)
- `API_KEY`: The PAT you created above

## Run

`python main.py`

## Tournament creator

`creator.py` is a quick utility used to create recurring tournaments. It's very specific to DarkOnTeams but it could be a good reference maybe.
