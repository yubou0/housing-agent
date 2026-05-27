#附近交通
import os
import requests
from dotenv import load_dotenv

load_dotenv()


def get_tdx_token() -> str | None:
    """
    取得 TDX access token。
    需要 .env:
    TDX_CLIENT_ID
    TDX_CLIENT_SECRET
    """
    url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"

    client_id = os.getenv("TDX_CLIENT_ID")
    client_secret = os.getenv("TDX_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        response = requests.post(url, data=payload, timeout=15)
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.exceptions.RequestException:
        return None


def approximate_distance_meters(
    lat1: float,
    lng1: float,
    lat2: float,
    lng2: float,
) -> float:
    return ((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2) ** 0.5 * 111000


def get_nearby_mrt(
    latitude: float,
    longitude: float,
    radius_m: int = 1500,
) -> list[dict]:
    token = get_tdx_token()

    if not token:
        return []

    endpoints = [
        ("台北捷運", "https://tdx.transportdata.tw/api/basic/v2/Rail/Metro/Station/TRTC"),
        ("台中捷運", "https://tdx.transportdata.tw/api/basic/v2/Rail/Metro/Station/TMRT"),
        ("高雄捷運", "https://tdx.transportdata.tw/api/basic/v2/Rail/Metro/Station/KRTC"),
        ("桃園捷運", "https://tdx.transportdata.tw/api/basic/v2/Rail/Metro/Station/TYMC"),
    ]

    headers = {"authorization": f"Bearer {token}"}

    all_stations = []

    for system_name, url in endpoints:
        try:
            response = requests.get(
                url,
                headers=headers,
                params={"$format": "JSON"},
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()

            if isinstance(data, list):
                for station in data:
                    station["_system_name"] = system_name
                all_stations.extend(data)

        except requests.exceptions.RequestException:
            continue

    nearby = []

    for station in all_stations:
        pos = station.get("StationPosition") or {}
        station_lat = pos.get("PositionLat")
        station_lng = pos.get("PositionLon")

        if station_lat is None or station_lng is None:
            continue

        distance = approximate_distance_meters(
            latitude,
            longitude,
            station_lat,
            station_lng,
        )

        if distance <= radius_m:
            nearby.append({
                "system": station.get("_system_name", "捷運"),
                "name": station.get("StationName", {}).get("Zh_tw", "未知站"),
                "distance_meters": round(distance),
            })

    return sorted(nearby, key=lambda item: item["distance_meters"])[:5]


def get_nearby_bus_stops(
    latitude: float,
    longitude: float,
    radius_m: int = 500,
) -> list[dict]:
    url = "https://overpass-api.de/api/interpreter"

    query = f"""
    [out:json][timeout:10];
    node["highway"="bus_stop"](around:{radius_m},{latitude},{longitude});
    out center;
    """

    try:
        response = requests.get(
            url,
            params={"data": query},
            headers={"User-Agent": "housing-area-insight-agent/1.0"},
            timeout=15,
        )
        response.raise_for_status()

        data = response.json()
        nearby = []
        seen = set()

        for element in data.get("elements", []):
            tags = element.get("tags", {})
            name = tags.get("name")

            if not name or name in seen:
                continue

            stop_lat = element.get("lat")
            stop_lng = element.get("lon")

            if stop_lat is None or stop_lng is None:
                continue

            distance = approximate_distance_meters(
                latitude,
                longitude,
                stop_lat,
                stop_lng,
            )

            if distance <= radius_m:
                nearby.append({
                    "name": name,
                    "distance_meters": round(distance),
                })
                seen.add(name)

        return sorted(nearby, key=lambda item: item["distance_meters"])[:5]

    except requests.exceptions.RequestException:
        return []


def get_nearby_train_station(
    latitude: float,
    longitude: float,
    radius_m: int = 10000,
) -> dict | None:
    token = get_tdx_token()

    if not token:
        return None

    url = "https://tdx.transportdata.tw/api/basic/v2/Rail/TRA/Station"
    headers = {"authorization": f"Bearer {token}"}

    try:
        response = requests.get(
            url,
            headers=headers,
            params={"$format": "JSON"},
            timeout=10,
        )
        response.raise_for_status()

        stations = response.json()
        candidates = []

        if isinstance(stations, list):
            for station in stations:
                pos = station.get("StationPosition", {})
                station_lat = pos.get("PositionLat")
                station_lng = pos.get("PositionLon")

                if station_lat is None or station_lng is None:
                    continue

                distance = approximate_distance_meters(
                    latitude,
                    longitude,
                    station_lat,
                    station_lng,
                )

                if distance <= radius_m:
                    candidates.append({
                        "name": station.get("StationName", {}).get("Zh_tw", ""),
                        "distance_meters": round(distance),
                    })

        if not candidates:
            return None

        return sorted(candidates, key=lambda item: item["distance_meters"])[0]

    except requests.exceptions.RequestException:
        return None


def analyze_transport_by_point(
    latitude: float,
    longitude: float,
) -> dict:
    """
    分析指定座標附近交通便利性。

    Args:
        latitude: 緯度
        longitude: 經度

    Returns:
        dict: 附近火車站、捷運站、公車站
    """
    train_station = get_nearby_train_station(latitude, longitude, 10000)
    mrt_stations = get_nearby_mrt(latitude, longitude, 1500)
    bus_stops = get_nearby_bus_stops(latitude, longitude, 500)

    score = 0

    if train_station:
        score += 30
    if mrt_stations:
        score += 40
    if len(bus_stops) >= 3:
        score += 30
    elif bus_stops:
        score += 15

    level = "高" if score >= 70 else "中" if score >= 35 else "低"

    message_parts = [f"交通便利性評估為「{level}」。"]

    if train_station:
        message_parts.append(
            f"最近火車站為 {train_station['name']}，距離約 {train_station['distance_meters']} 公尺。"
        )
    else:
        message_parts.append("附近 10 公里內未找到台鐵車站。")

    if mrt_stations:
        nearest_mrt = mrt_stations[0]
        message_parts.append(
            f"最近捷運站為 {nearest_mrt['name']}，距離約 {nearest_mrt['distance_meters']} 公尺。"
        )
    else:
        message_parts.append("附近 1.5 公里內未找到捷運站。")

    if bus_stops:
        message_parts.append(f"附近 500 公尺內找到 {len(bus_stops)} 個公車站牌。")
    else:
        message_parts.append("附近 500 公尺內未找到公車站牌。")

    return {
        "status": "success",
        "data": {
            "latitude": latitude,
            "longitude": longitude,
            "transport_level": level,
            "score": score,
            "nearest_train_station": train_station,
            "nearby_mrt_stations": mrt_stations,
            "nearby_bus_stops": bus_stops,
        },
        "source": "TDX / OpenStreetMap Overpass API",
        "message": " ".join(message_parts),
    }