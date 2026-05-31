from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable

import requests as http_requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

try:
    from google import genai
except Exception as exc:
    GENAI_IMPORT_ERROR = exc
    genai = None

try:
    from housing_agent.tools.air_quality_tool import analyze_air_quality_by_place
except Exception as exc:
    AIR_IMPORT_ERROR = exc


    def analyze_air_quality_by_place(place_text: str, year: int = 2025) -> dict[str, Any]:
        return unavailable_tool("空氣品質工具", AIR_IMPORT_ERROR)

try:
    from housing_agent.tools.facility_tool import analyze_facilities_nearby
except Exception as exc:
    FACILITY_IMPORT_ERROR = exc

    def analyze_facilities_nearby(latitude: float, longitude: float, radius: int = 800) -> dict[str, Any]:
        return unavailable_tool("生活機能工具", FACILITY_IMPORT_ERROR)

try:
    from housing_agent.tools.location_tool import geocode_location
except Exception as exc:
    LOCATION_IMPORT_ERROR = exc

    def geocode_location(place: str, country_codes: str = "tw") -> dict[str, Any]:
        return unavailable_tool("地點解析工具", LOCATION_IMPORT_ERROR)

try:
    from housing_agent.tools.night_life_tool import analyze_late_night_living_index
except Exception as exc:
    NIGHT_IMPORT_ERROR = exc

    def analyze_late_night_living_index(latitude: float, longitude: float, radius_m: int = 500) -> dict[str, Any]:
        return unavailable_tool("夜間生活工具", NIGHT_IMPORT_ERROR)

try:
    from housing_agent.tools.meal_tool import recommend_restaurants_for_rental
except Exception as exc:
    MEAL_IMPORT_ERROR = exc

    def recommend_restaurants_for_rental(
        user_request: str,
        latitude: float,
        longitude: float,
        radius_meters: int = 1000,
        top_k: int = 3,
    ) -> dict[str, Any]:
        return unavailable_tool("餐飲推薦工具", MEAL_IMPORT_ERROR)

try:
    from housing_agent.tools.rental_tool import query_rental_range
except Exception as exc:
    RENT_IMPORT_ERROR = exc

    def query_rental_range(latitude: float, longitude: float, radius: str = "2.5公里") -> dict[str, Any]:
        return unavailable_tool("租金工具", RENT_IMPORT_ERROR)

try:
    from housing_agent.tools.transport_tool import analyze_transport_by_point
except Exception as exc:
    TRANSPORT_IMPORT_ERROR = exc

    def analyze_transport_by_point(latitude: float, longitude: float) -> dict[str, Any]:
        return unavailable_tool("交通工具", TRANSPORT_IMPORT_ERROR)


app = Flask(__name__)


DEFAULT_AREA = "台北車站附近"
QUICK_AREAS = ["台北車站附近", "公館附近", "中山站附近", "中央大學附近", "板橋車站附近"]
ADK_API_BASE = os.getenv("ADK_API_BASE", "http://localhost:8001").rstrip("/")
ADK_APP_NAME = os.getenv("ADK_APP_NAME", "housing_agent")
ADK_USER_ID = os.getenv("ADK_USER_ID", "web-user")
ADK_SESSION_ID = ""
ADK_SESSION_READY = False


def unavailable_tool(name: str, error: Exception) -> dict[str, Any]:
    return {
        "status": "error",
        "error_message": f"{name}尚未可用：{error}",
        "source": "Housing Agent",
    }


def now_label() -> str:
    return datetime.now().strftime("%H:%M")


def empty_section(name: str, message: str = "尚未查詢") -> dict[str, Any]:
    return {
        "status": "pending",
        "name": name,
        "message": message,
        "source": "Housing Agent",
        "data": {},
    }


