"""Read-only adapter for the public 12306 website (not a supported official API)."""

import asyncio
import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal

import httpx

from config import get_settings
from models.results import ToolResult

BASE = "https://kyfw.12306.cn/otn/"
CHINA = timezone(timedelta(hours=8))
SEATS = {21: "高级软卧", 23: "软卧/一等卧", 24: "软座", 25: "特等座",
         26: "无座", 28: "硬卧/二等卧", 29: "硬座", 30: "二等座",
         31: "一等座", 32: "商务座"}


def _clock(value: str) -> int:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("时间必须为 HH:mm，范围 00:00—23:59")
    h, m = map(int, value.split(":"))
    return h * 60 + m


def _stations(text: str) -> dict[str, str]:
    result = {}
    for record in text.split("@")[1:]:
        fields = record.split("|")
        if len(fields) >= 3 and re.fullmatch(r"[A-Z]{3}", fields[2]):
            result[fields[1]] = fields[2]
    if not result:
        raise ValueError("12306 车站字典格式发生变化")
    return result


def _parse_row(raw: str, travel_day: date, names: dict[str, str]) -> dict:
    fields = raw.split("|")
    if len(fields) < 33 or not fields[3] or not re.fullmatch(r"\d{2,3}:[0-5]\d", fields[10]):
        raise ValueError("12306 车次数据格式发生变化")
    departure = _clock(fields[8])
    _clock(fields[9])
    hours, minutes = map(int, fields[10].split(":"))
    duration = hours * 60 + minutes
    start = datetime.combine(travel_day, datetime.min.time(), CHINA) + timedelta(minutes=departure)
    arrival = start + timedelta(minutes=duration)
    if arrival.strftime("%H:%M") != fields[9]:
        raise ValueError("12306 到达时间与历时不一致")
    if fields[6] not in names or fields[7] not in names:
        raise ValueError("12306 返回了未知车站代码")
    return {
        "train_number": fields[3],
        "from_station": names[fields[6]], "from_code": fields[6],
        "to_station": names[fields[7]], "to_code": fields[7],
        "departure_at": start.isoformat(), "arrival_at": arrival.isoformat(),
        "arrival_day_offset": (arrival.date() - travel_day).days,
        "duration_minutes": duration,
        "seats": {name: fields[index] or "--" for index, name in SEATS.items()},
        "booking_available": fields[11] == "Y",
    }


