import re
import math
import requests
import urllib3
from bs4 import BeautifulSoup

from housing_agent.tools.location_tool import geocode_location

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


SITE_IDS = {
    # 北部
    "基隆": 46,
    "陽明": 54,
    "萬華": 62,
    "士林": 5,
    "大同": 6,
    "中山": 11,
    "古亭": 16,
    "松山": 29,

    # 新北
    "板橋": 30,
    "林口": 31,
    "汐止": 22,
    "永和": 19,
    "三重": 2,
    "土城": 4,
    "新店": 56,
    "新莊": 57,
    "菜寮": 53,
    "淡水": 48,
    "富貴角": 96,
    "萬里": 61,

    # 桃園
    "桃園": 43,
    "龍潭": 73,
    "觀音": 76,
    "大園": 8,
    "中壢": 12,
    "平鎮": 18,

    # 新竹
    "新竹": 55,
    "湖口": 52,
    "竹東": 24,

    # 苗栗
    "三義": 3,
    "苗栗": 41,
    "頭份": 72,

    # 台中
    "豐原": 74,
    "忠明": 28,
    "大里": 7,
    "西屯": 25,
    "沙鹿": 26,
    "臺灣大道": 142,

    # 南投
    "竹山": 23,
    "南投": 37,
    "埔里": 42,

    # 彰化
    "線西": 70,
    "彰化": 64,
    "二林": 1,
    "大城": 136,
    "員林": 139,

    # 雲林
    "斗六": 14,
    "臺西": 65,
    "崙背": 47,
    "麥寮": 49,

    # 嘉義
    "嘉義": 63,
    "新港": 58,
    "朴子": 21,

    # 台南
    "安南": 20,
    "新營": 59,
    "臺南": 67,
    "台南": 67,
    "善化": 50,
    "林森": 140,

    # 高雄
    "復興": 51,
    "美濃": 40,
    "鳳山": 68,
    "橋頭": 71,
    "楠梓": 60,
    "左營": 17,
    "仁武": 13,
    "大寮": 9,
    "小港": 10,
    "前金": 35,
    "前鎮": 36,
    "林園": 32,

    # 屏東
    "屏東": 38,
    "恆春": 39,
    "潮州": 69,

    # 東部
    "宜蘭": 27,
    "冬山": 15,
    "花蓮": 33,
    "關山": 75,
    "臺東": 66,
    "台東": 66,

    # 離島
    "馬公": 44,
    "金門": 34,
    "馬祖": 45,
}


