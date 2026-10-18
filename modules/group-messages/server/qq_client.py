"""Read-only platform clients. Standard library only; no UI, DB, AI, or credential files."""
import json, random, threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

class APIError(Exception):
    def __init__(self,source,category,message,retryable=False):
        super().__init__(message)
        self.source,self.category,self.retryable=source,category,retryable

def local_url(url):
    p=urlparse(url)
    if p.scheme!="http" or p.hostname not in ("localhost","127.0.0.1","::1") or p.username or p.password or p.query or p.fragment or p.path not in ("","/"):
        raise ValueError("QQ 接口地址应为本机 http://127.0.0.1:端口")
    return url.rstrip("/")

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise APIError("qq","address","QQ 本机接口发生重定向，请检查地址")

class Transport:
    def __init__(self,source,opener=None,timeout=20,retries=1,stop=None):
        self.source=source
        self.opener=opener or build_opener(ProxyHandler({}),NoRedirect())
        self.timeout=timeout;self.retries=retries;self.stop=stop or threading.Event()
    def fetch(self,request,retry=True):
        attempts=self.retries+1 if retry else 1
        for attempt in range(attempts):
            if self.stop.is_set():raise APIError(self.source,"stopped","采集已停止")
            retry_after=None
            try:
                with self.opener.open(request,timeout=self.timeout) as r:
                    raw=r.read(8*1024*1024+1)
                if len(raw)>8*1024*1024:raise APIError(self.source,"schema","响应超过 8MB，未导入")
                return raw
            except HTTPError as e:
                if e.code in (401,403):
                    raise APIError(self.source,"auth","连接口令未通过验证。请核对 NapCat“网络配置 → HTTP 服务端”的 Token；管理页面登录口令不能用于此连接。") from None
                if e.code == 404:
                    raise APIError(self.source,"address","这个地址未提供 QQ 接口。请填写 NapCat HTTP 服务端的地址和端口，并确认服务已启用。") from None
                temporary=e.code==429 or 500<=e.code<600
                category="rate_limit" if e.code==429 else "server" if temporary else "request"
                failure=APIError(self.source,category,"接口限流，稍后重试" if e.code==429 else "接口请求失败（HTTP "+str(e.code)+"）",temporary)
                try:retry_after=min(30,max(1,float(e.headers.get("Retry-After",""))))
                except (ValueError,TypeError):pass
            except (URLError,TimeoutError,ConnectionError,OSError):
                failure=APIError(self.source,"network","连接不到本机 QQ 服务。请先启动 NapCat，在“网络配置”启用 HTTP 服务端，并核对接口地址和端口。",True)
            if not failure.retryable or attempt+1>=attempts:raise failure
            delay=retry_after if retry_after is not None else min(8,2**attempt)+random.random()*0.3
            if self.stop.wait(delay):raise APIError(self.source,"stopped","采集已停止")
    def json(self,url,payload,headers=None):
        raw=self.fetch(Request(url,json.dumps(payload).encode(),{"Content-Type":"application/json",**(headers or {})}))
        try:
            value=json.loads(raw)
            if not isinstance(value,dict):raise ValueError()
            return value
        except (ValueError,TypeError):
            raise APIError(self.source,"schema","未收到 QQ 接口数据。请确认填写的是 HTTP 服务端地址（通常为 3000 端口），并在 NapCat 中检查 QQ 登录状态。管理页面通常使用 6099 端口。") from None

class QQClient:
    READ_ACTIONS={"get_login_info","get_status","get_version_info","get_group_list","get_friend_list",
        "get_group_msg_history","get_friend_msg_history","get_msg","get_image","get_forward_msg",
        "get_group_root_files","get_group_files_by_folder","get_group_file_url","get_file","get_private_file_url"}
    def __init__(self,base_url="http://127.0.0.1:3000",token="",timeout=15,stop=None):
        self.base_url=local_url(base_url);self.token=token
        self.transport=Transport("qq",timeout=timeout,stop=stop)
    def call(self,action,params=None):
        if action not in self.READ_ACTIONS:raise ValueError("仅开放已列出的读取接口")
        result=self.transport.json(self.base_url+"/"+action,params or {},
            {"Authorization":"Bearer "+self.token} if self.token else {})
        if result.get("status")!="ok" or result.get("retcode",0)!=0:
            if action == 'get_login_info':
                raise APIError('qq','account','QQ 登录尚未就绪。请在 NapCat 管理页面确认本人 QQ 已登录，再回来连接。')
            raise APIError("qq","upstream","QQ 读取失败："+action)
        return result.get("data")
    def login_info(self):return self.call("get_login_info")
    def groups(self):return self.call("get_group_list")
    def friends(self):return self.call("get_friend_list")
    def group_history(self,group_id,count=100):
        return self._history("get_group_msg_history",{"group_id":str(group_id),"count":min(100,max(1,int(count)))})
    def friend_history(self,user_id,count=100):
        return self._history("get_friend_msg_history",{"user_id":str(user_id),"count":min(100,max(1,int(count)))})
    def _history(self,action,params):
        data=self.call(action,params)
        rows=data.get("messages") if isinstance(data,dict) else data
        if not isinstance(rows,list):raise APIError("qq","schema","QQ 历史消息结构不匹配")
        return rows
    def image(self,file_ref):return self.call("get_image",{"file":file_ref})
    def group_files(self,group_id,folder_id=None):
        params={"group_id":str(group_id)}
        if folder_id is None:return self.call("get_group_root_files",params)
        params["folder_id"]=folder_id;return self.call("get_group_files_by_folder",params)
    def group_file_url(self,group_id,file_id,busid=0):
        return self.call("get_group_file_url",{"group_id":str(group_id),"file_id":file_id,"busid":busid})

