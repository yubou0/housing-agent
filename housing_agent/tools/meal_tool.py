from __future__ import annotations

import json
import math
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()


SCORE_LABELS = {
    "budget": "預算",
    "distance": "距離",
    "speed": "速度",
    "health": "健康",
    "mood": "心情/舒適",
    "weather": "天氣",
    "preference": "飲食偏好",
    "rating": "評分",
    "group": "多人友善",
    "pet": "寵物友善",
    "payment": "付款便利",
}

HOT_KEYWORDS = ("鍋", "湯", "麵", "粥", "拉麵", "火鍋", "滷味", "ramen", "noodle", "soup")
HEALTH_CATEGORIES = {"vegan", "vegetarian", "organic"}
PROTEIN_CATEGORIES = {"steak_house", "barbecue"}


class GeoapifyMealError(RuntimeError):
    """Geoapify request failed or returned unusable data."""


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _parse_budget(text: str, default: int) -> int:
    budget_patterns = [
        r"預算\s*(\d+)",
        r"(\d+)\s*元以內",
        r"(\d+)\s*塊以內",
        r"不要超過\s*(\d+)",
        r"最多\s*(\d+)",
    ]
    for pattern in budget_patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return default


def _parse_minutes(text: str, default: int) -> int:
    if "半小時" in text:
        return 30
    if "一小時" in text or "1小時" in text or "1 小時" in text:
        return 60
    match = re.search(r"(\d+)\s*分鐘", text)
    if match:
        return int(match.group(1))
    return default


def _parse_people_count(text: str) -> int:
    match = re.search(r"(\d+)\s*(個人|人|位)", text)
    if match:
        return max(1, int(match.group(1)))
    if any(word in text for word in ("朋友", "多人", "聚餐", "一起吃")):
        return 4
    return 1


def parse_meal_request(user_request: str) -> dict[str, Any]:
    """Parse natural-language meal needs into the same context shape as the meal decision agent."""
    text = (user_request or "").strip()
    context: dict[str, Any] = {
        "raw_input": text,
        "meal_type": "lunch",
        "budget": 150,
        "available_time": 60,
        "walking_limit": 10,
        "weather": "unknown",
        "mood": "normal",
        "hunger_level": 3,
        "health_goal": "none",
        "diet_restriction": "none",
        "preference": "none",
        "people_count": 1,
        "pet_friendly_needed": False,
        "payment": "any",
        "priority": [],
    }

    context["budget"] = _parse_budget(text, context["budget"])
    context["available_time"] = _parse_minutes(text, context["available_time"])
    context["people_count"] = _parse_people_count(text)

    if any(word in text for word in ("早餐", "早上")):
        context["meal_type"] = "breakfast"
    elif any(word in text for word in ("晚餐", "晚上")):
        context["meal_type"] = "dinner"
    elif any(word in text for word in ("宵夜", "半夜")):
        context["meal_type"] = "late_night"

    if any(word in text for word in ("下雨", "雨天", "雨", "濕")):
        context["weather"] = "rainy"
        context["walking_limit"] = min(context["walking_limit"], 8)
        context["priority"].append("distance")
    elif any(word in text for word in ("很熱", "太熱", "熱爆")):
        context["weather"] = "hot"
        context["walking_limit"] = min(context["walking_limit"], 8)
        context["priority"].append("comfort")
    elif any(word in text for word in ("很冷", "太冷", "冷")):
        context["weather"] = "cold"
        context["priority"].append("hot_food")

    if any(word in text for word in ("不想走太遠", "近一點", "不要太遠", "走很少")):
        context["walking_limit"] = min(context["walking_limit"], 8)
        context["priority"].append("distance")
    if any(word in text for word in ("趕課", "有課", "快一點", "趕時間", "時間不多")):
        context["priority"].extend(["speed", "distance"])
    if context["available_time"] <= 40:
        context["priority"].extend(["speed", "distance"])

    if any(word in text for word in ("很餓", "超餓", "餓爆")):
        context["hunger_level"] = 5
        context["priority"].append("speed")
    elif "有點餓" in text:
        context["hunger_level"] = 4

    if any(word in text for word in ("健康", "清爽", "均衡")):
        context["health_goal"] = "healthy"
        context["priority"].append("health")
    if any(word in text for word in ("高蛋白", "蛋白質", "健身")):
        context["health_goal"] = "high_protein"
        context["priority"].append("health")
    if any(word in text for word in ("低油", "不要太油", "少油")):
        context["health_goal"] = "low_oil"
        context["priority"].append("health")
    if any(word in text for word in ("素食", "吃素", "蔬食")):
        context["diet_restriction"] = "vegetarian"
        context["priority"].append("health")

    if any(word in text for word in ("熱的", "熱食", "湯", "暖")):
        context["preference"] = "hot_food"
    elif any(word in text for word in ("飯", "便當")):
        context["preference"] = "rice"
    elif any(word in text for word in ("麵", "麵類")):
        context["preference"] = "noodle"

    if any(word in text for word in ("累", "疲憊", "沒力")):
        context["mood"] = "tired"
        context["priority"].append("comfort")
    if any(word in text for word in ("壓力", "焦慮", "煩")):
        context["mood"] = "stressed"
        context["priority"].append("comfort")
    if any(word in text for word in ("開心", "慶祝", "聊天")):
        context["mood"] = "happy"
        context["priority"].append("group")

    if any(word in text for word in ("寵物", "毛孩", "帶狗", "帶貓", "寵物友善")):
        context["pet_friendly_needed"] = True
        context["priority"].append("pet")
    if context["people_count"] >= 3:
        context["priority"].append("group")

    lower_text = text.lower()
    if "line pay" in lower_text or "linepay" in lower_text:
        context["payment"] = "linepay"
    elif "刷卡" in text or "信用卡" in text or "card" in lower_text:
        context["payment"] = "card"
    elif "現金" in text:
        context["payment"] = "cash"

    context["priority"] = _unique(context["priority"])
    return context