def safe_call(name: str, source: str, func: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        result = func(*args, **kwargs)
    except Exception as exc:  # External data sources should not break the page.
        return {
            "status": "error",
            "name": name,
            "message": "資料暫時無法取得，請稍後再試。",
            "error": str(exc),
            "source": source,
            "data": {},
        }

    if result.get("status") == "success":
        data = result.get("data")
        if data is None:
            data = {
                key: value
                for key, value in result.items()
                if key not in {"status", "message", "source"}
            }
        return {
            "status": "success",
            "name": name,
            "message": result.get("message", "查詢完成。"),
            "source": result.get("source", source),
            "data": data,
        }

    return {
        "status": "error",
        "name": name,
        "message": result.get("error_message", "資料暫時無法取得，請稍後再試。"),
        "source": result.get("source", source),
        "data": result.get("data", {}),
    }


def run_area_analysis(
    query: str,
    include_air: bool = True,
    include_night: bool = True,
    include_meal: bool = True,
) -> dict[str, Any]:
    search_query = normalize_place_query(query)
    location = safe_call("地點解析", "OpenStreetMap Nominatim", geocode_location, search_query)
    if location["status"] != "success":
        return {
            "ok": False,
            "area": query,
            "generated_at": now_label(),
            "summary": "目前無法定位這個地點，請改用較完整的地標、捷運站或地址再試一次。",
            "location": location,
            "sections": {
                "rent": empty_section("租金範圍"),
                "transport": empty_section("交通便利性"),
                "facility": empty_section("生活機能"),
                "air": empty_section("空氣品質", "勾選空氣品質後查詢"),
                "night": empty_section("夜貓生活", "勾選夜間機能後查詢"),
                "meal": empty_section("附近餐飲", "勾選附近餐飲後查詢"),
            },
            "sources": [location],
        }

    loc_data = location["data"]
    latitude = loc_data["latitude"]
    longitude = loc_data["longitude"]

    tasks: dict[str, tuple[str, str, Callable[..., dict[str, Any]], tuple[Any, ...], dict[str, Any]]] = {
        "rent": ("租金範圍", "內政部租金查詢平台", query_rental_range, (latitude, longitude), {}),
        "transport": ("交通便利性", "TDX / OpenStreetMap Overpass API", analyze_transport_by_point, (latitude, longitude), {}),
        "facility": ("生活機能", "OpenStreetMap / Overpass API", analyze_facilities_nearby, (latitude, longitude), {"radius": 800}),
    }

    if include_air:
        tasks["air"] = (
            "空氣品質",
            "環境部空氣品質監測網",
            analyze_air_quality_by_place,
            (search_query,),
            {},
        )
    if include_night:
        tasks["night"] = (
            "夜貓生活",
            "Google Places API",
            analyze_late_night_living_index,
            (latitude, longitude),
            {"radius_m": 500},
        )

    if include_meal:
        tasks["meal"] = (
            "附近餐飲",
            "Geoapify / OpenStreetMap Overpass API",
            recommend_restaurants_for_rental,
            (query, latitude, longitude),
            {"radius_meters": 1000, "top_k": 3},
        )

    sections: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            key: executor.submit(safe_call, name, source, func, *args, **kwargs)
            for key, (name, source, func, args, kwargs) in tasks.items()
        }
        for key, future in futures.items():
            sections[key] = future.result()

    sections.setdefault("air", empty_section("空氣品質", "勾選空氣品質後查詢"))
    sections.setdefault("night", empty_section("夜貓生活", "勾選夜間機能後查詢"))
    sections.setdefault("meal", empty_section("附近餐飲", "勾選附近餐飲後查詢"))

    rule_summary = build_rule_summary(query, location, sections)
    llm_summary = build_llm_summary(query, location, sections, rule_summary)
    summary = llm_summary["message"] if llm_summary["status"] == "success" else rule_summary

    return {
        "ok": True,
        "area": clean_area_name(query, loc_data),
        "generated_at": now_label(),
        "summary": summary,
        "location": location,
        "sections": sections,
        "llm": llm_summary,
        "sources": [location, *sections.values(), llm_summary],
    }


def clean_area_name(query: str, location_data: dict[str, Any]) -> str:
    address = location_data.get("address") or {}
    candidate = address.get("suburb") or address.get("city_district") or address.get("town") or query
    return str(candidate).replace("附近", "").strip() or query


def normalize_place_query(query: str) -> str:
    normalized = query.strip()
    leading_phrases = ("我今天想在", "我想在", "想在", "幫我看", "幫我分析", "查一下", "查詢")
    for phrase in leading_phrases:
        if normalized.startswith(phrase):
            normalized = normalized[len(phrase):].strip()

    # Chat questions often look like "公館附近夜間生活方便嗎".
    # Keep the place before "附近" and drop the intent after it.
    if "附近" in normalized:
        before_nearby = normalized.split("附近", 1)[0].strip(" ，,。?？")
        if before_nearby:
            return before_nearby

    for phrase in (
        "附近租屋",
        "附近租房",
        "附近餐廳",
        "餐廳推薦",
        "餐飲推薦",
        "推薦",
        "夜間生活方便嗎",
        "夜間生活",
        "夜生活方便嗎",
        "夜生活",
        "生活機能好不好",
        "生活機能",
        "交通方便嗎",
        "交通",
        "方便嗎",
        "好不好",
        "有什麼好吃",
        "吃什麼",
        "吃飯",
        "美食",
        "下雨不想走遠",
        "不想走太遠",
        "不要太遠",
        "想吃熱食",
        "熱食",
        "附近",
        "租房子",
        "租屋",
        "找房子",
        "找房",
    ):
        normalized = normalized.replace(phrase, "")
    return normalized.strip(" ，,。?？") or query


