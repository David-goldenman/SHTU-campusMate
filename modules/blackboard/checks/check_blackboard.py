import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from checks.module_support import load

package = load('blackboard')
reader = sys.modules[package.__name__ + '.reader']
at = datetime(2026,10,16,tzinfo=timezone.utc)
assert reader.availability({'available':'Yes'},at) == ('open',True)
assert reader.availability({'available':'Yes','adaptiveRelease':{'start':'2099-01-01T00:00:00Z'}},at) == ('scheduled',False)
assert reader.availability({'available':'Yes','adaptiveRelease':{'start':'bad-date'}},at) == ('unknown',None)
assert reader.availability(None,at) == ('unknown',None)
assert reader.activity('<div id="grades_wrapper"><div id="12" class="sortable_item_row submitted_item_row">Submitted</div><div id="13" class="sortable_item_row">未提交</div></div>') == {'_12_1':True,'_13_1':False}


class Tree:
    def pages(self,url):
        return iter([{'id':'_1_1','title':'合成文件夹','contentHandler':{'id':'resource/x-bb-folder'},'hasChildren':True}, {'id':'_2_1','title':'合成资料','contentHandler':{'id':'resource/x-bb-file'}}])


issues = []
nodes = reader.contents(Tree(),'_9_1',issues)
assert len(nodes) == 2 and issues
items = reader.materials(nodes,'_9_1')
assert len(items) == 1 and items[0]['download_url'].startswith('/api/v1/modules/blackboard/file?')
print('blackboard: availability windows, unknown states, submission evidence, cyclic folders and stable file paths passed')