def _get_geoapify_api_key() -> str:
    return os.getenv("GEOAPIFY_API_KEY", "")


def _request_json(url: str, body: bytes | None = None, timeout: float = 10.0) -> dict[str, Any]:
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if body else "GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise GeoapifyMealError(f"Geoapify API 回傳錯誤：HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeoapifyMealError("Geoapify API 目前無法連線或回傳格式不正確。") from exc


def _food_type(categories: str) -> str:
    if "cafe" in categories:
        return "cafe"
    if "vegetarian" in categories or "vegan" in categories:
        return "vegetarian"
    if "noodle" in categories or "ramen" in categories:
        return "noodle"
    return "restaurant"


def _osm_uri(properties: dict[str, Any]) -> str:
    latitude = properties.get("lat")
    longitude = properties.get("lon")
    if latitude is None or longitude is None:
        return ""
    return f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=18/{latitude}/{longitude}"


def _straight_line_meters(origin_latitude: float, origin_longitude: float, properties: dict[str, Any]) -> int:
    latitude = math.radians(float(properties.get("lat", origin_latitude)))
    longitude = math.radians(float(properties.get("lon", origin_longitude)))
    origin_lat = math.radians(origin_latitude)
    origin_lng = math.radians(origin_longitude)
    delta_lat = latitude - origin_lat
    delta_lng = longitude - origin_lng
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(origin_lat) * math.cos(latitude) * math.sin(delta_lng / 2) ** 2
    )
    return max(1, int(6371000 * 2 * math.asin(math.sqrt(haversine))))


def _distance_values(
    latitude: float,
    longitude: float,
    properties: dict[str, Any],
    route: dict[str, Any] | None,
) -> tuple[int, int, str]:
    if route:
        meters = int(route["distance"])
        return meters, max(1, math.ceil(float(route["time"]) / 60)), "geoapify_route_matrix_walk"
    api_distance = properties.get("distance")
    if api_distance is not None:
        meters = int(api_distance)
    else:
        meters = _straight_line_meters(latitude, longitude, properties)
    return meters, max(1, math.ceil(meters / 75)), "straight_line_estimate"