# 注意：
# 這份座標目前是組員用 geocode 產生的初版資料。
# 部分測站名稱可能被定位到錯誤位置，之後建議改成官方測站座標。
# 目前先保留作為 MVP 的最近測站判斷基礎。
STATION_COORDS = {
    "基隆": (25.1317232, 121.744652),
    "陽明": (24.4634744, 118.4368052),
    "萬華": (25.0334399, 121.4999266),
    "士林": (25.0934949, 121.5262468),
    "大同": (25.009319, 121.141948),
    "中山": (25.0526256, 121.5203914),
    "古亭": (25.0264102, 121.5229533),
    "松山": (25.0491542, 121.5781643),

    "板橋": (25.0144988, 121.462992),
    "林口": (25.0657846, 121.3614372),
    "汐止": (25.0674211, 121.6606848),
    "永和": (23.857553, 120.304116),
    "三重": (25.0546641, 121.482813),
    "土城": (24.9731817, 121.444391),
    "新店": (24.9580443, 121.5376991),
    "新莊": (25.0359828, 121.4519938),
    "菜寮": (25.060314, 121.4920589),
    "淡水": (25.167713, 121.4455264),
    "富貴角": (25.2960798, 121.5368819),
    "萬里": (23.42963, 121.388711),

    "桃園": (25.0130205, 121.2148716),
    "龍潭": (24.7792724, 121.7433056),
    "觀音": (23.3961647, 121.3593643),
    "大園": (25.0558139, 121.2106496),
    "中壢": (24.9533168, 121.2261602),
    "平鎮": (24.9226521, 121.1968395),

    "新竹": (24.8014026, 120.971678),
    "湖口": (24.9028021, 121.043748),
    "竹東": (24.7383207, 121.0949025),

    "三義": (24.4205666, 120.7742376),
    "苗栗": (24.5692318, 120.8222649),
    "頭份": (24.6840831, 120.9083476),

    "豐原": (24.2545422, 120.7236842),
    "忠明": (23.8851427, 120.9212839),
    "大里": (24.9667612, 121.9225152),
    "西屯": (25.0913603, 121.657092),
    "沙鹿": (23.4991668, 120.4933484),
    "臺灣大道": (23.7097159, 121.4200265),

    "竹山": (24.116442, 120.593979),
    "南投": (23.90235, 120.6909167),
    "埔里": (23.9666667, 120.9691462),

    "線西": (24.1307299, 120.4709418),
    "彰化": (24.081673, 120.538205),
    "二林": (23.8991521, 120.3681546),
    "大城": (23.8541915, 120.3210776),
    "員林": (23.9593485, 120.5696323),

    "斗六": (23.7118077, 120.5411553),
    "臺西": (23.1414391, 120.2292537),
    "崙背": (23.7607642, 120.3546184),
    "麥寮": (23.7490142, 120.2544168),

    "嘉義": (23.4799042, 120.4415839),
    "新港": (23.107932, 120.1845702),
    "朴子": (23.464327, 120.2469615),

    "安南": (23.755076, 120.495852),
    "新營": (23.3063865, 120.3232684),
    "臺南": (22.9912348, 120.184982),
    "台南": (22.9912348, 120.184982),
    "善化": (23.1330374, 120.3066223),
    "林森": (24.6004637, 121.5124086),

    "復興": (23.2592584, 121.3002874),
    "美濃": (22.8363731, 121.0928033),
    "鳳山": (22.6315973, 120.3566769),
    "橋頭": (22.7610975, 120.3102547),
    "楠梓": (22.7271409, 120.324127),
    "左營": (22.6873207, 120.307384),
    "仁武": (22.7027015, 120.3520022),
    "大寮": (22.6221173, 120.3905893),
    "小港": (22.5645135, 120.3538755),
    "前金": (22.6289683, 120.2946284),
    "前鎮": (22.5892626, 120.307776),
    "林園": (24.9717619, 121.5511202),

    "屏東": (22.6687454, 120.4860668),
    "恆春": (22.0026559, 120.7446924),
    "潮州": (22.5499793, 120.5360618),

    "宜蘭": (24.7545601, 121.7583109),
    "冬山": (24.63671, 121.7919433),
    "花蓮": (23.9926399, 121.6009524),
    "關山": (23.0456036, 121.1644987),
    "臺東": (22.7934597, 121.1224316),
    "台東": (22.7934597, 121.1224316),

    "馬公": (26.1577951, 119.9519756),
    "金門": (24.4480637, 118.3856331),
    "馬祖": (26.3698381, 120.4970704),
}


def calculate_distance_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> int:
    """
    使用 Haversine formula 計算兩點距離，單位公尺。
    """
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


def get_location_coordinates(place: str) -> tuple[float, float]:
    """
    使用既有 Location Tool 將使用者地點轉成經緯度。
    """
    result = geocode_location(place)

    if result["status"] != "success":
        raise ValueError(result.get("error_message", "地點轉換失敗"))

    return result["latitude"], result["longitude"]


def find_nearest_station(place_text: str) -> dict:
    """
    根據使用者輸入地點，找出最近的空品測站。
    """
    latitude, longitude = get_location_coordinates(place_text)

    nearest_station = None
    nearest_distance = float("inf")

    for station_name, coords in STATION_COORDS.items():
        if station_name not in SITE_IDS:
            continue

        station_lat, station_lon = coords

        distance = calculate_distance_meters(
            latitude,
            longitude,
            station_lat,
            station_lon,
        )

        if distance < nearest_distance:
            nearest_distance = distance
            nearest_station = station_name

    if not nearest_station:
        return {
            "status": "error",
            "error_message": "找不到最近空品測站。",
        }

    return {
        "status": "success",
        "station_name": nearest_station,
        "distance_meters": nearest_distance,
        "latitude": latitude,
        "longitude": longitude,
    }