def build_rule_summary(query: str, location: dict[str, Any], sections: dict[str, dict[str, Any]]) -> str:
    parts = [f"已定位「{query}」，並整理租金、交通與生活機能。"]

    rent = sections.get("rent", {})
    if rent.get("status") == "success":
        parts.append(rent["message"])

    transport = sections.get("transport", {})
    if transport.get("status") == "success":
        level = transport.get("data", {}).get("transport_level")
        if level:
            parts.append(f"交通便利性為「{level}」。")

    facility = sections.get("facility", {})
    if facility.get("status") == "success":
        level = facility.get("data", {}).get("facility_level")
        if level:
            parts.append(f"生活機能為「{level}」。")

    if all(sections.get(key, {}).get("status") != "success" for key in ("rent", "transport", "facility")):
        parts.append("外部資料源目前回應不完整，但地點解析已完成，可稍後重新查詢。")

    return " ".join(parts)


def compact_sections_for_llm(sections: dict[str, dict[str, Any]]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, section in sections.items():
        data = section.get("data", {})
        compact[key] = {
            "name": section.get("name"),
            "status": section.get("status"),
            "message": section.get("message"),
            "source": section.get("source"),
            "data": data,
        }
    return compact


def build_llm_summary(
    query: str,
    location: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    fallback_summary: str,
) -> dict[str, Any]:
    if genai is None:
        return {
            "status": "error",
            "name": "Gemini Agent 摘要",
            "message": f"Gemini SDK 尚未可用，改用規則摘要：{GENAI_IMPORT_ERROR}",
            "source": "Google Gemini API",
            "data": {},
        }

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "status": "error",
            "name": "Gemini Agent 摘要",
            "message": "尚未設定 GOOGLE_API_KEY，已改用規則摘要。",
            "source": "Google Gemini API",
            "data": {},
        }

    payload = {
        "query": query,
        "location": location,
        "sections": compact_sections_for_llm(sections),
        "fallback_summary": fallback_summary,
    }
    payload_text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(payload_text) > 12000:
        payload_text = payload_text[:12000] + "...[truncated]"

    prompt = f"""
你是租屋生活圈分析系統的總結 Agent。
請根據下方 JSON 工具結果，用繁體中文寫一段 2 到 4 句的整體建議。

規則：
1. 只根據工具結果回答，不要捏造沒有出現的數字。
2. 優先整合租金、交通、生活機能；如果有空氣品質、夜貓生活、餐飲推薦，也一起納入。
3. 語氣要像專業但好懂的租屋顧問。
4. 不要列點，不要說「根據 JSON」。

工具結果：
{payload_text}
""".strip()

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            raise ValueError("Gemini 未回傳文字。")

        return {
            "status": "success",
            "name": "Gemini Agent 摘要",
            "message": text,
            "source": "Google Gemini API",
            "data": {
                "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                "fallback_summary": fallback_summary,
            },
        }
    except Exception as exc:
        return {
            "status": "error",
            "name": "Gemini Agent 摘要",
            "message": f"Gemini 摘要暫時無法產生，已改用規則摘要：{exc}",
            "source": "Google Gemini API",
            "data": {
                "fallback_summary": fallback_summary,
            },
        }


def ensure_adk_session() -> str:
    global ADK_SESSION_ID, ADK_SESSION_READY
    if not ADK_SESSION_ID:
        ADK_SESSION_ID = str(time.time())
    if ADK_SESSION_READY:
        return ADK_SESSION_ID

    response = http_requests.post(
        f"{ADK_API_BASE}/apps/{ADK_APP_NAME}/users/{ADK_USER_ID}/sessions/{ADK_SESSION_ID}",
        headers={"Content-Type": "application/json"},
        json={},
        timeout=10,
    )
    if response.status_code not in {200, 201, 409}:
        raise RuntimeError(f"建立 ADK session 失敗：{response.status_code} {response.text}")

    ADK_SESSION_READY = True
    return ADK_SESSION_ID