def _search_geoapify_restaurants(
    latitude: float,
    longitude: float,
    radius_meters: int,
    max_results: int,
) -> dict[str, Any]:
    api_key = _get_geoapify_api_key()
    if not api_key:
        raise GeoapifyMealError("尚未設定 GEOAPIFY_API_KEY，無法查詢全台即時餐廳資料。")

    if not (20.0 <= float(latitude) <= 27.0 and 117.0 <= float(longitude) <= 123.5):
        raise GeoapifyMealError("傳入的座標不在台灣範圍內。")

    radius_meters = min(max(int(radius_meters), 100), 50000)
    max_results = min(max(int(max_results), 1), 20)
    places_payload = _request_json(
        "https://api.geoapify.com/v2/places?"
        + urlencode({
            "categories": "catering.restaurant",
            "filter": f"circle:{longitude},{latitude},{radius_meters}",
            "bias": f"proximity:{longitude},{latitude}",
            "limit": max_results,
            "lang": "zh",
            "apiKey": api_key,
        })
    )
    places = places_payload.get("features", [])

    targets = []
    for place in places:
        properties = place.get("properties", {})
        if properties.get("lon") is not None and properties.get("lat") is not None:
            targets.append({"location": [properties.get("lon"), properties.get("lat")]})

    distances: dict[int, dict[str, Any]] = {}
    if targets:
        matrix_payload = _request_json(
            "https://api.geoapify.com/v1/routematrix?" + urlencode({"apiKey": api_key}),
            json.dumps({
                "mode": "walk",
                "sources": [{"location": [longitude, latitude]}],
                "targets": targets,
            }).encode("utf-8"),
        )
        rows = matrix_payload.get("sources_to_targets", [])
        route_rows = rows[0] if rows and isinstance(rows[0], list) else rows
        distances = {
            int(row.get("target_index", index)): row
            for index, row in enumerate(route_rows)
            if row and row.get("distance") is not None and row.get("time") is not None
        }

    restaurants = []
    for index, place in enumerate(places):
        properties = place.get("properties", {})
        if properties.get("lat") is None or properties.get("lon") is None:
            continue
        categories = set(properties.get("categories", []))
        category_text = " ".join(categories).lower()
        name = properties.get("name") or properties.get("address_line1") or "未命名餐廳"
        distance_meters, walk_time, distance_source = _distance_values(
            latitude,
            longitude,
            properties,
            distances.get(index),
        )
        restaurants.append({
            "restaurant_id": properties.get("place_id", index + 1),
            "restaurant_name": name,
            "price": None,
            "price_label": "未提供",
            "price_is_estimate": False,
            "walk_time": walk_time,
            "distance_meters": distance_meters,
            "distance_source": distance_source,
            "food_type": _food_type(category_text),
            "is_hot_food": int(any(keyword in f"{name.lower()} {category_text}" for keyword in HOT_KEYWORDS)),
            "healthy_score": 8.0 if any(tag in category_text for tag in HEALTH_CATEGORIES) else 6.0,
            "protein_score": 8.0 if any(tag in category_text for tag in PROTEIN_CATEGORIES) else 6.0,
            "speed_score": 6.0,
            "comfort_score": 6.0,
            "group_friendly": 5.0,
            "pet_friendly": 5.0,
            "rating": None,
            "open_start": "00:00",
            "open_end": "23:59",
            "payment_methods": ["unknown"],
            "tags": list(categories),
            "formatted_address": properties.get("formatted", ""),
            "map_uri": _osm_uri(properties),
            "data_source": "geoapify",
        })

    return {
        "data_source": "geoapify",
        "origin": {
            "label": f"{latitude:.6f}, {longitude:.6f}",
            "latitude": latitude,
            "longitude": longitude,
        },
        "radius_meters": radius_meters,
        "restaurants": restaurants,
    }


