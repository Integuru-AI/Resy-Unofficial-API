from curl_cffi import requests as curl_requests


def run(headers, user_input):
    """List all venues the authenticated user has access to in Resy OS."""

    try:
        status_code, text, json_data = _call_api(headers)
    except Exception as e:
        return {'status_code': 500, 'body': {'error': str(e)}}

    if status_code in (401, 419):
        return {'status_code': 401, 'body': {'error': 'Session expired'}}

    if status_code == 403:
        body_text = text[:500]
        if "1010" in body_text or "incapsula" in body_text.lower():
            return {'status_code': 403, 'body': {'error': 'Request blocked by WAF. Cookies may need refresh.'}}
        return {'status_code': 401, 'body': {'error': 'Session expired'}}

    if status_code != 200:
        return {
            'status_code': status_code,
            'body': {'error': f'Failed to fetch venues: {text[:200]}'},
        }

    if json_data is None:
        return {'status_code': 401, 'body': {'error': 'Session expired - invalid response'}}

    if not isinstance(json_data, list):
        return {'status_code': 401, 'body': {'error': 'Session expired'}}

    venues = []
    for venue in json_data:
        location = venue.get("location", {})
        venues.append({
            "venue_id": venue.get("id"),
            "name": venue.get("name"),
            "slug": venue.get("slug"),
            "location_code": location.get("code"),
            "location_name": location.get("name"),
        })

    return {
        'status_code': 200,
        'body': {
            'total_count': len(venues),
            'venues': venues,
        },
    }


# === PRIVATE ===

def _call_api(headers):
    """Fetch the list of venues from the API.

    Returns (status_code, response_text, parsed_json_or_None).
    """

    common_headers = {
        "Authorization": headers.get("Authorization", ""),
        "x-resy-universal-auth": headers.get("x-resy-universal-auth", ""),
        "x-origin": headers.get("x-origin", "https://os.resy.com"),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://os.resy.com/",
    }

    cookie = headers.get("Cookie", "")
    if cookie:
        common_headers["Cookie"] = cookie

    session = curl_requests.Session(impersonate="chrome131")

    resp = session.get(
        "https://auth.resy.com/1/venues",
        headers=common_headers,
        timeout=30,
    )

    try:
        json_data = resp.json()
    except Exception:
        json_data = None

    return resp.status_code, resp.text, json_data
