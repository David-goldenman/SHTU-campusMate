import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from fastapi import HTTPException
from backend.services.campus.analysis import account_revision
from checks.module_support import load, sandbox

package = load('academic-assistant')
Conversations = sys.modules[package.__name__ + '.conversations'].Conversations
with sandbox('academic-assistant') as context:
    owner = account_revision(context)
    pair = [{'role':'user','text':'合成的旧问题','created_at':'2026-10-17T08:00:00Z'}, {'role':'assistant','text':'旧回复','created_at':'2026-10-17T08:01:00Z'}]
    context.store.write('chat:' + owner, pair)
    chats = Conversations(context)
    first = chats.index()['active_id']
    assert len(chats.index()['items']) == 1 and chats.messages(first) == pair
    second = chats.create()['id']
    chats.append(second, [{**pair[0], 'text':'另一段问题'},pair[1]])
    chats.select(first)
    assert Conversations(context).index()['active_id'] == first
    assert Conversations(context).messages(second)[0]['text'] == '另一段问题'
    chats.update(first, {'archived':True})
    assert chats.select(first)['conversation']['archived'] is True
    context.auth.revision = 'other-account'
    assert chats.index()['items'] == []
    try:
        chats.select(first)
        raise AssertionError('Cross-account conversation access')
    except HTTPException as error:
        assert error.status_code == 404
    context.auth.revision = 'synthetic-account-one'
    chats.delete(first)
    assert context.store.read('chat:' + owner) is None
    assert chats.index()['active_id'] == second
    chats.delete(second)
    assert Conversations(context).index() == {'items':[], 'active_id':None}
print('conversations: legacy migration, selection, archive, restart persistence, deletion and account isolation passed')

import asyncio
import httpx
Task = sys.modules[package.__name__ + '.tools'].Task
Attend = sys.modules[package.__name__ + '.models'].Attend
with sandbox('academic-assistant') as context:
    accepted = []
    async def api(module,path,**kwargs):
        assert module == 'campus-agent' and path == '/proposals/p1/accept' and kwargs['method'] == 'POST'
        accepted.append(path)
        return httpx.Response(200,json={'id':'p1','state':'accepted'})
    context.api = api
    task = Task(context, '我确认参加这场活动')
    task.references['notice:1'] = {'proposal_id':'p1'}
    assert asyncio.run(task.attend(Attend(proposal_id='p1',quote=task.message)))['items']
    for message, quote, reference in [
        ('如果我参加这场活动', '如果我参加这场活动', True),
        ('如果我参加这场活动会怎样？', '我参加这场活动', True),
        ('不要把这场活动加入日程', '把这场活动加入日程', True),
        ('我不想参加这场活动', '参加这场活动', True),
        ('我参加这场活动的话，需要准备什么？', '我参加这场活动', True),
        ('我参加这场活动可以吗？', '我参加这场活动', True),
        ('别人说“我确认参加这场活动”', '我确认参加这场活动', True),
        ('我确认参加这场活动', '我确认参加这场活动', False),
    ]:
        rejected = Task(context,message)
        if reference:
            rejected.references = task.references
        try:
            asyncio.run(rejected.attend(Attend(proposal_id='p1',quote=quote)))
            raise AssertionError('Attendance requires current explicit consent and a read proposal')
        except HTTPException as error:
            assert error.status_code == 422
        assert len(accepted) == 1, 'Rejected intent must not send a proposal acceptance request'
    command = Task(context, '请帮我把这场活动加入日程。')
    command.references = task.references
    assert asyncio.run(command.attend(Attend(proposal_id='p1',quote='把这场活动加入日程')))['items']
    assert len(accepted) == 2, 'A direct calendar command still works with an exact excerpt'
    positive = Task(context, '讲座内容不错，我确认参加这场活动。')
    positive.references = task.references
    assert asyncio.run(positive.attend(Attend(proposal_id='p1',quote='我确认参加这场活动')))['items']
    assert len(accepted) == 3, 'Unrelated positive context must not be treated as a negation of attendance'
print('study attendance: explicit current intent and read-proposal boundaries passed')
