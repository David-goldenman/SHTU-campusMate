"""An uncertain attendance requirement must not erase verified activity dates."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from checks.module_support import load

package=load('mail')
window=sys.modules[package.__name__+'.event_window'].event_window
quote='时间:2026年10月19日周一14:00-15:00\n地点:合成报告厅'
item={'received_at':'2026-10-16T12:00:00+08:00','body_text':quote}
review={'fingerprint':'v1','input_revision':'v1','review_pending':False,'needs_check':True,
        'event':{'title':'合成消防培训','event_type':'lecture','starts_at':'2026-10-19T14:00:00+08:00','ends_at':'2026-10-19T15:00:00+08:00','quote':quote}}
assert window(item,review)['expires_at']=='2026-10-19T15:00:00+08:00'
assert window({**item,'body_text':quote+'\n同日16:00—17:00有另一场演练。'},review)['expires_at']=='2026-10-20T00:00:00+08:00'
assert window({**item,'body_text':quote+'\n另有2026年10月22日16:00的活动。'},review) is None
split='演练时间\n2026\n年\n10\n月\n19\n日（星期一）\n16:00\n—\n17:00'
other={**review,'event':{**review['event'],'starts_at':'2026-10-19T16:00:00+08:00','ends_at':'2026-10-19T17:00:00+08:00','quote':split}}
assert window({**item,'body_text':split},other)['expires_at']=='2026-10-19T17:00:00+08:00'
noend={**review,'event':{**review['event'],'ends_at':None}}
assert window(item,noend)['basis']=='event_day_end'
utc={**review,'event':{**review['event'],'starts_at':'2026-10-19T06:00:00Z','ends_at':'2026-10-19T07:00:00Z'}}
assert window(item,utc)['expires_at']=='2026-10-19T15:00:00+08:00'
for change in ({'review_pending':True},{'input_revision':'v2'},{'fingerprint':None}):
    assert window(item,{**review,**change}) is None
for change in ({'starts_at':'2026-10-20T14:00:00+08:00'},{'starts_at':'2026-10-19T14:00:00'},
               {'ends_at':'2026-10-19T13:00:00+08:00'},{'ends_at':'2026-10-19T18:00:00+08:00'},{'quote':'虚构日期和时间'}):
    assert window(item,{**review,'event':{**review['event'],**change}}) is None
deadline='报名问卷截止：2026年10月19日14:00-15:00'
assert window({**item,'body_text':deadline},{**review,'event':{**review['event'],'quote':deadline}}) is None
combined='报名截止：2026年10月18日12:00。'+quote
assert window({**item,'body_text':combined},{**review,'event':{**review['event'],'quote':combined}})['expires_at']=='2026-10-19T15:00:00+08:00'
assert review['needs_check'] and review['event']['quote']==quote
print('mail event windows: attendance uncertainty, source-grounded dates, fragmented text, timezone, multi-session/day, no-end and stale/deadline guards passed')