async def query_train_tickets(
    from_station: str,
    to_station: str,
    travel_date: str,
    departure_start: str = "00:00",
    departure_end: str = "23:59",
    train_types: str = "",
    sort_by: Literal["departure", "duration"] = "departure",
    limit: int = 20,
) -> ToolResult:
    """查询指定车站间的直达列车，供行程规划使用，不购票、不查中转或票价。

    from_station/to_station 必须为准确车站名（如北京南、上海虹桥）或三字母电报码，
    不自动扩展同城车站。travel_date 为北京时间乘车日期 YYYY-MM-DD；相对日期先查当前时间。
    departure_start/end 为同一天发车时间范围 HH:mm。train_types 为空表示全部，或 G,D,C,Z,T,K,S,Y,L 等逗号分隔；P 表示纯数字普快。
    sort_by 为 departure（最早出发）或 duration（最短历时），limit 为 1—50。
    保留无票车次；余票是查询时快照，-- 表示未知或不适用。失败不能解释为无车次。
    可结合高德 route_planning 规划到站和离站交通，但必须预留进站、检票和换乘时间。
    """
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", travel_date):
            raise ValueError("日期必须为 YYYY-MM-DD")
        day = date.fromisoformat(travel_date)
        if day < datetime.now(CHINA).date():
            raise ValueError("不能查询过去的乘车日期")
        lower, upper = _clock(departure_start), _clock(departure_end)
        types = {item.strip().upper() for item in train_types.split(",") if item.strip()}
        if lower > upper or sort_by not in {"departure", "duration"} or not 1 <= limit <= 50:
            raise ValueError("检查时间范围、sort_by 和 limit（1—50）")
        if types - set("GDCZTKSYLP"):
            raise ValueError("不支持的车次类型，请使用 G,D,C,Z,T,K,S,Y,L,P")
        if not from_station.strip() or not to_station.strip():
            raise ValueError("出发站和到达站不能为空")
    except (ValueError, TypeError) as exc:
        return ToolResult.failure("INVALID_ARGUMENT", str(exc))

    async def fetch():
        async with httpx.AsyncClient(timeout=8, follow_redirects=False,
                                     headers={"Referer": BASE + "leftTicket/init"}) as client:
            station_response = await client.get(BASE + "resources/js/framework/station_name.js")
            station_response.raise_for_status()
            stations = _stations(station_response.text)
            names = {code: name for name, code in stations.items()}
            codes = []
            for value in (from_station.strip(), to_station.strip()):
                code = stations.get(value, value.upper())
                if code not in names:
                    candidates = [name for name in stations if value in name][:10]
                    return ToolResult.failure("STATION_NOT_FOUND", f"未知车站：{value}。请指定准确车站名。候选：{candidates}")
                codes.append(code)
            if codes[0] == codes[1]:
                return ToolResult.failure("INVALID_ARGUMENT", "出发站和到达站不能相同")
            page = await client.get(BASE + "leftTicket/init")
            page.raise_for_status()
            match = re.search(r'''CLeftTicketUrl\s*=\s*["'](leftTicket/query[A-Za-z]*)["']''', page.text)
            if not match:
                raise ValueError("12306 页面缺少查询接口信息，可能受限或页面已变更")
            response = await client.get(BASE + match.group(1), params={
                "leftTicketDTO.train_date": travel_date,
                "leftTicketDTO.from_station": codes[0],
                "leftTicketDTO.to_station": codes[1], "purpose_codes": "ADULT",
            })
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("status") is not True:
                return ToolResult.failure("UPSTREAM_REJECTED", "12306 未接受查询，请在官方页面核验日期或稍后重试")
            data = payload.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("result"), list):
                raise ValueError("12306 返回的数据结构不符合预期")
            rows = [_parse_row(row, day, names) for row in data["result"]]
            # Exact stations only: do not silently substitute nearby stations.
            rows = [r for r in rows if r["from_code"] == codes[0] and r["to_code"] == codes[1]]
            total = len(rows)
            rows = [r for r in rows if lower <= _clock(r["departure_at"][11:16]) <= upper
                    and (not types or (r["train_number"][0] if r["train_number"][0].isalpha() else "P") in types)]
            rows.sort(key=lambda r: (r["duration_minutes"], r["departure_at"]) if sort_by == "duration" else (r["departure_at"], r["duration_minutes"]))
            return ToolResult.success({
                "source": BASE + "leftTicket/init", "queried_at": datetime.now(CHINA).isoformat(),
                "travel_date": travel_date, "from_station": names[codes[0]], "to_station": names[codes[1]],
                "total_direct": total, "total_matched": len(rows), "returned": min(limit, len(rows)),
                "trains": rows[:limit],
                "notice": "仅供行程参考，余票随时变化；空结果不代表线路不存在，也可能尚未开售。请在12306核验。无票车次仍保留；不含票价和中转方案。",
            })

    try:
        return await asyncio.wait_for(fetch(), timeout=max(1, get_settings().tool_timeout_seconds - 1))
    except (asyncio.TimeoutError, httpx.TimeoutException):
        return ToolResult.failure("TRAIN_QUERY_TIMEOUT", "12306 查询超时，请稍后重试", retryable=True)
    except httpx.HTTPError:
        return ToolResult.failure("TRAIN_NETWORK_ERROR", "无法访问12306（网络、TLS、限流或服务异常），请使用官方页面核验", retryable=True)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return ToolResult.failure("TRAIN_RESPONSE_ERROR", f"12306 响应无法解析：{exc}")
