from serpapi import SerpApiClient
from config import get_settings
from models import ToolResult
from typing import Literal
import asyncio,httpx



async def search_information(query:str) -> ToolResult:
    """
    在线搜索工具
    """
    search_api = get_settings().search_api_key
    if not search_api:
        return ToolResult.failure("CONFIG_MISSING", "未配置搜索 API")
    
    params = {
        'engine':'google',
        'q':query,
        'api_key':search_api,
        'gl':'cn',      #国家代码
        'hl':'zh-cn'    #语言代码
    }

    try:
        client = SerpApiClient(params_dict=params)
        response = await asyncio.to_thread(client.get_dict)

     # 智能解析:优先寻找最直接的答案
        if "answer_box_list" in response:
            return ToolResult.success(response["answer_box_list"])
        if "answer_box" in response and "answer" in response["answer_box"]:
            return ToolResult.success(response["answer_box"]['answer'])
        if "knowledge_graph" in response and "description" in response["knowledge_graph"]:
            return ToolResult.success(response["knowledge_graph"]["description"])

        if "organic_results" in response and response["organic_results"]:
             # 如果没有直接答案，则返回前三个有机结果的摘要
            snippets = [
                f"[{i+1}] {res.get('title', '')}\n{res.get('snippet', '')}"
                for i, res in enumerate(response["organic_results"][:3])
            ]
            return ToolResult.success("\n\n".join(snippets))
        return ToolResult.success(f"没有找到关于 '{query}' 的信息。")
    
    except Exception as e:
        return ToolResult.failure("EXTERNAL_SERVICE_ERROR", f"搜索时发生错误：{e}", retryable=True)
    

