import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from checks.module_support import load

package = load('dashboard')
data = {'courses':[{'id':'current','current':True,'course_ids':['x:1']},{'id':'old','current':False,'course_ids':['x:2']}], 'materials':[{'course_id':'x:1'},{'course_id':'x:2'}], 'metadata':{'source_metadata':{'one':{'status':'ready'},'two':{'status':'error'}}}}
result = package.summarize(data,[{'id':'a','due_at':'2026-10-01'},{'id':'b','due_at':None}],[{'id':'read','read':True},{'id':'unread','read':False}])
assert result['stats'] == {'courses':1,'pending':2,'materials':1,'ready_sources':1}
assert len(result['upcoming']) == 1 and [item['id'] for item in result['notifications']] == ['unread']
print('dashboard: current-course statistics, known deadlines, partial sources and unread notices passed')
