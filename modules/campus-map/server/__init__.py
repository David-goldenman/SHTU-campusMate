import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from backend.services.campus.analysis import account_revision
from .conditions import create_conditions_router
from .discovery import Discovery

_discovery = None

ZONE = ZoneInfo('Asia/Shanghai')
FIELDS = ('id', 'title', 'course_title', 'event_type', 'source', 'start_time', 'at', 'starts_at', 'ends_at',
          'date', 'period_start', 'period_end', 'status', 'location', 'all_day')


def create_router(context):
    global _discovery
    router = APIRouter()
    places = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'places.json').read_text(encoding='utf-8'))
    places['basemap'] = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'osm-basemap.json').read_text(encoding='utf-8'))
    walking = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'walking-network.json').read_text(encoding='utf-8'))
    leads = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'condition-leads.json').read_text(encoding='utf-8'))
    _discovery = Discovery(context, places)
    router.include_router(create_conditions_router(context, places, walking, leads, _discovery))
    router.include_router(_discovery.router())

    @router.get('/places')
    def public_places():
        return places

    @router.get('/walking-network')
    def walking_network():
        return walking

    @router.get('/day')
    async def day(date: date | None = None):
        selected = date or datetime.now(ZONE).date()
        owner = account_revision(context)
        response = await context.api('timetable', '/schedule?week_start=' + selected.isoformat())
        if owner != account_revision(context):
            raise HTTPException(409, '账号已切换，请重新读取当天安排。')
        if response.status_code != 200:
            return {'date': selected.isoformat(), 'available': False, 'events': [],
                    'issues': ['时间表模块未启用或暂时不可用，校园地图仍可查看。']}
        snapshot = response.json()
        calendar = snapshot.get('calendar', {})
        selected_day = next((item for item in calendar.get('days', []) if item['date'] == selected.isoformat()), {})
        events = [{field: item[field] for field in FIELDS if field in item}
                  for item in selected_day.get('events', []) if item.get('status') not in {'cancel', 'leave', 'moved'}]
        return {'date': selected.isoformat(), 'available': True, 'events': events,
                'status': snapshot.get('status'), 'updated_at': snapshot.get('updated_at'),
                'issues': snapshot.get('data', {}).get('issues', []),
                'week_one': calendar.get('week_one')}

    return router


def start(context):
    if _discovery:
        _discovery.start()


def stop(context):
    if _discovery:
        _discovery.close()
