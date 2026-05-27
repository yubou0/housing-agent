#文字地點-->經緯度
import os
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def geocode_location(place: str, country_codes: Optional[str] = "tw") -> dict:
    """
    將使用者輸入的地點、地址或區域名稱轉換為經緯度。

    Args:
        place: 地點名稱，例如「台北車站」、「中央大學」、「中壢火車站」
        country_codes: 預設限制台灣，使用 "tw"

    Returns:
        dict: 包含 latitude、longitude、display_name 等欄位
    """
    if not place or not place.strip():
        return {
            "status": "error",
            "error_message": "Place name is empty.",
            "source": "OpenStreetMap Nominatim",
        }

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": place.strip(),
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 1,
        "accept-language": "zh-TW",
    }

    if country_codes:
        params["countrycodes"] = country_codes.lower()

    headers = {
        "User-Agent": os.getenv(
            "NOMINATIM_USER_AGENT",
            "housing-area-insight-agent/1.0"
        )
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()

        if not data:
            return {
                "status": "error",
                "error_message": f"No geocoding result found for '{place}'.",
                "source": "OpenStreetMap Nominatim",
            }

        best_match = data[0]

        return {
            "status": "success",
            "place": place,
            "latitude": float(best_match["lat"]),
            "longitude": float(best_match["lon"]),
            "display_name": best_match.get("display_name", ""),
            "address": best_match.get("address", {}),
            "class": best_match.get("class", ""),
            "type": best_match.get("type", ""),
            "source": "OpenStreetMap Nominatim",
        }

    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "error_message": f"Geocoding request failed: {str(e)}",
            "source": "OpenStreetMap Nominatim",
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Unexpected geocoding error: {str(e)}",
            "source": "OpenStreetMap Nominatim",
        }