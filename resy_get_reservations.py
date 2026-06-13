from curl_cffi import requests as curl_requests
from datetime import datetime
import json
from urllib.parse import urlencode


def run(headers, user_input):
    """Fetch all reservations for a specific date from Resy OS."""

    # Validate input
    venue_id = user_input.get("venue_id")
    if not venue_id:
        return {'status_code': 400, 'body': {'error': 'venue_id is required'}}

    date_str = user_input.get("date")
    if not date_str:
        return {'status_code': 400, 'body': {'error': 'date is required'}}

    # Convert date to year and day_of_year
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        year = str(date_obj.year)
        day_of_year = str(date_obj.timetuple().tm_yday)
    except ValueError:
        return {'status_code': 400, 'body': {'error': 'date must be in YYYY-MM-DD format'}}

    try:
        raw_data = _fetch_reservations(headers, venue_id, year, day_of_year)
    except _ApiError as e:
        return {'status_code': e.status_code, 'body': {'error': e.message}}

    # Parse the response into clean format
    reservations = []
    if isinstance(raw_data, list) and raw_data:
        rows = raw_data[0].get("data", {}).get("rows", [])
        for row in rows:
            cols = {col["header"]["name"]: col["value"] for col in row.get("cols", [])}
            reservations.append({
                "reservation_id": cols.get("Reservation_id"),
                "time": cols.get("Time"),
                "service": cols.get("service"),
                "guest": cols.get("Guest"),
                "phone": cols.get("phone"),
                "email": cols.get("Email"),
                "party_size": cols.get("Party_Size"),
                "table": cols.get("table"),
                "status": cols.get("status"),
                "vip_tag": cols.get("VIP_Tag"),
                "allergy_tags": cols.get("Allergy_Tags"),
                "guest_tags": cols.get("Guest_Tags"),
                "visit_tags": cols.get("Visit_Tags"),
                "ticket_type": cols.get("ticket_type"),
                "total_visits": cols.get("Total_Visits"),
                "last_visit": cols.get("Last_Visit"),
                "visit_note": cols.get("Visit_Note"),
                "special_requests": cols.get("Special_Requests"),
                "guest_notes": cols.get("Guest_Notes"),
            })

    return {
        'status_code': 200,
        'body': {
            'date': date_str,
            'total_count': len(reservations),
            'reservations': reservations,
        },
    }


# === PRIVATE ===

class _ApiError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message


def _fetch_reservations(headers, venue_id, year, day_of_year):
    """Authenticate for the venue and fetch reservations from the analytics API."""

    common_headers = {
        "Authorization": headers.get("Authorization", ""),
        "x-origin": headers.get("x-origin", "https://os.resy.com"),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://os.resy.com/",
    }

    # Use a session to handle Incapsula WAF cookies across requests
    session = curl_requests.Session(impersonate="chrome131")

    # Seed session with auth cookies from headers if available
    cookie = headers.get("Cookie", "")
    if cookie:
        common_headers["Cookie"] = cookie

    # Step 1: Authenticate for the venue to get analytics token
    venue_auth_resp = session.post(
        "https://auth.resy.com/1/auth/venue",
        json={"venue_id": int(venue_id)},
        headers={
            **common_headers,
            "x-resy-universal-auth": headers.get("x-resy-universal-auth", ""),
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    # Detect session expiration
    if venue_auth_resp.status_code in (401, 419):
        raise _ApiError(401, 'Session expired')

    if venue_auth_resp.status_code == 403:
        # Check if this is an Incapsula block vs. auth failure
        body_text = venue_auth_resp.text[:500]
        if "1010" in body_text or "incapsula" in body_text.lower():
            raise _ApiError(403, 'Request blocked by WAF. Cookies may need refresh.')
        raise _ApiError(401, 'Session expired')

    if venue_auth_resp.status_code != 200:
        raise _ApiError(
            venue_auth_resp.status_code,
            f'Failed to authenticate for venue: {venue_auth_resp.text[:200]}',
        )

    try:
        venue_data = venue_auth_resp.json()
    except Exception:
        raise _ApiError(401, 'Session expired - invalid response from venue auth')

    # Check if we got a valid response
    if "token" not in venue_data:
        raise _ApiError(401, 'Session expired')

    analytics_token = venue_data.get("os_tokens", {}).get("analytics")
    if not analytics_token:
        raise _ApiError(500, 'No analytics token returned from venue auth')

    # Step 2: Fetch reservations
    struct_binds = json.dumps({"year": year, "dayofyear": day_of_year})

    reservations_resp = session.post(
        "https://api.resy.com/3/analytics/report/core/Reservations",
        data=urlencode({"struct_binds": struct_binds}),
        headers={
            **common_headers,
            "x-resy-services-auth": analytics_token,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=30,
    )

    if reservations_resp.status_code in (401, 403, 419):
        raise _ApiError(401, 'Session expired')

    if reservations_resp.status_code != 200:
        raise _ApiError(
            reservations_resp.status_code,
            f'Failed to fetch reservations: {reservations_resp.text[:200]}',
        )

    try:
        return reservations_resp.json()
    except Exception:
        raise _ApiError(500, 'Invalid JSON response from reservations endpoint')
