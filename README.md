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

## Run

`python main.py`
