import React from 'react';
import {Easing,interpolate,useCurrentFrame} from 'remotion';
import chats from '../production/group-chats.json';

const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
function Glyph({kind}:{kind:'chat'|'people'|'folder'|'smile'|'cut'}){
  const paths={chat:'M4 4h16v12H9l-5 4V4Z',people:'M16 20v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M10 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8M17 4a4 4 0 0 1 0 8M20 20v-2a4 4 0 0 0-3-3.87',folder:'M3 7V4h7l2 3h9v13H3V7Z',smile:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM8 9h.01M16 9h.01M8 14q4 5 8 0',cut:'M21 3 8 16M21 21 8 8M9 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z'};
  return <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d={paths[kind]}/></svg>;
}
function Avatar({label,tone='student'}:{label:string;tone?:string}){
  return <span className={'chat-avatar '+tone}><svg viewBox="0 0 40 40"><circle cx="20" cy="14" r="7"/><path d="M7 38v-5a13 13 0 0 1 26 0v5Z"/></svg><small>{label}</small></span>;
}
export function ChatSources(){
  const frame=useCurrentFrame();
  return <div className="product-stage chat-sources">{chats.map((chat,index)=>{
    const enter=interpolate(frame,[index*28,44+index*28],[0,1],{...clamp,easing:Easing.bezier(.22,.8,.2,1)});
    return <section key={chat.source} className={'source-chat '+chat.source} style={{opacity:enter,transform:`translateY(${Math.round((1-enter)*32)}px)`}}>
      <div className="source-chat-label"><strong>{chat.name}</strong><span>课程群聊天示例</span></div>
      <div className="chat-window"><aside className="chat-rail"><Avatar label="" tone="self"/><b><Glyph kind="chat"/></b><Glyph kind="people"/><Glyph kind="folder"/><span className="chat-menu">☰</span></aside>
        <aside className="chat-list"><div className="chat-search">⌕ 搜索 <span>＋</span></div>{[chat.title,'文件传输助手','课程讨论小组','自习打卡'].map((title,i)=><div key={title} className={i===0?'selected':''}><Avatar label="" tone={i===0?'group':'student'}/><div><strong>{title}</strong><small>{i===0?'[新消息] HW2 提交提醒':i===1?'Lecture Slides L2.pdf':i===2?'收到，谢谢':'今晚图书馆见'}</small></div></div>)}</aside>
        <div className="chat-main"><header><strong>{chat.title} ({chat.members})</strong><span>—　□　×</span></header><div className="chat-history"><div className="chat-date">10 月 19 日　{chat.messages[0].time}</div>{chat.messages.map((message,i)=>{
          const shown=interpolate(frame,[25+index*18+i*12,47+index*18+i*12],[0,1],clamp);
          const marked=message.role==='ta'&&frame>105+index*32;
          return <div key={message.id} className={'chat-message '+message.role} style={{opacity:shown,transform:`translateY(${Math.round((1-shown)*9)}px)`}}><Avatar label="" tone={message.role}/><div><span className="chat-sender">{message.sender}{message.role==='ta'&&chat.source==='qq'?<i>助教</i>:null}</span><p className={marked?'marked':''}>{message.text}</p></div></div>;
        })}</div><div className="chat-composer"><div><Glyph kind="smile"/><Glyph kind="folder"/><Glyph kind="cut"/><span>···</span></div><small>发送</small></div></div>
      </div>
    </section>;
  })}</div>;
}
