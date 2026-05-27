#附近設施

import math
import requests


FACILITY_LABELS = {
    "convenience_store": "超商",
    "hospital": "醫院",
    "clinic": "診所",
    "pharmacy": "藥局",
    "park": "公園",
    "bike_rental": "YouBike / 自行車租借站",
    "parking": "停車場",
    "mall": "商場 / 百貨",
    "supermarket": "超市",
}


def calculate_distance_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> int:
    earth_radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return round(earth_radius * c)


def build_address(tags: dict) -> str:
    parts = [
        tags.get("addr:city"),
        tags.get("addr:district"),
        tags.get("addr:suburb"),
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
    ]
    address = "".join(part for part in parts if part)
    return address or "OSM 未提供完整地址"


def get_item_coordinate(item: dict) -> tuple[float | None, float | None]:
    if "lat" in item and "lon" in item:
        return item["lat"], item["lon"]

    center = item.get("center", {})
    return center.get("lat"), center.get("lon")


def analyze_facilities_nearby(
    latitude: float,
    longitude: float,
    radius: int = 800,
) -> dict:
    """
    分析指定座標附近生活設施。

    Args:
        latitude: 緯度
        longitude: 經度
        radius: 搜尋半徑，單位公尺

    Returns:
        dict: 附近設施統計、最近設施、生活機能分數
    """
    overpass_url = "https://overpass-api.de/api/interpreter"

    query = f"""
    [out:json][timeout:25];
    (
      node["shop"="convenience"](around:{radius},{latitude},{longitude});
      way["shop"="convenience"](around:{radius},{latitude},{longitude});
      node["amenity"="hospital"](around:{radius},{latitude},{longitude});
      way["amenity"="hospital"](around:{radius},{latitude},{longitude});
      node["amenity"="clinic"](around:{radius},{latitude},{longitude});
      way["amenity"="clinic"](around:{radius},{latitude},{longitude});
      node["amenity"="pharmacy"](around:{radius},{latitude},{longitude});
      way["amenity"="pharmacy"](around:{radius},{latitude},{longitude});
      node["leisure"="park"](around:{radius},{latitude},{longitude});
      way["leisure"="park"](around:{radius},{latitude},{longitude});
      node["amenity"="bicycle_rental"](around:{radius},{latitude},{longitude});
      way["amenity"="bicycle_rental"](around:{radius},{latitude},{longitude});
      node["amenity"="parking"](around:{radius},{latitude},{longitude});
      way["amenity"="parking"](around:{radius},{latitude},{longitude});
      node["shop"="mall"](around:{radius},{latitude},{longitude});
      way["shop"="mall"](around:{radius},{latitude},{longitude});
      node["shop"="supermarket"](around:{radius},{latitude},{longitude});
      way["shop"="supermarket"](around:{radius},{latitude},{longitude});
    );
    out center;
    """

    try:
        response = requests.post(
            overpass_url,
            data=query,
            headers={"User-Agent": "housing-area-insight-agent/1.0"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        facilities = {
            "convenience_store": [],
            "hospital": [],
            "clinic": [],
            "pharmacy": [],
            "park": [],
            "bike_rental": [],
            "parking": [],
            "mall": [],
            "supermarket": [],
        }

        for item in data.get("elements", []):
            tags = item.get("tags", {})
            item_lat, item_lon = get_item_coordinate(item)

            if item_lat is None or item_lon is None:
                continue

            facility_info = {
                "name": tags.get("name", "未命名設施"),
                "address": build_address(tags),
                "latitude": item_lat,
                "longitude": item_lon,
                "distance_meters": calculate_distance_meters(
                    latitude,
                    longitude,
                    item_lat,
                    item_lon,
                ),
                "google_maps_url": (
                    f"https://www.google.com/maps/search/?api=1&query={item_lat},{item_lon}"
                ),
            }

            if tags.get("shop") == "convenience":
                facilities["convenience_store"].append(facility_info)
            elif tags.get("amenity") == "hospital":
                facilities["hospital"].append(facility_info)
            elif tags.get("amenity") == "clinic":
                facilities["clinic"].append(facility_info)
            elif tags.get("amenity") == "pharmacy":
                facilities["pharmacy"].append(facility_info)
            elif tags.get("leisure") == "park":
                facilities["park"].append(facility_info)
            elif tags.get("amenity") == "bicycle_rental":
                facilities["bike_rental"].append(facility_info)
            elif tags.get("amenity") == "parking":
                facilities["parking"].append(facility_info)
            elif tags.get("shop") == "mall":
                facilities["mall"].append(facility_info)
            elif tags.get("shop") == "supermarket":
                facilities["supermarket"].append(facility_info)

        for items in facilities.values():
            items.sort(key=lambda facility: facility["distance_meters"])

        counts = {key: len(value) for key, value in facilities.items()}

        score = (
            counts["convenience_store"]
            + counts["hospital"] * 3
            + counts["clinic"] * 2
            + counts["pharmacy"] * 2
            + counts["park"]
            + counts["bike_rental"]
            + counts["parking"]
            + counts["mall"] * 2
            + counts["supermarket"] * 2
        )

        level = "高" if score >= 25 else "中" if score >= 10 else "低"

        nearest_facilities = {
            key: value[:3]
            for key, value in facilities.items()
        }

        message = (
            f"附近 {radius} 公尺內生活機能評估為「{level}」。"
            f"超商 {counts['convenience_store']} 間、"
            f"診所 {counts['clinic']} 間、"
            f"藥局 {counts['pharmacy']} 間、"
            f"公園 {counts['park']} 個、"
            f"超市 {counts['supermarket']} 間。"
        )

        return {
            "status": "success",
            "data": {
                "latitude": latitude,
                "longitude": longitude,
                "radius_meters": radius,
                "facility_level": level,
                "score": score,
                "counts": counts,
                "nearest_facilities": nearest_facilities,
            },
            "source": "OpenStreetMap / Overpass API",
            "message": message,
        }

    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "error_message": f"Failed to fetch facility data: {str(e)}",
            "source": "OpenStreetMap / Overpass API",
        }