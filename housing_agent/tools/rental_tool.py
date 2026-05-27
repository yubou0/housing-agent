from housing_agent.services.rental_service import get_rental_range_by_point


def query_rental_range(
    latitude: float,
    longitude: float,
    radius: str = "2.5公里",
) -> dict:
    """
    查詢指定座標周邊的租金範圍。

    Args:
        latitude: 緯度
        longitude: 經度
        radius: 查詢半徑，可使用「1公里」、「2.5公里」、「5公里」

    Returns:
        dict: 包含 rent_q1、rent_median、rent_q3
    """
    result = get_rental_range_by_point(
        latitude=latitude,
        longitude=longitude,
        radius=radius,
    )

    if result["status"] != "success":
        return result

    return {
        "status": "success",
        "data": {
            "latitude": result["latitude"],
            "longitude": result["longitude"],
            "radius": result["radius"],
            "rent_q1": result["rent_q1"],
            "rent_median": result["rent_median"],
            "rent_q3": result["rent_q3"],
            "rent_range_text": (
                f"{result['rent_q1']} 元 ~ {result['rent_q3']} 元，"
                f"中位數約 {result['rent_median']} 元"
            ),
        },
        "source": result["source"],
        "message": (
            f"查詢半徑 {result['radius']} 內，租金主要範圍約為 "
            f"{result['rent_q1']} 元至 {result['rent_q3']} 元，"
            f"中位數約 {result['rent_median']} 元。"
        ),
    }