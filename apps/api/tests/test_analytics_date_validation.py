from datetime import date,timedelta
import pytest
from fastapi import HTTPException
from app.analytics_routes import validate_dates

def test_default_range_is_28_days():
 start,end=validate_dates(None,date.today()-timedelta(days=1))
 assert (end-start).days==27

def test_rejects_future_or_today_end():
 with pytest.raises(HTTPException): validate_dates(None,date.today())

def test_rejects_inverted_range():
 with pytest.raises(HTTPException): validate_dates(date(2026,11,20),date(2026,11,10))

def test_rejects_range_over_one_year():
 with pytest.raises(HTTPException): validate_dates(date(2025,1,1),date.today()-timedelta(days=1))