def _format_function_args(args: dict[str, Any]) -> str:
    if not args:
        return ""
    parts = []
    for name, value in args.items():
        if isinstance(value, str):
            rendered = value
        else:
            rendered = json.dumps(value, ensure_ascii=False, default=str)
        parts.append(f"{name}: {rendered}")
    return " [" + "] [".join(parts) + "]"


def _extract_adk_reply(events: list[dict[str, Any]]) -> str:
    lines = []

    for event in events:
        content = event.get("content", {})
        parts = content.get("parts", [])

        for part in parts:
            if "functionCall" in part:
                function_call = part["functionCall"]
                name = function_call.get("name", "unknown_tool")
                args = _format_function_args(function_call.get("args", {}))
                lines.append(f"[Function Call] {name}{args}")
            elif "functionResponse" in part:
                function_response = part["functionResponse"]
                name = function_response.get("name", "tool")
                lines.append(f"[Function Response] {name} 完成")
            elif "text" in part and part["text"]:
                lines.append(part["text"])

    return "\n".join(lines).strip() or "ADK Agent 沒有回傳文字。"


def run_adk_agent(message: str) -> str:
    session_id = ensure_adk_session()
    body = {
        "app_name": ADK_APP_NAME,
        "user_id": ADK_USER_ID,
        "session_id": session_id,
        "new_message": {
            "role": "user",
            "parts": [{"text": message}],
        },
    }
    response = http_requests.post(
        f"{ADK_API_BASE}/run",
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    response.raise_for_status()
    result_json = response.json()
    if not isinstance(result_json, list):
        raise RuntimeError(f"ADK /run 回傳格式不正確：{result_json}")

    return _extract_adk_reply(result_json)


def chat_reply(message: str) -> str:
    lowered = message.lower()
    include_air = any(keyword in message for keyword in ("空氣", "pm2.5", "AQI", "aqi"))
    include_night = any(keyword in message for keyword in ("夜", "宵夜", "半夜", "24", "外送", "晚下班", "晚下課"))
    include_meal = any(
        keyword in message
        for keyword in ("吃什麼", "餐廳", "食物", "吃飯", "美食", "熱食", "咖啡", "健康餐", "蔬食", "素食", "下雨不想走遠")
    )

    if any(word in message for word in ("你好", "哈囉", "嗨", "你是誰", "可以做什麼")):
        return "我是租屋地區資訊 Agent，可以幫你整理指定地點的租金範圍、交通便利性、生活機能，也能加查空氣品質、夜間生活與附近餐飲推薦。"

    if any(word in message for word in ("租金", "交通", "捷運", "生活", "附近", "租屋", "房租", "空氣", "夜", "餐廳", "吃")) or "rent" in lowered:
        result = run_area_analysis(message, include_air=True, include_night=True, include_meal=True)
        if not result["ok"]:
            return result["summary"]

        sections = result["sections"]
        lines = [f"{result['area']}分析完成。", result["summary"]]
        for key in ("air", "night", "meal"):
            if sections[key]["status"] == "success":
                lines.append(sections[key]["message"])
        return "\n".join(lines)

    return "你可以直接輸入想了解的地點，例如「中央大學附近租屋」、「公館附近夜間生活方便嗎」或「台北車站附近吃什麼」。"


@app.get("/")
def index() -> str:
    initial_area = {
        "area": "台北車站",
        "generated_at": now_label(),
        "summary": "輸入地點後，Agent 會整理租金範圍、交通便利性、生活機能，並可加查空氣品質與夜間生活。",
    }
    return render_template("index.html", initial_area=initial_area, quick_areas=QUICK_AREAS)


@app.post("/api/analyze")
def analyze() -> Any:
    body = request.get_json(silent=True) or {}
    query = str(body.get("location", "")).strip()
    if not query:
        return jsonify({"error": "請輸入想分析的租屋地點。"}), 400

    result = run_area_analysis(
        query,
        include_air=True,
        include_night=True,
        include_meal=True,
    )
    status = 200 if result["ok"] else 422
    return jsonify(result), status


@app.post("/api/chat")
def chat() -> Any:
    body = request.get_json(silent=True) or {}
    message = str(body.get("message", "")).strip()
    if not message:
        return jsonify({"error": "請輸入問題。"}), 400
    try:
        reply = run_adk_agent(message)
    except Exception as exc:
        reply = f"ADK Agent 暫時無法回覆：{exc}"
    return jsonify({"reply": reply, "generated_at": now_label()})


@app.get("/health")
def health() -> Any:
    return jsonify({"status": "ok", "service": "housing-agent-web"})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