def _filter_restaurants(restaurants: list[dict[str, Any]], user_context: dict[str, Any]) -> list[dict[str, Any]]:
    filtered = []
    for restaurant in restaurants:
        if restaurant["price"] is not None and restaurant["price"] > user_context["budget"] * 1.5:
            continue
        if restaurant["walk_time"] > user_context["walking_limit"] * 2:
            continue
        if user_context["meal_type"] != "breakfast" and restaurant["food_type"] == "breakfast":
            continue
        if user_context["meal_type"] == "breakfast" and restaurant["food_type"] not in {"breakfast", "cafe"}:
            continue
        if user_context["diet_restriction"] == "vegetarian" and restaurant["food_type"] != "vegetarian":
            continue
        filtered.append(restaurant)
    return filtered


def _budget_score(price: int | None, budget: int) -> float:
    if price is None:
        return 0.6
    if price <= budget:
        return 1.0
    over_ratio = (price - budget) / max(budget, 1)
    return max(0.0, 1.0 - over_ratio)


def _distance_score(walk_time: int, walking_limit: int, weather: str) -> float:
    if walk_time <= walking_limit:
        score = 1.0
    else:
        score = max(0.0, 1.0 - (walk_time - walking_limit) / max(walking_limit, 1))
    if weather in {"rainy", "hot"} and walk_time > walking_limit:
        score *= 0.7
    return score


def _dynamic_weights(user_context: dict[str, Any]) -> dict[str, float]:
    weights = {
        "budget": 0.17,
        "distance": 0.14,
        "speed": 0.14,
        "health": 0.10,
        "mood": 0.10,
        "weather": 0.09,
        "preference": 0.09,
        "rating": 0.07,
        "group": 0.03,
        "pet": 0.03,
        "payment": 0.04,
    }
    if user_context["available_time"] <= 40:
        weights["speed"] += 0.12
        weights["distance"] += 0.08
        weights["rating"] -= 0.03
        weights["mood"] -= 0.02
    if user_context["weather"] in {"rainy", "hot"}:
        weights["distance"] += 0.09
        weights["weather"] += 0.08
        weights["mood"] += 0.03
        weights["rating"] -= 0.03
    if user_context["health_goal"] in {"healthy", "high_protein", "low_oil"}:
        weights["health"] += 0.18
        weights["rating"] -= 0.03
        weights["preference"] -= 0.02
    if user_context["mood"] in {"tired", "stressed"}:
        weights["mood"] += 0.10
        weights["speed"] -= 0.02
    if user_context["hunger_level"] >= 5:
        weights["speed"] += 0.05
        weights["distance"] += 0.03
    if user_context["people_count"] >= 3:
        weights["group"] += 0.13
        weights["pet"] -= 0.01
    if user_context.get("pet_friendly_needed"):
        weights["pet"] += 0.15
        weights["mood"] += 0.05
        weights["speed"] -= 0.02

    weights = {key: max(0.01, value) for key, value in weights.items()}
    total = sum(weights.values())
    return {key: round(value / total, 4) for key, value in weights.items()}


