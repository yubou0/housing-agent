import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)


def _get_place_name(place: dict) -> str:
    display_name = place.get("displayName", {})
    return display_name.get("text", "Unknown place")


def _get_place_location(place: dict) -> dict:
    location = place.get("location", {})
    return {
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
    }


def _is_taiwan_convenience_store(name: str) -> bool:
    keywords = [
        "7-eleven",
        "7-11",
        "統一超商",
        "全家",
        "familymart",
        "萊爾富",
        "hi-life",
        "ok mart",
        "ok超商",
    ]

    lower_name = name.lower()
    return any(keyword.lower() in lower_name for keyword in keywords)


def _is_24_hour_place(opening_hours: dict) -> bool:
    if not opening_hours:
        return False

    weekday_descriptions = opening_hours.get("weekdayDescriptions", [])

    for text in weekday_descriptions:
        lower_text = text.lower()

        if (
            "24 hours" in lower_text
            or "open 24 hours" in lower_text
            or "24 小時" in text
            or "24小時" in text
        ):
            return True

    periods = opening_hours.get("periods", [])

    for period in periods:
        open_time = period.get("open", {})
        close_time = period.get("close")

        if open_time and close_time is None:
            return True

    return False


def _is_late_night_place(opening_hours: dict, late_hour: int = 22) -> bool:
    if not opening_hours:
        return False

    if _is_24_hour_place(opening_hours):
        return True

    periods = opening_hours.get("periods", [])

    for period in periods:
        open_time = period.get("open", {})
        close_time = period.get("close", {})

        if not open_time or not close_time:
            continue

        open_day = open_time.get("day")
        close_day = close_time.get("day")
        close_hour = close_time.get("hour")

        if close_hour is None:
            continue

        # 跨日營業，例如 18:00 開到隔天 02:00
        if close_day is not None and open_day is not None and close_day != open_day:
            return True

        # 同一天但營業到 22:00 以後
        if close_hour >= late_hour:
            return True

    return False


def _search_google_places_nearby(
    latitude: float,
    longitude: float,
    radius_m: int,
    included_types: list[str],
    max_result_count: int = 20,
) -> dict:
    api_key = (
        os.getenv("GOOGLE_PLACES_API_KEY")
        or os.getenv("GOOGLE_MAPS_API_KEY")
    )

    if api_key:
        api_key = api_key.strip().strip('"').strip("'")

    print("[NightLife Debug] GOOGLE_PLACES_API_KEY repr:", repr(api_key[:12] if api_key else None))
    print("[NightLife Debug] key has non-ascii:", any(ord(c) > 127 for c in api_key) if api_key else None)

    if not api_key:
        return {
            "status": "error",
            "error_message": "Google Places API key is not set.",
        }

    url = "https://places.googleapis.com/v1/places:searchNearby"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,"
            "places.displayName,"
            "places.formattedAddress,"
            "places.location,"
            "places.types,"
            "places.googleMapsUri,"
            "places.businessStatus,"
            "places.currentOpeningHours,"
            "places.regularOpeningHours,"
            "places.delivery,"
            "places.takeout"
        ),
    }

    payload = {
        "includedTypes": included_types,
        "maxResultCount": max_result_count,
        "languageCode": "zh-TW",
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": float(radius_m),
            }
        },
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()

        return {
            "status": "success",
            "places": response.json().get("places", []),
        }

    except requests.exceptions.RequestException as e:
        status_code = None
        response_text = ""

        if e.response is not None:
            status_code = e.response.status_code
            response_text = e.response.text

        return {
            "status": "error",
            "error_message": (
                f"Google Places API request failed: {str(e)}; "
                f"status_code={status_code}; response_text={response_text[:300]}"
            ),
        }


def calculate_night_life_score(
    convenience_store_count: int,
    late_night_restaurant_count: int,
    late_night_cafe_count: int,
    twenty_four_hour_count: int,
    delivery_count: int,
    takeout_count: int,
) -> dict:
    score = 0
    reasons = []

    if convenience_store_count >= 5:
        score += 30
        reasons.append("500 公尺內主要超商數量充足，深夜採買非常方便。")
    elif convenience_store_count >= 3:
        score += 22
        reasons.append("500 公尺內有多間主要超商，基本夜間生活機能良好。")
    elif convenience_store_count >= 1:
        score += 12
        reasons.append("附近有主要超商，但密度不算高。")
    else:
        reasons.append("附近主要超商較少，深夜採買可能較不方便。")

    if late_night_restaurant_count >= 8:
        score += 25
        reasons.append("深夜餐廳選擇多，適合晚下課或晚下班後用餐。")
    elif late_night_restaurant_count >= 4:
        score += 18
        reasons.append("深夜仍有一些餐廳可選。")
    elif late_night_restaurant_count >= 1:
        score += 8
        reasons.append("深夜餐廳選擇有限。")
    else:
        reasons.append("深夜餐廳選擇很少。")

    if late_night_cafe_count >= 3:
        score += 10
        reasons.append("附近有多間深夜咖啡廳，適合讀書或工作。")
    elif late_night_cafe_count >= 1:
        score += 5
        reasons.append("附近有少量深夜咖啡廳。")

    if twenty_four_hour_count >= 3:
        score += 15
        reasons.append("有多間 24 小時店家，夜間機能佳。")
    elif twenty_four_hour_count >= 1:
        score += 8
        reasons.append("至少有 24 小時店家可使用。")

    delivery_takeout_score = min(20, delivery_count * 2 + takeout_count)
    score += delivery_takeout_score

    if delivery_takeout_score >= 15:
        reasons.append("外送與外帶支援度高。")
    elif delivery_takeout_score >= 8:
        reasons.append("外送與外帶支援度普通。")
    else:
        reasons.append("外送與外帶資訊較少或支援度有限。")

    score = min(score, 100)

    if score >= 80:
        level = "夜貓生活機能極佳"
    elif score >= 60:
        level = "夜貓生活機能良好"
    elif score >= 40:
        level = "夜貓生活機能普通"
    else:
        level = "夜貓生活機能偏弱"

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
    }


