# 上科大统一登录接入核查

核查日期：2026-10-18。使用学校邮箱注册不等于支持学校 SSO。

| 服务 | 当前证据 | 应用处理 |
| --- | --- | --- |
| Blackboard、ELRC、E 云课堂、教务课表 | 已有学校 IDS 跳转和服务端身份探测 | 共用学校 Cookie，登录成功后逐项连接；每项单独记录状态和验证要求 |
| 学校邮箱 Coremail | [学校账号说明](https://it.shanghaitech.edu.cn/2021/0421/c8344a63059/page.htm)单独说明邮箱账号及密码重置；[邮箱入口](https://mail.shanghaitech.edu.cn/)提供邮箱密码、短信与 Coremail 扫码，公开配置未启用 ExtLogin | 保留独立的官方窗口连接、Cookie 与 SID。未确认可供本应用使用的 IDS → 邮箱入口 |
| Gradescope | [官方学校 SSO 选择页](https://www.gradescope.com/saml)返回的 164 项机构配置中，没有 ShanghaiTech / Shanghai / 上海科技匹配；[官方管理员说明](https://guides.gradescope.com/hc/en-us/articles/37915486508301-Admin-Account-Overview)说明 SSO 和 LMS 集成由机构管理员配置 | 保留独立账号与会话恢复。若学校开通 SAML 或课程配置 Blackboard LTI，可再接入正式入口 |
| Piazza | [官方 SSO 入口](https://piazza.com/sso)列出 University of Virginia、Georgia Institute of Technology、Piazza University、UC Davis，未列上科大 | 保留独立账号与会话恢复；没有确认可用的上科大 SSO 入口 |

没有在公开入口中找到，不等于平台永久不支持或学校不存在内部入口。邮箱页面的 Egate 链接只证明可以访问门户，不能证明它可给邮箱签发登录会话。此次未得到可用的邮箱门户票据入口，也未确认学校已开通 Gradescope/Piazza 的机构 SSO，所以不能通过复制学校 Cookie 或复用学校密码来宣称完成接入。

学校自己的[身份互联认证平台说明](https://it.shanghaitech.edu.cn/xysfhlrzpt/list.htm)确认统一认证为接入的业务系统提供跨系统登录。这不意味着所有使用学校邮箱的平台都自动接入。

后续接入应以学校或平台提供的正式服务入口、身份映射和可验证会话为准。Gradescope 的 Blackboard LTI 需要实际配置的课程入口，不能自行构造签名或将通用 SSO 列表缺席解释为 LTI 不可用。
