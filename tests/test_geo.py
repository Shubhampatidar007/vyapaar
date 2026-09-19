"""Haversine + GeoJSON tests."""
import pytest

from app.utils.geo import (
    from_geojson_point, haversine_meters, humanize_distance, to_geojson_point, valid_coordinates,
)


def test_zero_distance():
    assert haversine_meters(24.0, 75.0, 24.0, 75.0) == pytest.approx(0.0, abs=1e-6)


def test_known_distance_delhi_mumbai():
    # Delhi -> Mumbai is roughly 1150 km.
    distance = haversine_meters(28.6139, 77.2090, 19.0760, 72.8777)
    assert 1_130_000 < distance < 1_180_000


def test_short_distance_is_accurate():
    # ~0.001 degrees of latitude is about 111 metres.
    distance = haversine_meters(24.0734, 75.0686, 24.0744, 75.0686)
    assert distance == pytest.approx(111.2, abs=2.0)


def test_symmetry():
    a = haversine_meters(24.0, 75.0, 24.5, 75.5)
    b = haversine_meters(24.5, 75.5, 24.0, 75.0)
    assert a == pytest.approx(b)


def test_geojson_orders_longitude_first():
    point = to_geojson_point(24.0734, 75.0686)
    assert point["type"] == "Point"
    assert point["coordinates"] == [75.0686, 24.0734]


def test_geojson_roundtrip():
    latitude, longitude = from_geojson_point(to_geojson_point(24.0734, 75.0686))
    assert (latitude, longitude) == (24.0734, 75.0686)


def test_from_geojson_handles_none():
    assert from_geojson_point(None) is None
    assert from_geojson_point({"coordinates": [1]}) is None


def test_valid_coordinates():
    assert valid_coordinates(24.0, 75.0)
    assert not valid_coordinates(91.0, 75.0)
    assert not valid_coordinates(24.0, 181.0)


def test_humanize_distance():
    assert humanize_distance(203) == "~200m"
    assert humanize_distance(1500) == "~1.5km"
