#經緯度-->TWD97-->抓租金(Q1、median、Q3)
import time
import json
import requests
import urllib3
from pyproj import Transformer

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

RENT_API_URL = "https://moisagis.moi.gov.tw/rent/cfm/calrentbuffer.cfm"


def wgs84_to_twd97(latitude: float, longitude: float) -> tuple[float, float]:
    """
    將 WGS84 經緯度轉為 TWD97 / TM2 zone 121。
    內政部租金平台使用 cx / cy 平面座標。
    """
    transformer = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:3826",
        always_xy=True,
    )

    cx, cy = transformer.transform(longitude, latitude)
    return round(cx, 1), round(cy, 1)


def parse_rent_response(raw_text: str) -> dict:
    """
    解析內政部租金查詢平台回傳資料。
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "status": "error",
            "error_message": "Rental response is not valid JSON.",
        }

    if data.get("TEXT") != "SUCCESS":
        return {
            "status": "error",
            "error_message": data.get("TEXT", "Rental query failed."),
            "raw_status": data.get("TEXT"),
        }

    return {
        "status": "success",
        "rent_q1": data.get("RENT_Q1"),
        "rent_median": data.get("RENT_MEDIAN"),
        "rent_q3": data.get("RENT_Q3"),
    }


def get_rental_range_by_point(
    latitude: float,
    longitude: float,
    radius: str = "2.5公里",
    rent_show: str = "中位數",
    rent_type: str = "全部類別",
    build_age: str = "全部類別",
) -> dict:
    """
    根據經緯度與半徑查詢租金範圍。

    Args:
        latitude: WGS84 緯度
        longitude: WGS84 經度
        radius: "1公里"、"2.5公里"、"5公里"

    Returns:
        dict: 租金 Q1 / Median / Q3
    """
    allowed_radius = {"1公里", "2.5公里", "5公里"}

    if radius not in allowed_radius:
        return {
            "status": "error",
            "error_message": f"不支援的半徑：{radius}，請使用 1公里、2.5公里 或 5公里。",
            "source": "內政部租金查詢平台",
        }

    cx, cy = wgs84_to_twd97(latitude, longitude)

    url = f"{RENT_API_URL}?_t={int(time.time() * 1000)}"

    payload = {
        "cx": str(cx),
        "cy": str(cy),
        "selectedbuffer": radius,
        "selectedrentshow": rent_show,
        "selectedrenttype": rent_type,
        "selectedbuildage": build_age,
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://moisagis.moi.gov.tw/rent/",
        "Origin": "https://moisagis.moi.gov.tw",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }

    try:
        response = requests.post(
            url,
            data=payload,
            headers=headers,
            timeout=15,
            verify=False,
        )
        response.raise_for_status()

        rent_data = parse_rent_response(response.text)

        if rent_data["status"] != "success":
            return {
                "status": "error",
                "error_message": rent_data.get("error_message", "租金資料解析失敗。"),
                "latitude": latitude,
                "longitude": longitude,
                "cx": cx,
                "cy": cy,
                "radius": radius,
                "source": "內政部租金查詢平台",
            }

        return {
            "status": "success",
            "latitude": latitude,
            "longitude": longitude,
            "cx": cx,
            "cy": cy,
            "radius": radius,
            "rent_q1": rent_data.get("rent_q1"),
            "rent_median": rent_data.get("rent_median"),
            "rent_q3": rent_data.get("rent_q3"),
            "source": "內政部租金查詢平台",
        }

    except requests.Timeout:
        return {
            "status": "error",
            "error_message": "租金查詢逾時，請稍後再試。",
            "source": "內政部租金查詢平台",
        }
    except requests.RequestException as e:
        return {
            "status": "error",
            "error_message": f"租金查詢請求失敗：{str(e)}",
            "source": "內政部租金查詢平台",
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"租金查詢發生未知錯誤：{str(e)}",
            "source": "內政部租金查詢平台",
        }