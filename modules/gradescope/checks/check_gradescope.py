import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load
from backend.services.campus import SourceError

package = load('gradescope')
reader = sys.modules[package.__name__ + '.reader']
page = '''<div id="account-show"><h3 class="courseList--term">Fall 2026</h3><div><a class="courseBox" href="/courses/101"><span class="courseBox--name">合成课程</span><span class="courseBox--shortname">CS 100</span></a></div></div>'''
assert reader.courses(page)[0]['semester'] == '2026-fall'
table = '''<table id="assignments-student-table"><tbody>
<tr><td class="table--primaryLink"><button data-assignment-id="202">合成作业</button></td><td class="submissionStatus">No Submission</td><td><time class="submissionTimeChart--dueDate" datetime="2026-10-20T12:00:00+08:00"></time></td></tr>
<tr><td class="table--primaryLink">未来作业</td><td class="submissionStatus">No Submission</td><td><time class="submissionTimeChart--releaseDate" datetime="2099-10-20T12:00:00+08:00"></time></td></tr>
<tr><td class="table--primaryLink"><a href="/courses/101/assignments/203/submissions/1">已评分作业</a></td><td class="submissionStatus"><span class="submissionStatus--score">9 / 10</span></td></tr>
</tbody></table>'''
items = reader.assignments(table,101,[])
assert items[0]['actionable'] is True and items[0]['submitted'] is False
assert items[1]['source_id'] is None and items[1]['availability'] == 'scheduled' and items[1]['actionable'] is False
assert items[2]['submitted'] is True and items[2]['score'] == 9
props = {'assignment':{'submission_allowed':False,'template_url':'https://production-gradescope-uploads.s3-us-west-2.amazonaws.com/statement.pdf'}, 'questions':[]}
detail = '<div data-react-class="AssignmentSubmissionViewer" data-react-props="' + html.escape(json.dumps(props),quote=True) + '"></div>'
result = reader.enrich(items[0],detail)
assert result['availability'] == 'closed' and result['materials'][0]['download_url'].startswith('/api/v1/modules/gradescope/file?')
props['assignment']['submission_allowed'] = 'unknown'
detail = '<div data-react-class="AssignmentSubmissionViewer" data-react-props="' + html.escape(json.dumps(props),quote=True) + '"></div>'
assert reader.enrich(items[2],detail)['actionable'] is None
try:
    reader.courses('<html>maintenance</html>')
    raise AssertionError('Changed pages must retain cache')
except SourceError:
    pass
print('gradescope: terms, scheduled assignments, tri-state submissions, detail capability and stable file routes passed')
