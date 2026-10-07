"""hardware/withings.py — Withings Health API (OAuth2) for blood pressure.

Withings BPM Connect syncs BP readings to the Withings cloud.
This module handles OAuth2 token management and fetching BP measurements.

API Reference: https://developer.withings.com/api-reference
Measure types: 9 = diastolic, 10 = systolic, 11 = heart pulse
"""

import logging
import time
from typing import Optional

import requests

from config import settings

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
_MEASURE_URL = "https://wbsapi.withings.net/measure"

# Withings measure type codes
_SYSTOLIC = 10
_DIASTOLIC = 9
_PULSE = 11


def get_token(auth_code: str) -> dict:
    """Exchange an OAuth2 authorization code for access + refresh tokens.

    Returns: {access_token, refresh_token, expires_in, userid}
    """
    resp = requests.post(_TOKEN_URL, data={
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": settings.WITHINGS_CLIENT_ID,
        "client_secret": settings.WITHINGS_CLIENT_SECRET,
        "code": auth_code,
        "redirect_uri": settings.WITHINGS_REDIRECT_URI,
    }, timeout=30)
    body = resp.json().get("body", {})
    logger.info("Withings token obtained for user %s", body.get("userid"))
    return body


def refresh_token(current_refresh: str) -> dict:
    """Refresh an expired access token.

    Returns: {access_token, refresh_token, expires_in}
    """
    resp = requests.post(_TOKEN_URL, data={
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": settings.WITHINGS_CLIENT_ID,
        "client_secret": settings.WITHINGS_CLIENT_SECRET,
        "refresh_token": current_refresh,
    }, timeout=30)
    body = resp.json().get("body", {})
    logger.info("Withings token refreshed.")
    return body


def fetch_bp_reading(access_token: str, since_ts: Optional[int] = None) -> Optional[dict]:
    """Fetch the most recent blood pressure reading from Withings.

    Args:
        access_token: Valid Withings OAuth2 access token.
        since_ts:     Unix timestamp — only fetch readings after this time.
                      Defaults to 120 seconds ago.

    Returns:
        {systolic, diastolic, pulse_rate} or None if no reading found.
    """
    if since_ts is None:
        since_ts = int(time.time()) - 120

    resp = requests.post(_MEASURE_URL, data={
        "action": "getmeas",
        "meastype": f"{_SYSTOLIC},{_DIASTOLIC},{_PULSE}",
        "lastupdate": since_ts,
    }, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)

    data = resp.json()
    if data.get("status") != 0:
        logger.error("Withings API error: %s", data)
        return None

    groups = data.get("body", {}).get("measuregrps", [])
    if not groups:
        logger.info("No new BP readings from Withings since %d.", since_ts)
        return None

    # Take the most recent measurement group
    latest = groups[0]
    reading = {"systolic": None, "diastolic": None, "pulse_rate": None}
    for measure in latest.get("measures", []):
        value = measure["value"] * (10 ** measure["unit"])
        if measure["type"] == _SYSTOLIC:
            reading["systolic"] = int(value)
        elif measure["type"] == _DIASTOLIC:
            reading["diastolic"] = int(value)
        elif measure["type"] == _PULSE:
            reading["pulse_rate"] = int(value)

    logger.info("Withings BP reading: sys=%s dia=%s pulse=%s",
                reading["systolic"], reading["diastolic"], reading["pulse_rate"])
    return reading