def _score_restaurant(restaurant: dict[str, Any], user_context: dict[str, Any]) -> dict[str, Any]:
    weights = _dynamic_weights(user_context)
    budget_score = _budget_score(restaurant["price"], user_context["budget"])
    distance_score = _distance_score(restaurant["walk_time"], user_context["walking_limit"], user_context["weather"])
    speed_score = min(1.0, restaurant["speed_score"] / 10 + (0.08 if user_context["hunger_level"] >= 5 else 0))
    health_score = (
        restaurant["protein_score"] / 10 if user_context["health_goal"] == "high_protein"
        else restaurant["healthy_score"] / 10 if user_context["health_goal"] in {"healthy", "low_oil"}
        else 0.6
    )
    mood_score = (
        restaurant["comfort_score"] / 10 if user_context["mood"] in {"tired", "stressed"}
        else restaurant["group_friendly"] / 10 if user_context["mood"] == "happy"
        else (restaurant["rating"] / 5 if restaurant["rating"] is not None else 0.6)
    )
    weather_score = (
        0.65 * distance_score + 0.35 * (restaurant["comfort_score"] / 10)
        if user_context["weather"] == "rainy"
        else restaurant["comfort_score"] / 10 if user_context["weather"] == "hot"
        else 1.0 if user_context["weather"] == "cold" and restaurant["is_hot_food"]
        else 0.4 if user_context["weather"] == "cold"
        else 0.7
    )
    preference_score = (
        1.0 if user_context["preference"] == "hot_food" and restaurant["is_hot_food"]
        else 0.3 if user_context["preference"] == "hot_food"
        else 1.0 if user_context["preference"] == "rice" and restaurant["food_type"] in {"rice", "bento", "buffet"}
        else 1.0 if user_context["preference"] == "noodle" and restaurant["food_type"] == "noodle"
        else 0.55 if user_context["preference"] in {"rice", "noodle"}
        else 0.7
    )
    rating_score = restaurant["rating"] / 5 if restaurant["rating"] is not None else 0.6
    group_score = restaurant["group_friendly"] / 10
    pet_score = restaurant["pet_friendly"] / 10
    payment_score = 0.8 if user_context["payment"] == "any" else 0.6

    scores = {
        "budget_score": round(budget_score, 2),
        "distance_score": round(distance_score, 2),
        "speed_score": round(speed_score, 2),
        "health_score": round(health_score, 2),
        "mood_score": round(mood_score, 2),
        "weather_score": round(weather_score, 2),
        "preference_score": round(preference_score, 2),
        "rating_score": round(rating_score, 2),
        "group_score": round(group_score, 2),
        "pet_score": round(pet_score, 2),
        "payment_score": round(payment_score, 2),
    }
    final_score = sum(weights[key] * scores[f"{key}_score"] for key in weights)
    return {"restaurant": restaurant, "final_score": round(final_score, 4), "scores": scores, "weights": weights}


def _top_weight_labels(weights: dict[str, float], limit: int = 3) -> list[str]:
    ordered = sorted(weights.items(), key=lambda item: item[1], reverse=True)
    return [SCORE_LABELS.get(key, key) for key, _ in ordered[:limit]]


def _price_summary(restaurant: dict[str, Any]) -> str:
    if restaurant.get("price") is None:
        return "價位未提供"
    return f"價位約 {restaurant['price']} 元"


