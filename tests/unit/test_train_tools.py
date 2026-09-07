import asyncio
from datetime import datetime, timedelta

import httpx
import pytest

from LLMTools import train_tools as tool


DAY = (datetime.now(tool.CHINA).date() + timedelta(days=1)).isoformat()


def row(number="G1", departure="23:00", arrival="01:00", duration="02:00"):
    fields = [""] * 40
    for index, value in {3: number, 6: "VNP", 7: "AOH", 8: departure,
                         9: arrival, 10: duration, 11: "N", 30: "无"}.items():
        fields[index] = value
    return "|".join(fields)


def install(monkeypatch, payload=None, mode="normal"):
    original = httpx.AsyncClient
    calls = []

    def handler(request):
        calls.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if request.url.path.endswith("station_name.js"):
            return httpx.Response(200, text="var station_names ='@bjn|北京南|VNP|x@shhq|上海虹桥|AOH|x';")
        if request.url.path.endswith("/init"):
            return httpx.Response(200, text='var CLeftTicketUrl = "leftTicket/queryG";' if mode != "blocked" else "verification required")
        assert request.url.params["leftTicketDTO.from_station"] == "VNP"
        assert request.url.params["leftTicketDTO.train_date"] == DAY
        return httpx.Response(200, json=payload if payload is not None else {"status": True, "data": {"result": [row()]}})

    monkeypatch.setattr(tool.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return calls


def query(**kwargs):
    return asyncio.run(tool.query_train_tickets("北京南", "上海虹桥", DAY, **kwargs))


def test_overnight_and_sold_out(monkeypatch):
    install(monkeypatch)
    result = query()
    assert result.ok
    train = result.data["trains"][0]
    assert train["arrival_day_offset"] == 1
    assert train["duration_minutes"] == 120
    assert train["seats"]["二等座"] == "无"
    assert train["booking_available"] is False
    assert train["departure_at"].endswith("+08:00")


def test_filter_sort_limit(monkeypatch):
    install(monkeypatch, {"status": True, "data": {"result": [
        row("G2", "08:00", "12:00", "04:00"), row("D1", "09:00", "10:00", "01:00"),
        row("G3", "10:00", "12:00", "02:00")]}})
    result = query(train_types="G", sort_by="duration", limit=1, departure_end="20:00")
    assert result.data["total_matched"] == 2
    assert result.data["trains"][0]["train_number"] == "G3"


@pytest.mark.parametrize("kwargs", [{"departure_start": "24:00"}, {"limit": 0},
    {"train_types": "A"}, {"sort_by": "price"}, {"departure_start": "18:00", "departure_end": "08:00"}])
def test_invalid_arguments(kwargs):
    assert query(**kwargs).error_code == "INVALID_ARGUMENT"


@pytest.mark.parametrize("mode,code", [("timeout", "TRAIN_QUERY_TIMEOUT"), ("blocked", "TRAIN_RESPONSE_ERROR")])
def test_network_failures(monkeypatch, mode, code):
    install(monkeypatch, mode=mode)
    assert query().error_code == code


@pytest.mark.parametrize("payload,expected", [
    ({"status": True, "data": {"result": []}}, None),
    ({"status": False}, "UPSTREAM_REJECTED"),
    ({"status": True, "data": {}}, "TRAIN_RESPONSE_ERROR"),
    ({"status": True, "data": {"result": ["bad"]}}, "TRAIN_RESPONSE_ERROR"),
])
def test_upstream_responses(monkeypatch, payload, expected):
    install(monkeypatch, payload)
    result = query()
    assert result.error_code == expected
    if expected is None:
        assert result.data["trains"] == []


def test_unknown_station(monkeypatch):
    calls = install(monkeypatch)
    result = asyncio.run(tool.query_train_tickets("北京", "上海虹桥", DAY))
    assert result.error_code == "STATION_NOT_FOUND"
    assert "北京南" in result.error_message
    assert len(calls) == 1


def test_past_date():
    assert asyncio.run(tool.query_train_tickets("北京南", "上海虹桥", "2000-01-01")).error_code == "INVALID_ARGUMENT"