async def weather_query_gaode(
            city:str,           #待查询地区
            target_date:str     #目标日期
    ):
    """
    用来查询某个地区的天气，可以提供当前天气到未来四天天气预报  
    input example:
    city:"成都",
    target_date:"2026-09-04"
    """
    url = "https://restapi.amap.com/v3/weather/weatherInfo"
    weather_api = get_settings().gaode_map_api
    if not weather_api:
        return ToolResult.failure("CONFIG_MISSING", "未配置天气查询API")
    
    try:
        #发送get请求
        timeout = httpx.Timeout(get_settings().tool_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                adcode = await get_adcode(city=city,AMAP_KEY=weather_api,client=client)
                if not adcode:
                    return ToolResult.failure(
                        "INVALID_CITY",
                        f"未找到城市 {city} 对应的 adcode",
                        retryable=False
                    )
            except Exception as e:
                return ToolResult.failure("EXTERNAL_SERVICE_ERROR", f"转city为adcode码错误：{e}", retryable=True)
            params = {
                "key": weather_api,
                "city": adcode,
                "extensions": "all",
                "output": "JSON"
            }
            response = await client.get(url,params=params)
        #判断请求返回状态码是否正常，正常不管，不正常raise出HTTPError
        response.raise_for_status()
        #将返回的消息requests.text转为json格式
        data = response.json()

        if data.get("status") != "1":
            return ToolResult.failure("EXTERNAL_SERVICE_ERROR", f"高德api请求失败", retryable=False)

        forecasts = data.get("forecasts", [])

        if not forecasts:
            return ToolResult.failure(
                "INVALID_RESPONSE",
                "高德 API 未返回天气预报数据",
                retryable=False
            )

        casts = forecasts[0].get("casts", [])

        # 找指定日期
        for weather in casts:
            if weather.get("date") == target_date:
                return ToolResult.success({
                        "city": city,
                        "date": target_date,
                        "week":weather.get("week"),
                        "day_weather": weather.get('dayweather'),
                        "day_temp":weather.get("daytemp_float"),
                        "night_weather":weather.get("nightweather"),
                        "night_temp":weather.get("nighttemp_float"),
                        "day_wind":weather.get('daywind'),
                        "daypower":weather.get("daypower"),
                        "nightwind":weather.get("nightwind"),
                        "nightpower":weather.get("nightpower")
                    })

        return ToolResult.failure("EXTERNAL_SERVICE_ERROR", f"未查询到指定日期天气", retryable=False)
    except Exception as e:
        return ToolResult.failure("EXTERNAL_SERVICE_ERROR", f"高德api请求失败：{e}", retryable=False)

async def get_adcode(city: str,AMAP_KEY:str,client):
    """
    辅助工具:
        weather_query_gaode来获取对应城市的adcode
    """
    url = "https://restapi.amap.com/v3/geocode/geo"

    params = {
        "key": AMAP_KEY,
        "address": city,
        "output": "JSON"
    }
    #发送get请求
    timeout = httpx.Timeout(get_settings().tool_timeout_seconds)
    response = await client.get(url,params=params)
    response.raise_for_status()

    data = response.json()

    if data.get("status") != "1":
        raise RuntimeError(
            f"高德API请求失败: {data.get('info')}"
        )

    geocodes = data.get("geocodes", [])

    if not geocodes:
        return None

    return geocodes[0]["adcode"]


async def route_planning(
    origin_loc: str,        #起点
    destination_loc: str,   #终点
    route_type: Literal["driving", "transit", "walking"] = "driving",   #出行方式
    origin_city: str | None = None,         #起点所在城市
    destination_city: str | None = None     #终点所在城市
) -> ToolResult:
    """
    出行路径规划工具
    Args:
        origin_loc:
            起点，例如："成都大学"
        destination_loc:
            终点，例如："成都东站"
        route_type:
            交通方式：
            driving  驾车
            transit  公交/地铁
            walking  步行
        origin_city:
            起点所在城市，例如："成都"
        destination_city:
            终点所在城市，例如："成都"
    """
    #获取高德地图api
    amap_key = get_settings().gaode_map_api

    if not amap_key:
        return ToolResult.failure(
            "CONFIG_MISSING",
            "未配置高德地图 API Key"
        )

    #获取起点和终点的经纬度信息
    origin_result, destination_result = await asyncio.gather(
        geocode(
            amap_key=amap_key,
            address=origin_loc,
            city=origin_city
        ),
        geocode(
            amap_key=amap_key,
            address=destination_loc,
            city=destination_city
        )
    )

    #判断起点终点编码是否成功
    if not origin_result.ok:
        return ToolResult.failure(
            "ORIGIN_GEOCODE_ERROR",
            f"起点地理编码失败：{origin_result.error_message}",
            retryable=False
        )

    if not destination_result.ok:
        return ToolResult.failure(
            "DESTINATION_GEOCODE_ERROR",
            f"终点地理编码失败：{destination_result.error_message}",
            retryable=False
        )
    #起点终点经纬度信息
    origin = origin_result.data["location"]
    destination = destination_result.data["location"]

    try:
        #根据交通方式请求不同接口
        #驾车
        if route_type == "driving":
            return await _driving_route(
                amap_key,
                origin_loc,
                destination_loc,
                origin,
                destination
            )
        #步行
        elif route_type == "walking":
            return await _walking_route(
                amap_key,
                origin_loc,
                destination_loc,
                origin,
                destination
            )
        #公共交通
        elif route_type == "transit":
            if not origin_city:
                return ToolResult.failure(
                    "CITY_REQUIRED",
                    "公交路径规划必须提供起点城市",
                    retryable=False
                )

            if not destination_city:
                destination_city = origin_city

            return await _transit_route(
                amap_key,
                origin_loc,
                destination_loc,
                origin,
                destination,
                origin_city,
                destination_city
            )

        return ToolResult.failure(
            "INVALID_ROUTE_TYPE",
            f"不支持的路径规划类型：{route_type}",
            retryable=False
        )

    except httpx.TimeoutException:
        return ToolResult.failure(
            "TIMEOUT",
            "高德路径规划请求超时",
            retryable=True
        )

    except httpx.HTTPError as e:
        return ToolResult.failure(
            "HTTP_ERROR",
            str(e),
            retryable=True
        )

    except Exception as e:
        return ToolResult.failure(
            "UNKNOWN_ERROR",
            str(e)
        )

async def _driving_route(
    amap_key: str,
    origin_name: str,
    destination_name: str,
    origin: str,
    destination: str
) -> ToolResult:
    """
    驾车路径规划
    """
    url = "https://restapi.amap.com/v5/direction/driving"

    params = {
        "key": amap_key,
        "origin": origin,
        "destination": destination,
        "show_fields": "cost"
    }

    data = await _request_amap(url, params)

    if not data.ok:
        return data

    route = data.data.get("route", {})

    paths = route.get("paths", [])

    if not paths:
        return ToolResult.failure(
            "NO_ROUTE",
            "没有找到可用驾车路线"
        )

    path = paths[0]

    steps = []

    for step in path.get("steps", []):

        steps.append({
            "instruction": step.get("instruction"),
            "road_name": step.get("road_name"),
            "orientation": step.get("orientation"),
            "distance": _to_int(
                step.get("step_distance")
            )
        })

    cost = path.get("cost", {})

    result = {
        "route_type": "driving",
        "origin_name": origin_name,
        "destination_name": destination_name,

        "origin": origin,
        "destination": destination,
        # 米
        "distance": _to_int(
            path.get("distance")
        ),
        # 秒
        "duration": _to_int(
            cost.get("duration")
        ),
        "traffic_lights": _to_int(
            cost.get("traffic_lights")
        ),
        "steps": steps
    }

    return ToolResult.success(result)

async def _walking_route(
    amap_key: str,
    origin_name: str,
    destination_name: str,
    origin: str,
    destination: str
) -> ToolResult:
    """
    步行路径规划
    """
    url = "https://restapi.amap.com/v5/direction/walking"

    params = {
        "key": amap_key,
        "origin": origin,
        "destination": destination,
        "show_fields": "cost"
    }

    data = await _request_amap(url, params)
    if not data.ok:
        return data
    route = data.data.get("route", {})
    paths = route.get("paths", [])
    if not paths:
        return ToolResult.failure(
            "NO_ROUTE",
            "没有找到可用步行路线"
        )
    path = paths[0]
    steps = []
    for step in path.get("steps", []):
        steps.append({
            "instruction": step.get("instruction"),
            "road_name": step.get("road_name"),
            "orientation": step.get("orientation"),
            "distance": _to_int(
                step.get("step_distance")
            )
        })
    result = {
        "route_type": "walking",
        "origin_name": origin_name,
        "destination_name": destination_name,
        "origin": origin,
        "destination": destination,
        "distance": _to_int(
            path.get("distance")
        ),
        "duration": _to_int(
            path.get("cost", {}).get("duration")
        ),
        "steps": steps
    }
    return ToolResult.success(result)

async def _transit_route(
    amap_key: str,
    origin_name: str,
    destination_name: str,
    origin: str,
    destination: str,
    origin_city: str,
    destination_city: str
) -> ToolResult:
    """
    公共交通路径规划
    """
    url = "https://restapi.amap.com/v5/direction/transit/integrated"

    params = {
        "key": amap_key,
        "origin": origin,
        "destination": destination,
        "city1": origin_city,
        "city2": destination_city
    }

    data = await _request_amap(url, params)
    if not data.ok:
        return data
    route = data.data.get("route", {})
    transits = route.get("transits", [])
    if not transits:
        return ToolResult.failure(
            "NO_ROUTE",
            "没有找到可用公交路线"
        )
    routes = []

    # 公交一般有多套方案
    for transit in transits:
        segments = []
        for segment in transit.get("segments", []):
            segment_data = {}
            # 步行
            walking = segment.get("walking")
            if walking:
                walking_steps = []
                for step in walking.get("steps", []):
                    walking_steps.append({
                        "instruction":
                            step.get("instruction"),
                        "road_name":
                            step.get("road_name"),
                        "distance":
                            _to_int(
                                step.get("step_distance")
                            )
                    })
                segment_data["walking"] = {
                    "distance":
                        _to_int(
                            walking.get("distance")
                        ),
                    "steps":
                        walking_steps
                }
            #公交/地铁
            bus = segment.get("bus")
            if bus:
                buslines = []
                for busline in bus.get(
                    "buslines",
                    []
                ):
                    buslines.append({
                        "name":
                            busline.get("name"),
                        "departure_stop":
                            busline.get(
                                "departure_stop"
                            ),
                        "arrival_stop":
                            busline.get(
                                "arrival_stop"
                            ),
                        "distance":
                            _to_int(
                                busline.get("distance")
                            ),
                        "duration":
                            _to_int(
                                busline.get("duration")
                            ),
                        "via_num":
                            _to_int(
                                busline.get("via_num")
                            ),
                        "via_stops":
                            busline.get(
                                "via_stops",
                                []
                            )
                    })
                segment_data["bus"] = {
                    "buslines": buslines
                }
            if segment_data:
                segments.append(segment_data)
        routes.append({
            "distance":
                _to_int(
                    transit.get("distance")
                ),
            "duration":
                _to_int(
                    transit.get(
                        "cost",
                        {}
                    ).get("duration")
                ),
            "walking_distance":
                _to_int(
                    transit.get(
                        "cost",
                        {}
                    ).get(
                        "walking_distance"
                    )
                ),
            "segments":
                segments
        })

    result = {
        "route_type": "transit",
        "origin_name": origin_name,
        "destination_name": destination_name,
        "origin": origin,
        "destination": destination,
        "routes": routes
    }

    return ToolResult.success(result)

async def geocode(
    amap_key: str,
    address: str,
    city: str | None = None
) -> ToolResult:
    """
    地点/地址 -> 经纬度
    """
    if not amap_key:
        return ToolResult.failure(
            "CONFIG_MISSING",
            "未配置高德地图 API Key"
        )
    url = "https://restapi.amap.com/v3/geocode/geo"
    params = {
        "key": amap_key,
        "address": address
    }
    if city:
        params["city"] = city
    try:
        data_result = await _request_amap(
            url,
            params
        )
        if not data_result.ok:
            return data_result
        data = data_result.data
        geocodes = data.get(
            "geocodes",
            []
        )
        if not geocodes:
            return ToolResult.failure(
                "LOCATION_NOT_FOUND",
                f"没有找到地点：{address}"
            )
        location_info = geocodes[0]
        location = location_info.get(
            "location"
        )
        if not location:
            return ToolResult.failure(
                "LOCATION_NOT_FOUND",
                f"地点没有返回经纬度：{address}"
            )
        longitude, latitude = location.split(",")
        result = {
            "address":
                address,
            "formatted_address":
                location_info.get(
                    "formatted_address"
                ),
            "location":
                location,
            "longitude":
                float(longitude),
            "latitude":
                float(latitude),
            "province":
                location_info.get(
                    "province"
                ),
            "city":
                location_info.get(
                    "city"
                ),
            "district":
                location_info.get(
                    "district"
                ),
            "adcode":
                location_info.get(
                    "adcode"
                ),
            "level":
                location_info.get(
                    "level"
                )
        }
        return ToolResult.success(result)

    except httpx.TimeoutException:
        return ToolResult.failure(
            "TIMEOUT",
            "高德地理编码请求超时",
            retryable=True
        )

    except httpx.HTTPError as e:
        return ToolResult.failure(
            "HTTP_ERROR",
            str(e),
            retryable=True
        )

    except Exception as e:
        return ToolResult.failure(
            "UNKNOWN_ERROR",
            str(e)
        )

async def _request_amap(
    url: str,
    params: dict
) -> ToolResult:
    """
    高德请求
    """
    async with httpx.AsyncClient(
        timeout=10
    ) as client:
        response = await client.get(
            url,
            params=params
        )
        response.raise_for_status()
        data = response.json()
    if data.get("status") != "1":
        return ToolResult.failure(
            "AMAP_ERROR",
            data.get(
                "info",
                "高德地图接口请求失败"
            )
        )
    return ToolResult.success(data)

# 安全转换 int
def _to_int(
    value
) -> int:

    try:
        return int(float(value or 0))

    except (ValueError, TypeError):
        return 0

if __name__ == "__main__":
    print(asyncio.run(route_planning('电子科技大学清水河校区','九寨贵')))