def analyze_late_night_living_index(
    latitude: float,
    longitude: float,
    radius_m: int = 500,
) -> dict:
    """
    分析指定座標附近的夜貓生活機能。

    Args:
        latitude: 緯度
        longitude: 經度
        radius_m: 搜尋半徑，預設 500 公尺

    Returns:
        dict: 夜貓生活指數、深夜店家、24 小時店家、外送外帶資訊
    """
    radius_m = min(max(int(radius_m), 300), 1500)

    search_type_groups = [
        ["convenience_store"],
        ["restaurant"],
        ["cafe"],
        ["meal_takeaway"],
    ]

    all_places = {}
    errors = []

    for included_types in search_type_groups:
        result = _search_google_places_nearby(
            latitude=latitude,
            longitude=longitude,
            radius_m=radius_m,
            included_types=included_types,
        )

        if result["status"] != "success":
            errors.append(result["error_message"])
            continue

        for place in result.get("places", []):
            place_id = place.get("id")
            if place_id:
                all_places[place_id] = place

    if not all_places and errors:
        return {
            "status": "error",
            "error_message": errors[0],
            "source": "Google Places API",
        }

    convenience_stores = []
    taiwan_convenience_stores = []
    restaurants = []
    cafes = []
    takeaway_places = []

    late_night_restaurants = []
    late_night_cafes = []
    twenty_four_hour_places = []
    delivery_places = []
    takeout_places = []

    place_summaries = []

    for place in all_places.values():
        name = _get_place_name(place)
        types = place.get("types", [])
        regular_opening_hours = place.get("regularOpeningHours", {})
        current_opening_hours = place.get("currentOpeningHours", {})
        opening_hours = regular_opening_hours or current_opening_hours

        is_late_night = _is_late_night_place(opening_hours)
        is_24_hour = _is_24_hour_place(opening_hours)

        if "convenience_store" in types:
            convenience_stores.append(place)

            if _is_taiwan_convenience_store(name):
                taiwan_convenience_stores.append(place)

        if "restaurant" in types or "meal_takeaway" in types:
            restaurants.append(place)

            if is_late_night:
                late_night_restaurants.append(place)

        if "cafe" in types:
            cafes.append(place)

            if is_late_night:
                late_night_cafes.append(place)

        if "meal_takeaway" in types:
            takeaway_places.append(place)

        if is_24_hour:
            twenty_four_hour_places.append(place)

        if place.get("delivery") is True:
            delivery_places.append(place)

        if place.get("takeout") is True:
            takeout_places.append(place)

        location = _get_place_location(place)

        place_summaries.append({
            "name": name,
            "types": types,
            "address": place.get("formattedAddress"),
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "google_maps_url": place.get("googleMapsUri"),
            "open_now": current_opening_hours.get("openNow"),
            "is_late_night": is_late_night,
            "is_24_hour": is_24_hour,
            "delivery": place.get("delivery"),
            "takeout": place.get("takeout"),
        })

    score_result = calculate_night_life_score(
        convenience_store_count=len(taiwan_convenience_stores),
        late_night_restaurant_count=len(late_night_restaurants),
        late_night_cafe_count=len(late_night_cafes),
        twenty_four_hour_count=len(twenty_four_hour_places),
        delivery_count=len(delivery_places),
        takeout_count=len(takeout_places),
    )

    important_places = [
        place for place in place_summaries
        if place["is_late_night"] or place["is_24_hour"]
    ][:5]

    if not important_places:
        important_places = place_summaries[:5]

    counts = {
        "all_places": len(all_places),
        "convenience_stores": len(convenience_stores),
        "taiwan_major_convenience_stores": len(taiwan_convenience_stores),
        "restaurants": len(restaurants),
        "cafes": len(cafes),
        "takeaway_places": len(takeaway_places),
        "late_night_restaurants": len(late_night_restaurants),
        "late_night_cafes": len(late_night_cafes),
        "twenty_four_hour_places": len(twenty_four_hour_places),
        "delivery_supported_places": len(delivery_places),
        "takeout_supported_places": len(takeout_places),
    }

    message = (
        f"附近 {radius_m} 公尺內夜貓生活指數為 {score_result['score']} / 100，"
        f"等級為「{score_result['level']}」。"
        f"主要超商 {counts['taiwan_major_convenience_stores']} 間，"
        f"深夜餐廳 {counts['late_night_restaurants']} 間，"
        f"24 小時店家 {counts['twenty_four_hour_places']} 間。"
    )

    return {
        "status": "success",
        "data": {
            "latitude": latitude,
            "longitude": longitude,
            "radius_m": radius_m,
            "score": score_result["score"],
            "level": score_result["level"],
            "reasons": score_result["reasons"],
            "counts": counts,
            "important_places": important_places,
        },
        "source": "Google Places API",
        "message": message,
    }