def get_ten_year_trend(site_id: int) -> list:
    response = requests.post(
        "https://airtw.moenv.gov.tw/AJAX_Chart.aspx",
        data={
            "Target": "TenYearAQI",
            "SiteID": str(site_id),
        },
        verify=False,
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def find_metric(data: list, key: str):
    for item in data:
        if key in item:
            return item[key]
    return None


def analyze_air_quality_trend(data: list) -> dict:
    pm25_history = find_metric(data, "PM25")

    if not pm25_history:
        return {
            "pm25_change_percent": None,
            "trend": "未知",
        }

    latest_change = pm25_history[-1]

    if latest_change <= -30:
        trend = "顯著改善"
    elif latest_change < 0:
        trend = "略有改善"
    elif latest_change == 0:
        trend = "持平"
    else:
        trend = "惡化"

    return {
        "pm25_change_percent": latest_change,
        "trend": trend,
    }


def get_year_pm25_average(site_id: int, year: int = 2025) -> dict | None:
    session = requests.Session()
    url = "https://airtw.moenv.gov.tw/CHT/Query/Month_Avg.aspx"

    response = session.get(url, verify=False, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    viewstate_tag = soup.find("input", {"id": "__VIEWSTATE"})
    eventvalidation_tag = soup.find("input", {"id": "__EVENTVALIDATION"})
    viewstategenerator_tag = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})

    if not viewstate_tag or not eventvalidation_tag or not viewstategenerator_tag:
        return None

    payload = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": viewstate_tag["value"],
        "__EVENTVALIDATION": eventvalidation_tag["value"],
        "__VIEWSTATEGENERATOR": viewstategenerator_tag["value"],
        "ctl00$CPH_Content$ddl_Site": str(site_id),
        "ctl00$CPH_Content$ddlQYear": str(year),
        "ctl00$CPH_Content$btnQuery": "查詢",
    }

    response = session.post(
        url,
        data=payload,
        verify=False,
        timeout=20,
    )
    response.raise_for_status()

    matches = re.findall(
        r"<td>PM2\.5</td>\s*"
        r"<td>(\d{4}/\d{2})</td>\s*"
        r"<td>([\d\.]+)</td>",
        response.text,
    )

    values = [float(value) for _, value in matches]

    if not values:
        return None

    average = round(sum(values) / len(values), 2)

    return {
        "year": year,
        "monthly_values": values,
        "pm25_average": average,
    }


def analyze_air_quality_by_station(
    station_name: str,
    year: int = 2025,
) -> dict:
    """
    根據空品測站名稱查詢 PM2.5 年平均與近十年趨勢。
    """
    if station_name not in SITE_IDS:
        return {
            "status": "error",
            "error_message": f"找不到空品測站：{station_name}",
            "available_stations": list(SITE_IDS.keys()),
            "source": "環境部空氣品質監測網",
        }

    site_id = SITE_IDS[station_name]

    try:
        pm25_info = get_year_pm25_average(
            site_id=site_id,
            year=year,
        )

        if not pm25_info:
            return {
                "status": "error",
                "error_message": f"無法取得 {station_name} 測站 {year} 年 PM2.5 平均資料。",
                "source": "環境部空氣品質監測網",
            }

        trend_raw = get_ten_year_trend(site_id)
        trend_info = analyze_air_quality_trend(trend_raw)

        summary = (
            f"{station_name}站 {year} 年 PM2.5 平均濃度為 "
            f"{pm25_info['pm25_average']} μg/m³，"
            f"近十年變化 {trend_info['pm25_change_percent']}%，"
            f"空氣品質呈 {trend_info['trend']} 趨勢。"
        )

        return {
            "status": "success",
            "data": {
                "station_name": station_name,
                "site_id": site_id,
                "year": year,
                "pm25_average": pm25_info["pm25_average"],
                "pm25_change_percent": trend_info["pm25_change_percent"],
                "trend": trend_info["trend"],
            },
            "source": "環境部空氣品質監測網",
            "message": summary,
        }

    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "error_message": f"空氣品質資料請求失敗：{str(e)}",
            "source": "環境部空氣品質監測網",
        }

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"空氣品質分析發生錯誤：{str(e)}",
            "source": "環境部空氣品質監測網",
        }


def analyze_air_quality_by_place(
    place_text: str,
    year: int = 2025,
) -> dict:
    """
    根據使用者輸入地點，找最近空品測站後查詢空氣品質。
    """
    try:
        nearest_result = find_nearest_station(place_text)

        if nearest_result["status"] != "success":
            return {
                "status": "error",
                "error_message": nearest_result["error_message"],
                "source": "環境部空氣品質監測網",
            }

        station_name = nearest_result["station_name"]
        distance_meters = nearest_result["distance_meters"]

        result = analyze_air_quality_by_station(
            station_name=station_name,
            year=year,
        )

        if result["status"] == "success":
            result["data"]["matched_from_place"] = place_text
            result["data"]["nearest_station_distance_meters"] = distance_meters
            result["message"] += (
                f" 此資料以距離查詢地點約 {distance_meters} 公尺的"
                f"「{station_name}」測站作為參考。"
            )

        return result

    except Exception as e:
        return {
            "status": "error",
            "error_message": f"空氣品質地點分析失敗：{str(e)}",
            "source": "環境部空氣品質監測網",
        }