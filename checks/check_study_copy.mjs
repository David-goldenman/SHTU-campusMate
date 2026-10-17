import assert from 'node:assert/strict';
import {copyTopic, latestUserText, studyCopyText} from '../modules/academic-assistant/web/copy-context.js';

for (const [text,topic] of [
  ['请解释一下绩点和均绩','grades'],['Check my GPA','grades'],['How do I read my grades?','grades'],
  ['明天的作业快截止了','deadlines'],['Any upcoming deadlines?','deadlines'],['Homework is due tomorrow','deadlines'],
  ['帮我看下课程表和排课','timetable'],['Show my timetable','timetable'],['Plan my class schedule','timetable'],
  ['下一节课几点开始','timetable'],['下一堂课是什么','timetable'],['When is the next class?','timetable'],['Where is my next lecture?','timetable'],
  ['这份讲义和课程大纲','documents'],['Find the PDF lecture notes','documents'],['Read the syllabus','documents'],
  ['你好，今天聊点什么','general'],['I am an undergraduate student','general'],['Hello there','general'],
]) assert.equal(copyTopic(text),topic);
assert.equal(copyTopic('GPA deadline timetable PDF'),'grades');
for (const text of [null,undefined,{},[],42]) assert.equal(copyTopic(text),'general');
const history = [
  {role:'user',text:'Any upcoming deadlines?'},
  {role:'assistant',text:'Your GPA and grades are available'},
];
assert.equal(copyTopic(latestUserText(history)),'deadlines','Assistant output must never select the topic');
assert.equal(copyTopic(latestUserText([...history,{role:'user',text:'Read this PDF'},{role:'assistant',text:'Here is your timetable'}])),'documents');
assert.equal(copyTopic(latestUserText([{role:'assistant',text:'GPA'}])),'general');
assert.equal(copyTopic(latestUserText([{role:'system',text:'成绩'}])),'general');
assert.equal(latestUserText([{role:'user',text:'GPA'},{role:'user',text:''}]),'');
assert.equal(latestUserText([]),'');
assert.equal(latestUserText(null),'');
assert.equal(copyTopic(studyCopyText(history,'Read my PDF draft')),'documents','A restored draft takes precedence over previous conversation context');
assert.equal(copyTopic(studyCopyText(history,'你好')),'general','An explicit unknown draft does not inherit an old topic');
assert.equal(copyTopic(studyCopyText(history,'   ')),'deadlines','Empty drafts use the latest user message');
assert.equal(copyTopic(studyCopyText([],'')),'general','A new empty conversation clears the previous topic');
console.log('study copy: explicit Chinese/English topics, next class, restored drafts and assistant exclusion passed');
