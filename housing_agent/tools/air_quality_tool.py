#空氣品質
import re
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


SITE_IDS = {
    "中壢": 12,
    "桃園": 43,
    "平鎮": 18,
    "龍潭": 73,
    "新竹": 55,
    "湖口": 52,
    "竹東": 24,
    "淡水": 48,
    "板橋": 30,
    "林口": 31,
    "新莊": 57,
    "土城": 4,
    "永和": 19,
    "汐止": 22,
    "臺南": 67,
    "台南": 67,
    "高雄": 68,
    "屏東": 38,
    "宜蘭": 27,
    "花蓮": 33,
    "臺東": 66,
    "台東": 66,
}


def infer_air_quality_station(place_text: str) -> str | None:
    """
    從地點文字或 geocode display_name 推測空品測站。
    第一版採關鍵字對應。
    """
    if not place_text:
        return None

    for station_name in SITE_IDS:
        if station_name in place_text:
            return station_name

    # 常見地點補充
    if "中央大學" in place_text or "國立中央大學" in place_text:
        return "中壢"

    if "台北車站" in place_text or "臺北車站" in place_text or "西門町" in place_text:
        return "板橋"

    if "台大" in place_text or "臺灣大學" in place_text or "台灣大學" in place_text:
        return "永和"

    return None


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
        pm25_info = get_year_pm25_average(site_id=site_id, year=year)

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
    根據地點文字推測最近空品測站，再查空氣品質。
    """
    station_name = infer_air_quality_station(place_text)

    if not station_name:
        return {
            "status": "error",
            "error_message": (
                "目前無法從地點判斷對應空品測站，"
                "請提供較明確的行政區或測站名稱，例如中壢、桃園、板橋。"
            ),
            "source": "環境部空氣品質監測網",
        }

    result = analyze_air_quality_by_station(station_name, year=year)

    if result["status"] == "success":
        result["data"]["matched_from_place"] = place_text

    return result