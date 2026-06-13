import json
from datetime import date, datetime, timezone, timedelta
from urllib.parse import quote
from curl_cffi import requests


def run(headers, user_input):
    """Get today's reservations list with guest names, times, party sizes, and statuses."""
    auth_url = "https://auth.resy.com"
    api_url = "https://api.resy.com"

    cookie = headers.get("Cookie", "")
    authorization = headers.get("Authorization", "")
    x_origin = headers.get("x-origin", "https://os.resy.com")
    user_token = headers.get("x-resy-universal-auth", "")

    base_headers = {
        "Authorization": authorization,
        "X-Resy-Universal-Auth": user_token,
        "X-Origin": x_origin,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://os.resy.com/",
        "Origin": "https://os.resy.com",
        "Cookie": cookie,
    }

    # Auto-detect venue_id if not provided
    venue_id = user_input.get("venue_id")
    if not venue_id:
        venue_id = _get_first_venue_id(auth_url, base_headers)
        if not venue_id:
            return {"status_code": 401, "body": {"error": "Session expired - could not detect venue"}}

    # Default date to today in venue's timezone (Eastern Time)
    target_date_str = user_input.get("date")
    if target_date_str:
        # Parse YYYY-MM-DD to get year and day of year
        parts = target_date_str.split("-")
        target_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
    else:
        # Use Eastern Time (UTC-4 EDT / UTC-5 EST) for "today" since venue is EST5EDT
        eastern = timezone(timedelta(hours=-4))
        target_date = datetime.now(eastern).date()

    year = target_date.year
    day_of_year = target_date.timetuple().tm_yday

    # Get venue-scoped token and analytics token
    venue_data = _get_venue_auth(auth_url, authorization, user_token, x_origin, cookie, int(venue_id))
    if not venue_data:
        return {"status_code": 401, "body": {"error": "Session expired - could not obtain venue token"}}

    analytics_token = venue_data.get("analytics_token", "")
    if not analytics_token:
        return {"status_code": 401, "body": {"error": "No analytics token available"}}

    # Fetch reservations
    struct_binds = json.dumps({"year": str(year), "dayofyear": str(day_of_year)})
    form_body = f"struct_binds={quote(struct_binds)}"

    response = requests.post(
        f"{api_url}/3/analytics/report/core/Reservations",
        data=form_body,
        headers={
            "Authorization": authorization,
            "X-Resy-Services-Auth": analytics_token,
            "X-Origin": x_origin,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://os.resy.com/",
            "Origin": "https://os.resy.com",
            "Cookie": cookie,
        },
        impersonate="chrome131",
        timeout=30,
    )

    if response.status_code in (401, 419):
        return {"status_code": 401, "body": {"error": "Session expired"}}

    if response.status_code != 200:
        try:
            return {"status_code": response.status_code, "body": response.json()}
        except Exception:
            return {"status_code": response.status_code, "body": {"error": response.text[:200]}}

    try:
        raw_data = response.json()
    except Exception:
        return {"status_code": 500, "body": {"error": "Invalid JSON response"}}

    # Parse the raw analytics format into a clean list
    reservations = _parse_reservations(raw_data)

    return {
        "status_code": 200,
        "body": {
            "date": target_date.isoformat(),
            "total": len(reservations),
            "reservations": reservations,
        },
    }


# === PRIVATE ===

def _parse_reservations(raw_data):
    """Parse the analytics response into a clean reservations list."""
    reservations = []

    if not raw_data or not isinstance(raw_data, list) or len(raw_data) == 0:
        return reservations

    report = raw_data[0]
    rows = report.get("data", {}).get("rows", [])

    # Known field name mappings (analytics header name -> output key)
    field_map = {
        "Time": "time",
        "service": "service",
        "Guest": "guest",
        "Party_Size": "party_size",
        "table": "table",
        "status": "status",
        "phone": "phone",
        "Email": "email",
        "VIP_Tag": "vip_tag",
        "Visit_Tags": "visit_tags",
        "Allergy_Tags": "allergy_tags",
        "Guest_Tags": "guest_tags",
        "Total_Visits": "total_visits",
        "Visit_Note": "visit_note",
        "Special_Requests": "special_requests",
        "Guest_Notes": "guest_notes",
        "Reservation_id": "reservation_id",
        "ticket_type": "ticket_type",
    }

    for row in rows:
        cols = row.get("cols", [])
        entry = {}
        for col in cols:
            name = col.get("header", {}).get("name", "")
            value = col.get("value")
            if name in field_map:
                entry[field_map[name]] = value
            elif name:
                # Capture any additional fields not in the known map
                entry[name.lower()] = value

        if entry:
            reservations.append(entry)

    return reservations


def _get_first_venue_id(auth_url, base_headers):
    """Auto-detect the first venue ID for the user."""
    resp = requests.get(
        f"{auth_url}/1/venues",
        headers=base_headers,
        impersonate="chrome131",
        timeout=30,
    )
    if resp.status_code == 200:
        try:
            venues = resp.json()
            if venues and len(venues) > 0:
                return venues[0].get("id")
        except Exception:
            pass
    return None


def _get_venue_auth(auth_url, authorization, user_token, x_origin, cookie, venue_id):
    """Get venue token and analytics token."""
    # Go directly to venue auth with the token from headers.
    # The backend provides fresh tokens - no need to refresh first.
    # Refreshing requires the x-resy-rest-refresh cookie which expires
    # and causes 404 errors when it does.
    venue_resp = requests.post(
        f"{auth_url}/1/auth/venue",
        json={"venue_id": venue_id},
        headers={
            "Authorization": authorization,
            "X-Resy-Universal-Auth": user_token,
            "X-Origin": x_origin,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://os.resy.com/",
            "Origin": "https://os.resy.com",
            "Cookie": cookie,
        },
        impersonate="chrome131",
        timeout=30,
    )

    if venue_resp.status_code != 200:
        return None

    try:
        vd = venue_resp.json()
        venue_token = vd.get("token")
        os_tokens = vd.get("os_tokens", {})
        analytics_token = os_tokens.get("analytics", "")
        return {
            "venue_token": venue_token,
            "analytics_token": analytics_token,
        }
    except Exception:
        return None
