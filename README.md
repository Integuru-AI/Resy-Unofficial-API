# Resy Unofficial API

Unofficial Python integrations for Resy.

## Integrations

- `resy_get_reservations.py` - `get_reservations`.
- `resy_list_reservations.py` - `list_reservations`.
- `resy_list_venues.py` - `list_venues`.
- `resy_resy_reservations.py` - `resy_reservations`.

## Usage

Each file exposes a `run(input, context)` or `run(headers, input)` style entrypoint, matching the source integration runtime.
Authenticated request headers/cookies are expected to be supplied by the caller when required.

Install dependencies:

```bash
pip install -r requirements.txt
```

## Info

This unofficial API is built by [Integuru.ai](https://integuru.ai/).

For custom requests or hosted authentication, contact richard@taiki.online.

See the [complete list of APIs by Integuru](https://github.com/Integuru-AI/APIs-by-Integuru).
