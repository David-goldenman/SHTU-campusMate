"""Account-scoped, versioned local road-condition maintenance; no background jobs."""
from copy import deepcopy
from datetime import date, datetime
from threading import RLock
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.services.campus.accounts import AccountCache

ZONE = ZoneInfo('Asia/Shanghai')


class Condition(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=2, max_length=80)
    state: Literal['pending', 'confirmed', 'resolved', 'withdrawn'] = 'pending'
    effect: Literal['blocked', 'caution'] = 'blocked'
    scope: Literal['place', 'edges', 'area']
    place_id: str = Field(default='', max_length=100)
    edge_keys: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=100)
    bounds: list[float] = Field(default_factory=list, max_length=4)
    starts_on: date
    expected_end: date | None = None
    review_on: date
    source_kind: Literal['official', 'onsite', 'report'] = 'report'
    source_title: str = Field(min_length=2, max_length=160)
    source_date: date
    source_url: str = Field(default='', max_length=1500)
    note: str = Field(min_length=2, max_length=800)

    @model_validator(mode='after')
    def validate_evidence(self):
        if self.expected_end and self.expected_end < self.starts_on:
            raise ValueError('预计结束日期不能早于开始日期。')
        if self.review_on < self.source_date:
            raise ValueError('复核日期不能早于来源日期。')
        if self.source_url:
            url = urlsplit(self.source_url)
            if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
                raise ValueError('来源链接须为不含登录信息的 HTTP(S) 地址。')
        if self.source_kind == 'official' and not self.source_url:
            raise ValueError('校方通知需要填写原文链接。')
        if self.state in {'confirmed', 'resolved'} and self.source_kind == 'report':
            raise ValueError('确认限制或恢复通行需要校方通知或现场核实依据；转述线索请保留待核实。')
        if self.scope == 'place' and (not self.place_id or self.edge_keys or self.bounds):
            raise ValueError('请选择一个校门或建筑。')
        if self.scope == 'edges' and (not self.edge_keys or self.place_id or self.bounds):
            raise ValueError('请在地图选择受影响的道路。')
        if self.scope == 'area' and (len(self.bounds) != 4 or self.place_id or self.edge_keys):
            raise ValueError('请在地图圈选施工区域。')
        return self


class Version(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0)
    account_revision: str = Field(min_length=1, max_length=100)


class Change(Version):
    item: Condition


def edge_key(way, a, b):
    return str(way) + ':' + ':'.join(sorted((str(a), str(b))))


def create_conditions_router(context, places, network, seeds):
    router, cache, lock = APIRouter(), AccountCache(context, 'ids'), RLock()
    place_ids = {b['id'] for b in places['buildings']}
    keys = {edge_key(w['id'], a, b) for w in network['ways'] for a, b in zip(w['refs'], w['refs'][1:])}
    points = places['campus']['polygon']
    campus_box = (min(p[0] for p in points) - .001, min(p[1] for p in points) - .001,
                  max(p[0] for p in points) + .001, max(p[1] for p in points) + .001)

    def read(captured):
        return deepcopy(captured.store.read('conditions', {'version': 0, 'items': seeds, 'history': []}))

    def output(captured, state):
        cache.check(captured)
        return {'version': state['version'], 'account_revision': captured.account_owner,
                'items': state['items'], 'history': [{k: h[k] for k in ('version', 'id', 'title', 'action', 'at')} for h in reversed(state['history'])],
                'checked_at': datetime.now(ZONE).isoformat(), 'history_limit': 200,
                'undo_available': any(h['action'] != '撤销上次修改' and not h.get('undone') for h in state['history']),
                'baseline': network.get('retrieved_at'), 'local_only': True}

    def capture(body):
        captured = cache.capture()
        if captured.account_owner != body.account_revision:
            raise HTTPException(409, '账号已切换，请刷新维护记录后重试。')
        state = read(captured)
        if state['version'] != body.version:
            raise HTTPException(409, '维护记录已在其他页面更新，请刷新后再保存。')
        return captured, state

    def validate_target(item):
        if item.scope == 'place' and item.place_id not in place_ids:
            raise HTTPException(422, '地点已不在当前地图中，请重新选择。')
        if item.scope == 'edges' and (len(set(item.edge_keys)) != len(item.edge_keys) or any(k not in keys for k in item.edge_keys)):
            raise HTTPException(422, '部分道路已变化，请在当前地图重新选路。')
        if item.scope == 'area':
            x1, y1, x2, y2 = item.bounds
            if not (campus_box[0] <= x1 < x2 <= campus_box[2] and campus_box[1] <= y1 < y2 <= campus_box[3]):
                raise HTTPException(422, '圈选区域必须位于校园地图范围内。')
            if (x2 - x1) * (y2 - y1) < 1e-11:
                raise HTTPException(422, '圈选区域太小，请重新圈选。')

    def save(captured, state, item, before, action, undoes=None):
        now = datetime.now(ZONE).isoformat()
        state['version'] += 1
        item.update(updated_at=now, revision=state['version'])
        state['items'] = [old for old in state['items'] if old['id'] != item['id']] + [item]
        state['history'].append({'version': state['version'], 'id': item['id'], 'title': item['title'],
                                 'action': action, 'at': now, 'before': before, 'undoes': undoes})
        state['history'] = state['history'][-200:]
        cache.check(captured)
        captured.store.write('conditions', state)
        return output(captured, state)

    @router.get('/conditions')
    def list_conditions():
        with lock:
            captured = cache.capture()
            return output(captured, read(captured))

    @router.post('/conditions', status_code=201)
    def add_condition(body: Change):
        with lock:
            captured, state = capture(body)
            if sum(v['state'] in {'pending', 'confirmed'} for v in state['items']) >= 300:
                raise HTTPException(409, '进行中的记录已达 300 条，请先复核并结束旧记录。')
            validate_target(body.item)
            item = body.item.model_dump(mode='json')
            item.update(id=uuid4().hex, created_at=datetime.now(ZONE).isoformat())
            return save(captured, state, item, None, '新增')

    @router.put('/conditions/{identity}')
    def update_condition(identity: str, body: Change):
        with lock:
            captured, state = capture(body)
            before = next((v for v in state['items'] if v['id'] == identity), None)
            if not before:
                raise HTTPException(404, '维护记录不存在。')
            if before['state'] == 'confirmed' and body.item.state == 'pending':
                raise HTTPException(422, '已确认限制不能直接改成待核实；请根据新依据确认恢复或撤回错误记录。')
            if before['state'] != 'resolved' and body.item.state == 'resolved' and all(
                    str(getattr(body.item, key) or '') == str(before.get(key) or '')
                    for key in ('note', 'source_title', 'source_date', 'source_url')):
                raise HTTPException(422, '确认恢复前请补充新的核实说明或恢复通行依据。')
            validate_target(body.item)
            item = {**body.item.model_dump(mode='json'), 'id': identity, 'created_at': before['created_at']}
            return save(captured, state, item, before, '修改 / 复核')

    @router.post('/conditions/undo')
    def undo_condition(body: Version):
        with lock:
            captured, state = capture(body)
            last = next((h for h in reversed(state['history']) if h['action'] != '撤销上次修改' and not h.get('undone')), None)
            if not last:
                raise HTTPException(409, '没有可撤销的本地修改。')
            last['undone'] = True
            current = next(v for v in state['items'] if v['id'] == last['id'])
            restored = deepcopy(last['before']) if last['before'] else {**current, 'state': 'withdrawn'}
            return save(captured, state, restored, current, '撤销上次修改', last['version'])

    return router
