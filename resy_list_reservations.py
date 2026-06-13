from curl_cffi import requests
import json
import datetime
import urllib.parse


def run(headers, user_input):
    """List all reservations for the venue on a given date (defaults to today)."""
    base_url = "https://api.resy.com"

    # Determine date - default to today
    day = user_input.get("date")
    if day:
        try:
            target_date = datetime.date.fromisoformat(day)
        except ValueError:
            return {"status_code": 400, "body": {"error": "date must be in YYYY-MM-DD format"}}
    else:
        target_date = datetime.date.today()

    year = str(target_date.year)
    day_of_year = str(target_date.timetuple().tm_yday)

    # Get the services auth token
    # Priority: headers > try /1/auth/venue exchange
    services_auth = headers.get("x-resy-services-auth")

    if not services_auth:
        # Try to exchange universal auth for venue token to get services auth
        venue_id = _get_venue_id(headers)
        if venue_id:
            services_auth = _get_services_auth(headers, venue_id)

    if not services_auth:
        return {
            "status_code": 401,
            "body": {"error": "x-resy-services-auth token required. Session needs refresh."},
        }

    # Call the reservations report endpoint
    request_headers = {
        "Authorization": headers.get("Authorization", ""),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://os.resy.com",
        "Referer": "https://os.resy.com/",
        "x-origin": "https://os.resy.com",
        "x-resy-services-auth": services_auth,
    }

    body = urllib.parse.urlencode(
        {"struct_binds": json.dumps({"year": year, "dayofyear": day_of_year})}
    )

    response = requests.post(
        f"{base_url}/3/analytics/report/core/Reservations",
        headers=request_headers,
        data=body,
        impersonate="chrome131",
        timeout=30,
    )

    if response.status_code == 419:
        return {"status_code": 401, "body": {"error": "Session expired"}}

    if response.status_code != 200:
        return {
            "status_code": response.status_code,
            "body": {"error": f"API returned {response.status_code}", "detail": response.text},
        }

    data = response.json()

    # Parse the report response into clean reservation objects
    reservations = []
    if data and isinstance(data, list) and data[0].get("data", {}).get("rows"):
        for row in data[0]["data"]["rows"]:
            cols = {col["header"]["name"]: col["value"] for col in row["cols"]}
            reservation = {
                "time": cols.get("Time"),
                "service": cols.get("service"),
                "guest": cols.get("Guest"),
                "party_size": cols.get("Party_Size"),
                "status": cols.get("status"),
                "table": cols.get("table"),
                "reservation_id": cols.get("Reservation_id"),
                "vip_tag": cols.get("VIP_Tag"),
                "phone": cols.get("phone"),
                "email": cols.get("Email"),
                "allergy_tags": cols.get("Allergy_Tags"),
                "guest_tags": cols.get("Guest_Tags"),
                "visit_tags": cols.get("Visit_Tags"),
                "visit_note": cols.get("Visit_Note"),
                "special_requests": cols.get("Special_Requests"),
                "guest_notes": cols.get("Guest_Notes"),
                "total_visits": cols.get("Total_Visits"),
                "last_visit": cols.get("Last_Visit"),
                "ticket_type": cols.get("ticket_type"),
            }
            reservations.append(reservation)

    return {
        "status_code": 200,
        "body": {
            "date": target_date.isoformat(),
            "total_reservations": len(reservations),
            "reservations": reservations,
        },
    }


# === PRIVATE ===


def _get_venue_id(headers):
    """Get the first venue ID from the operator's venue list."""
    try:
        h = {
            "Authorization": headers.get("Authorization", ""),
            "Accept": "application/json, text/plain, */*",
            "x-resy-universal-auth": headers.get("x-resy-universal-auth", ""),
            "x-origin": "https://os.resy.com",
        }
        resp = requests.get(
            "https://auth.resy.com/1/venues",
            headers=h,
            impersonate="chrome131",
            timeout=15,
        )
        if resp.status_code == 200:
            venues = resp.json()
            if venues and isinstance(venues, list):
                return venues[0]["id"]
    except Exception:
        pass
    return None


def _get_services_auth(headers, venue_id):
    """Try to exchange user token for venue token to get services auth."""
    try:
        h = {
            "accept": "application/json, text/plain, */*",
            "authorization": headers.get("Authorization", ""),
            "content-type": "application/json",
            "cookie": headers.get("Cookie", ""),
            "origin": "https://os.resy.com",
            "referer": "https://os.resy.com/",
            "x-origin": "https://os.resy.com",
            "x-resy-universal-auth": headers.get("x-resy-universal-auth", ""),
        }
        resp = requests.post(
            "https://auth.resy.com/1/auth/venue",
            headers=h,
            json={"venue_id": venue_id},
            impersonate="chrome131",
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("os_tokens", {}).get("analytics")
    except Exception:
        pass
    return None