def _generate_explanation(recommendations: list[dict[str, Any]], user_context: dict[str, Any]) -> str:
    if not recommendations:
        return "目前找不到符合條件的餐廳，建議放寬預算、步行距離或營業時間限制。"

    top = recommendations[0]
    restaurant = top["restaurant"]
    scores = top["scores"]
    reasons: list[str] = []

    if scores["budget_score"] >= 0.9 and restaurant.get("price") is not None:
        reasons.append(f"價格約 {restaurant['price']} 元，符合你的 {user_context['budget']} 元預算")
    elif restaurant.get("price") is None:
        reasons.append("Geoapify 未提供菜單價位，價格仍需到店家頁面確認")
    if scores["distance_score"] >= 0.9:
        distance_text = f"步行約 {restaurant['walk_time']} 分鐘"
        if restaurant.get("distance_meters"):
            distance_text += f"（{restaurant['distance_meters']} 公尺）"
        reasons.append(f"{distance_text}，距離在可接受範圍內")
    if scores["speed_score"] >= 0.8:
        reasons.append("出餐速度估計較快，適合趕時間或很餓的時候")
    if user_context["preference"] == "hot_food" and restaurant["is_hot_food"]:
        reasons.append("它是熱食，符合你想吃熱的需求")
    if user_context["weather"] in {"rainy", "hot"}:
        reasons.append("天氣不方便移動，系統提高了距離與舒適度的重要性")
    if user_context["health_goal"] != "none" and scores["health_score"] >= 0.7:
        reasons.append("健康或蛋白質分數表現不錯，符合你的飲食目標")
    if user_context["people_count"] >= 3 and scores["group_score"] >= 0.7:
        reasons.append("多人友善度高，適合和朋友一起吃")
    if not reasons:
        reasons.append("它在目前條件下的整體分數最平衡")

    response = [
        f"我最推薦你去：{restaurant['restaurant_name']}",
        f"推薦分數：{top['final_score']}",
        "",
        "推薦原因：",
        *[f"- {reason}" for reason in reasons],
        "",
        "備選方案：",
    ]
    if len(recommendations) == 1:
        response.append("- 目前沒有其他明顯符合條件的備選餐廳。")
    for index, rec in enumerate(recommendations[1:], start=2):
        candidate = rec["restaurant"]
        response.append(
            f"{index}. {candidate['restaurant_name']}：{_price_summary(candidate)}，"
            f"步行 {candidate['walk_time']} 分鐘，分數 {rec['final_score']}"
        )
    response.extend([
        "",
        "本次系統主要考慮：",
        f"- 動態權重最高的因素是：{'、'.join(_top_weight_labels(top['weights']))}",
    ])
    if user_context["available_time"] <= 40:
        response.append("- 你時間有限，所以提高了出餐速度與距離的權重")
    if user_context["weather"] in {"rainy", "hot"}:
        response.append("- 天氣不方便移動，所以提高了距離與舒適度的權重")
    if user_context["health_goal"] != "none":
        response.append("- 因為你有健康需求，所以提高了健康分數的權重")
    if user_context.get("pet_friendly_needed"):
        response.append("- 因為你會帶寵物，所以提高了寵物友善的權重")
    if user_context["people_count"] >= 3:
        response.append("- 因為是多人同行，所以提高了多人友善度的權重")
    return "\n".join(response)


def recommend_restaurants_for_rental(
    user_request: str,
    latitude: float,
    longitude: float,
    radius_meters: int = 1000,
    top_k: int = 3,
) -> dict[str, Any]:
    """Recommend meals using the rent-meal-decision-agent Geoapify + multi-objective model."""
    try:
        context = parse_meal_request(user_request)
        nearby = _search_geoapify_restaurants(latitude, longitude, radius_meters, max(top_k * 3, 10))
        restaurants = _filter_restaurants(nearby["restaurants"], context)
        recommendations = [_score_restaurant(restaurant, context) for restaurant in restaurants]
        recommendations.sort(key=lambda item: item["final_score"], reverse=True)
        recommendations = recommendations[:min(max(int(top_k), 1), 5)]
        explanation = _generate_explanation(recommendations, context)
    except GeoapifyMealError as exc:
        return {
            "status": "error",
            "error_message": str(exc),
            "source": "Geoapify",
        }

    if not recommendations:
        return {
            "status": "success",
            "data": {
                "latitude": latitude,
                "longitude": longitude,
                "radius_meters": nearby["radius_meters"],
                "context": context,
                "recommendations": [],
                "explanation": explanation,
                "data_source": nearby["data_source"],
                "origin": nearby["origin"],
            },
            "source": "Geoapify",
            "message": explanation,
        }

    top = recommendations[0]["restaurant"]
    message = (
        f"我最推薦 {top['restaurant_name']}，步行約 {top['walk_time']} 分鐘"
        f"（{top['distance_meters']} 公尺）。"
    )
    return {
        "status": "success",
        "data": {
            "latitude": latitude,
            "longitude": longitude,
            "radius_meters": nearby["radius_meters"],
            "context": context,
            "recommendations": recommendations,
            "explanation": explanation,
            "data_source": nearby["data_source"],
            "origin": nearby["origin"],
        },
        "source": "Geoapify",
        "message": message,
    }
