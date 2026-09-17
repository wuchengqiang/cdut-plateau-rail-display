# 1. 项目基本信息

> 核对日期：2026-09-16（北京时间）。本文依据当前源码、Git、磁盘配置、历史交付验证记录及本项目会话整理。本文是新账号／新线程的独立入口，不能假定聊天历史、Codex 缓存、现场机器或 GitHub 登录仍可用。
>
> 本次仅生成交接文档，未修改程序、发送机械动作、提交 Git 或重新打包。主要交接对象是滑轨屏；同仓库的另两个产品单独说明。

- 项目名称：成都理工大学校史馆·青藏高原科考滑轨屏联动播控系统。
- 项目路径：`D:\滑轨屏轮播程序`。
- 仓库地址：`https://github.com/wuchengqiang/cdut-plateau-rail-display.git`。三个工作树的 origin 相同。远端当前公开性、访问权限及服务器最新提交未联网核实，不能保证匿名克隆或仅凭克隆就能恢复最新成果。
- 技术栈：Python + FastAPI + Uvicorn；React + TypeScript + Vite；原生浏览器 HTMLVideoElement；WebSocket 状态同步；UDP/TCP 电机适配；PyInstaller 绿色 Web 服务交付。
- 运行环境：Windows，PowerShell；现场浏览器为 Edge / 数字人 Host 内嵌浏览器。当前开发机核实为 Python 3.11.9、Node.js 24.14.0、npm 11.9.0；不代表这些版本均为最低要求。
- 包管理方式：后端 `requirements.txt`，前端 `frontend/package.json` + `frontend/package-lock.json`；根 `package.json` 转发前端命令。前端依赖声明有 `latest`，新环境优先 `npm.cmd --prefix frontend ci` 保持锁定版本。
- 当前主要分支：滑轨屏 `main`，HEAD `8971e94571fde9dd1387ae196710e873d8c2796a`；HEAD 是 V1.1.5 保存点，工作目录实际已发展到 V1.1.7，不能把两者等同。
- 当前工作树结构：主目录包含公共 `.git`，另两个目录是正式 Git worktree，共享对象、分支和 stash，文件及检出分支彼此独立。不是三个独立仓库，也不是简单目录副本。

| 工作树名称 | 文件路径 | Git 分支 | 用途 | 当前状态 |
| --- | --- | --- | --- | --- |
| 青藏高原滑轨屏（本交接主对象） | `D:\滑轨屏轮播程序` | `main` | 2160×3840竖屏、数字人嵌入、媒体与实体滑轨联动 | HEAD `8971e94`；工作区有 V1.1.6/V1.1.7 未提交修改；保留 V1.1.7 解压交付目录 |
| 70周年大屏播放器／穿越成理 | `D:\成都理工大学70周年视频播放器` | `anniversary-player-lite` | 5200×1560大屏、数字人、中控播放，无滑轨 | HEAD `22e1fb7`；9月16日核对干净；9月15日增加整片循环接口；未发现对应当天新交付包 |
| 70周年投影／沙盘播放器 | `D:\成都理工大学70周年投影播放器` | `codex/projector-player` | 纯投影、素材/区间点位、中控与维护，无滑轨 | HEAD `15c5a16`；9月16日核对干净；9月15日有交付 ZIP |

`tmp/`、`release/`、`browser-profile/`、`backend/static/` 是预览、产物或运行目录，不是额外工作树。当前未发现单独的“滑轨图文分支”；历史上讨论过，但不能据讨论宣称已创建。

# 2. 项目目标与背景

## 滑轨屏

本项目用于校史馆展陈：观众操作屏幕、数字人理解指令、或工作人员操作中控平板后，播放器选择展项，播放对应资料，并通过厂家控制软件让实体滑轨屏移动到相应位置。中控无需知道电机坐标和厂家协议。

最初主题为“极地科考”，后改为“青藏高原科考”。项目从独立桌面播放器逐步改为 Web 服务，由数字人 Host 内嵌浏览器显示页面、在上层叠加实际数字人。当前交付不需要 Tauri，但仍需打包本地后端运行环境，方便现场免安装 Python/Node。

当前阶段：四点和回原点已由用户报告现场实测可动；资料暂以4号点位的一部视频为主。现场先固定停在 p04 展示，隐藏点位栏和多余操作。最新界面为左侧竖向视频、右侧数字人预留区，背景呼应视频中的珠峰攀登故事。

长期方向：资料齐备后恢复按点位参观和自动巡展；视频或图文可配置；标题、按钮名称、坐标、素材及数字人关键词不依赖改源码。不能把这些长期方向误当成本轮已经开始的新任务。

主要业务约束：

- 现场滑轨屏是2160×3840竖屏，开发电脑横屏不代表现场改为横屏。当前视频也为竖屏，先前检查为2126×3840。
- 数字人由 Host 提供，须一直有位置展示。滑轨页不再做视频全屏、不加假对话气泡，页面玩偶默认关闭。
- 标题和日常页面尽量纯净，不展示英文装饰、内部状态或“硬件异常仍可播放”等运维文案；诊断放管理员面板/API。
- 暂时静态展示可配置，不能删除未来四点联动能力。UI 隐藏按钮也不代表停用 API。
- 视频由现场复制，通用包不含视频；素材命名与点位 ID 是配置映射，不是 API 的硬编码要求。

## 另两个产品

70周年大屏是为了复用媒体、数字人和 API 框架，但去除电机控制而创建的工作树。后来独立演进为“穿越成理”无人值守纯展示页。投影工作树进一步面向实体沙盘，支持建筑/展项视频及原片时间区间。

这两套的分辨率、数字人显示策略、接口命名、鉴权默认值和交付结构都不同；不能把它们的新功能整目录复制到滑轨屏。

# 3. 当前代码架构说明

## 滑轨屏目录

```text
D:\滑轨屏轮播程序\
├─ backend\
│  ├─ portable_launcher.py     双监听启动、Edge全屏及退出管理
│  ├─ app\main.py             API、运行时、WakeFusion、管理员、WebSocket
│  ├─ app\config.py           外置配置加载/校验/保存、素材存在性
│  ├─ app\services.py         媒体、场景、巡展、Mock/TCP/UDP电机
│  ├─ app\remote_control.py   8001白名单网关、密钥和来源校验
│  ├─ static\                 Vite构建产物（Git忽略）
│  └─ test_*.py                源码与交付程序测试
├─ frontend\src\
│  ├─ main.tsx                展示页、管理员、媒体事件、音量手势
│  ├─ exhibit.css             当前实际使用的样式
│  ├─ media-controller.ts     播控同步、结束反馈、掉帧/缓冲诊断
│  └─ styles.css              历史样式；当前main.tsx未导入
├─ config\                   外置业务、点位、协议和认证配置
├─ content\                  视频、背景、海报、校徽、玩偶
├─ wakefusion\               Host app.json和启动BAT
├─ packaging\               prepare/verify/archive及现场部署文档
├─ docs\                    历史说明、接口交接、第三方标准
├─ q版形象\                  原型素材目录，现页面默认不显示玩偶
├─ release\                 绿色交付产物（Git忽略）
└─ tmp\                     预览、截图、构建中间产物（Git忽略）
```

## 新接手首先需要理解的数据流

```text
Host内嵌页面/独立Edge ── 本机8000 ─┐
数字人标准动作API ──── 本机8000 ─┤
远程中控平板 ── Bearer + 8001 ──┤
                                ↓
                     同一份DisplayRuntime
                      SceneService / MediaService
                       ↓                     ↓
             UDP 127.0.0.1:53500       WebSocket /ws
                       ↓                     ↓
                 厂家控制软件          浏览器真正播放视频
                       ↓                     ↓
                    实体电机         ended/error会话反馈
```

后台不会自己渲染/解码视频；即便 API 返回成功，仍须正式浏览器页面存在才能播放及反馈结束。不要同时打开多个正式播放页，避免重复音频和多个反馈源。

选择点位时，先切换展示内容并启动播放，再等待电机到位。`currentPointId` 是已确认位置，`targetPointId` 是目标，`displayPointId` 是当前内容，三者不可混用。`mediaSessionId` 标识一次素材会话，`playbackRevision` 标识显式播控修订；前端不能因电机状态更新而重新 seek、重新创建视频或重复播放。

`points.json` 是业务点位和坐标源。`config.py` 将其转换成内部 scenes，并生成运行时 `machine.positionsMm`。文件中 `machine.json.positionsMm={}` 是正常状态，不能由此判断未配置坐标。旧 `scenes.json` 文档不是当前配置依据。

## 三套端口与身份的边界

| 产品/用途 | 当前地址或端口 | 请求/认证 |
| --- | --- | --- |
| 滑轨本机页面/业务 | `127.0.0.1:8000` | 仅回环，页面与本机操作 |
| 滑轨数字人标准接口 | 同8000，`/api/wakefusion/v1/*` | Host 注入 `WAKEFUSION_APP_TOKEN`，Bearer |
| 滑轨远程中控 | `192.168.1.105:8001`（部署目标IP） | 独立安装密钥，Bearer；读GET、动作POST空请求体 |
| 滑轨厂家服务 | 本机UDP `127.0.0.1:53500` | 当前无 SharedKey；ASCII命令 |
| 70周年大屏本机业务 | `127.0.0.1:8010` | 本机页与Host接口 |
| 70周年大屏中控 | 所在电脑IP，TCP8020 | `/api/control/v1/*`；GET/POST播控；当前配置token空，可配置 |
| 投影本机业务/维护 | `127.0.0.1:8010`，`/admin` | 维护页仅本机；正式页无数字人 |
| 投影中控 | 所在电脑IP，TCP8020 | 与大屏基础接口相同，另有媒体点位接口；当前token空，可配置 |

两套70周年服务默认端口相同，设计用于不同主机；同一开发机同时启动必须隔离配置并调整端口。现场滑轨IP曾误写为192.168.1.104；用户后来明确厂家软件和播放器都在192.168.1.105同一台主机，所以厂家目标最终改成回环地址。本文未重新探测现场IP。

## 滑轨接口与协议要点

- 中控读取：`GET /api/status`、`GET /api/points`。
- 中控动作：`POST /api/control/points/{id}/activate`，以及 `/api/control/play`、`pause`、`stop`、`home`、`carousel/start`、`carousel/stop`、`emergency-stop`。请求体可空。
- 本机兼容接口部分允许 GET/POST；8001网关严格限制读取GET、动作POST，不要用旧本机接口规则推断远程接口。
- 中控8001只开放白名单操作，不提供网页、素材、管理员、WakeFusion或WebSocket。数字人Token与中控Token不能互用。
- WakeFusion：`GET /api/wakefusion/v1/health|status|actions`，`POST /api/wakefusion/v1/actions/{index}/execute`。执行体按V1.1标准提供schemaVersion、requestId、source和幂等键，先查询动作目录取得index，不能把index等同点位序号。
- 当前配置10个数字人动作：四点、播放、暂停、停止、回原点、启动/停止巡展。软停有业务/中控入口，但未作为第11个数字人动作自动添加。
- 标准路径仍含`v1`，配置schema仍为`wakefusion.embedded-app/v1`；对齐文档修订V1.1不等于把这些标识改成`v1.1`。
- UDP命令带CRLF：`PING`→`PONG`；`STATUS`查询；`MOVE 1600`期待到位回包`OK:MOVE 1600`；`STOP`期待`OK:STOP`。
- MOVE为绝对坐标，正100就是正100；不自动取负。回原点发送`MOVE 0`，不能发送`ZERO`，后者会改变参考零点。
- UDP不使用TCP专属WATCH；每条请求采用独立套接字，隔离迟到回包。动作超时不自动重发，避免已移动但回包丢失时重复驱动。

# 4. 当前开发进度

## 已完成

| 功能 | 对应文件 | 实现方式与关键决策 |
| --- | --- | --- |
| 外置点位、标题、坐标、素材 | `config/points.json`、`backend/app/config.py` | ID稳定，显示名称/文件名独立；运行时生成坐标映射 |
| 真实滑轨通信 | `backend/app/services.py` | Mock/TCP/UDP适配，当前UDP127.0.0.1:53500；正坐标；不重试MOVE |
| 移动中同步播放 | `SceneService`、`media-controller.ts` | 开始切点即播放，到位只更新机械状态；硬件失败不倒退或隐藏已显示视频 |
| 自动巡展 | `CarouselService`、`test_carousel.py` | 视频结束且到位后继续；无视频/图文到位后停留默认12秒；returnHome模式 |
| 软件软停 | `main.py`、`services.py` | 取消在途任务后发送一次STOP；不能替代硬件急停，不自动校零 |
| 数字人V1.1对接 | `main.py`、`config/wakefusion.json`、`wakefusion/app.json` | 标准健康/状态/动作/幂等/鉴权；硬件初始化与业务ready解耦 |
| 远程中控受保护入口 | `remote_control.py`、`portable_launcher.py` | 单业务运行时、双端口；安装级持久密钥；来源和路由白名单 |
| 管理员及展示配置 | `main.tsx`、`main.py`、`config.py` | 页面入口、密码、素材重扫、展示方式、访客按钮显示开关、播放诊断 |
| 固定展示 | `config/app.json`及管理员 | demo模式隐藏点位和编号；机械停靠点与内容点可分开配置；当前均p04 |
| 珠峰主题竖屏页面 | `exhibit.css`、`main.tsx`、p04背景图 | 固定9:16视频框、完整显示素材；右侧大于28%安全区；保留播放/暂停/停止/喇叭 |
| 绿色部署 | `packaging/*.py`、`wakefusion/*.bat` | V1.1.7 Web服务EXE；启动BAT为ASCII/CRLF；独立Edge与Host托管两种模式 |

当前点位：

| ID | 标题 | 坐标mm | 素材配置 | 当前注意事项 |
| --- | --- | ---: | --- | --- |
| p00 | 机械原点 | 0 | 不作为可见展项 | 回原点动作使用 |
| p01 | 高原启程 | 1600 | `content/videos/p01.mp4` | 当前开发素材目录无此视频 |
| p02 | 地质巡测 | 3200 | `content/videos/p02.mp4` | 当前开发素材目录无此视频 |
| p03 | 冰川源区 | 4800 | `content/videos/p03.mp4` | 视频未放置；背景配置引用缺失文件，见第9节 |
| p04 | 高原守望 | 6400 | `content/videos/p04.mp4` | 当前实际文件名`P04.mp4`，约405,754,749字节；Windows可正常匹配大小写 |

完整参观时视觉从右到左为1→2→3→4，即屏幕左到右4、3、2、1；左滑从1进入2。固定展示demo关闭滑动/箭头和点位栏；compact隐藏底栏但保留切换箭头/滑动；visit显示完整点位栏。

巡展为按顺序递增、到末点后折返、最终回原点并停止。由p2开始是`p03→p04→p03→p02→p01→p00`；不是四点无限循环。代码仍支持其他tourMode，现场当前选returnHome。

## 正在开发

主线程最新获授权的实现任务为UI重做并打包，已经完成V1.1.7交付。当前任务是文档交接，没有另一项明确在途的功能开发。

- 最新源码未提交，切账号前仍需保存其完整状态。
- V1.1.7在实际Host叠加、触屏穿透、现场4K视频长时间播放方面，没有新的现场验收反馈；仅本机与模拟验证不能代替这些结果。
- 本次核对发现p03背景缺失，以及旧说明与现代码有冲突，已记录；本次未擅自修复或补发安装包。
- 没有确认中的开发环境阻塞；远端可达性及现场Host版本不确定。

## 尚未开始

以下是建议后续任务，未获得本次实现授权：

- 修复p03背景配置/资源一致性，影响素材引用和下一交付包。
- 将最新滑轨代码整理为可恢复的Git保存点，迁移必要非Git文件。
- 按真实现场数据分析剩余卡顿、Host覆盖层点击拦截；可能涉及Host团队配合。
- 若用户继续要求，再完善持久化诊断日志、构建素材完整性检查、文档整理。
- 等正式资料齐备，调整各点位媒体/图文及参观模式。没有已承诺的“全部改图文”开发分支。

## 另两个工作树各自进度

- 大屏：`22e1fb7`，已提交并干净；9月15日增加`loop/on`和`loop/off`，设置开关不主动起播，播放/暂停/继续/停止保持原接口。当前源码下未发现9月15日大屏新包；已有release目录主要是9月10日等历史版本，不能假定包含新增循环功能。其FastAPI/配置版本仍有1.1.0，与滑轨V1.1.7无关。
- 投影：`15c5a16`，已提交并干净；支持独立视频点位、长视频区间、默认循环、草稿/发布、预览、交接导出，以及Ctrl+Shift+M原窗口维护。维护时中控播控409 `MAINTENANCE_MODE`。已存在`穿越成理-投影播放器-20260915-170324.zip`（17,226,858字节）及更早170151包。选包须结合该工作树`build-manifest.json`和验证记录，不靠文件名猜测。

# 5. 最近开发上下文（重点）

## 滑轨主线的变更原因

1. **从桌面壳转为Web服务。** 数字人团队要求其Host内嵌浏览器访问链接并在页面上叠加形象，因此停用Tauri交付路线，保留本地服务绿色打包。第三方对接标准曾多次更新，现以`docs/第三方对接标准/WakeFusion嵌入应用开发与部署约定V1.1.md`为主要依据。
2. **健康检查不能被硬件卡死。** 现场曾出现首页200、能读四展项，但健康一直503、ready:false，Host拒绝展示。当前配置加载完成即可业务ready，硬件初始化在后台有时限执行，硬件状态单独报告；不要恢复“电机通才ready”的判断。
3. **厂家软件才是通信目标。** 最早按设备IP192.168.1.104配置，发生PING和MOVE超时。后确认播放器与厂家软件同机、主机IP192.168.1.105，厂家服务53500、UDP可用；改为127.0.0.1:53500。这里应用PING/PONG与Windows ICMP ping不是同一项检测。
4. **负坐标经验被实测纠正。** 厂家早期口述1600要发-1600，程序曾照做；用户在安全位置测试MOVE 100后确认就是正100，与协议一致。现0/1600/3200/4800/6400，不再取负，不再让中控计算坐标。
5. **不应等长距离移动结束才播。** 现场体验等待过久，改成切点立即播放并同步移动。此前还怀疑到位会中断视频；现分离媒体状态和机械状态，通过媒体会话/修订避免到位重播，增加掉帧、缓冲、时长诊断。真实解码性能仍依赖现场机器和素材，不能声称所有卡顿都已消除。
6. **先有一个视频，先做好固定演示。** 用户希望屏幕停p4、隐藏1234和不必要操作。增加demo/compact/visit及可配置展示内容点；随后管理员的“明日静态演示”改为长期适用名称，并区分显示设置与会真实移动的测试按钮。
7. **界面误把竖屏视频按横屏展示。** 用户明确现场2160×3840，现有视频2126×3840。早前16:9容器使画面很小且留白过多，V1.1.7改为固定9:16卡片；有无视频不改布局。视频字幕/黑边来自素材，不额外裁切。实际样例中的气泡、片内标题和下方点位卡均未照搬。
8. **背景应呼应珠峰故事。** 第一次生成草甸河谷背景后用户认为不贴合，重新将用户参考图直接提供给内置imagegen，生成蓝天、巍峨雪峰、冰川、覆雪岩石。现用`p04-everest-exhibition-v3.png`，仅改p04背景；前版`p04-plateau-exhibition-v2.png`还在磁盘，但不再是p04默认引用。AI主题图不应描述为真实纪实照片。
9. **触控被Host遮挡的历史反馈。** 用户曾报告独立页面可点击，数字人融合后不可点击。Host上层全窗口命中/透明层是待核查方向，而非已经证实且彻底解决的根因。播放器自身预留区`pointer-events:none`；无法靠本页面CSS保证穿透Host层。已提供受保护8001中控作为操作入口。
10. **2026-09-13交付V1.1.7。** 修改版本声明及对应测试，构建前端、PyInstaller服务，11项隔离回归通过，原ZIP约54.56MB。不含视频、安装密钥和浏览器缓存。Git没有同步提交本轮全部成果。

## 其他线程的可核实近况

本文没有读取那些线程完整聊天，仅依据各自源码、提交和当地文档：

- 大屏9月15日：`55986da`保存基线，`b364d0b`增加整片循环，`22e1fb7`补交接。正式展示页无鼠标播控按钮，由中控/数字人控制。播放/暂停期间默认通过Host消息隐藏数字人，停止等恢复；这与滑轨“数字人一直展示”的需求不同。
- 投影9月15日：`13c6c62`点位/区间首版；`a2f2492`维护快捷键、加载/暂停稳定性和交付；`00bfbc5`文档；`15c5a16`最终交付验证记录。它的“点位”是媒体/建筑点位，完全不是电机毫米坐标。
- 两套的早期《双播放器基础播控与循环接口交接》写过“点位暂未开放/本次未打包”；投影后续已实现并打包，所以读文档必须看适用工作树与修订时间。

当前推荐：滑轨以V1.1.7工作目录为UI和API延续基线，先补齐可恢复性与明确缺陷，再做现场联调，不回退套用旧横屏布局、负坐标或70周年鉴权规则。

# 6. 当前 Git 状态

以下是生成本文之前的本地快照，未执行fetch；远端情况以本地缓存引用为准。

## 主工作树

- 分支：`main`，HEAD `8971e94`。
- 相对本地`origin/main`领先2个提交：`8333a16`（正坐标、同步播放与触屏重构）和`8971e94`（V1.1.5保存点）。不等于已核实GitHub服务器现状。
- 未合并冲突：`git ls-files -u`为空。
- stash：`git stash list`为空，三个工作树共享这个stash空间。
- 当前20个已跟踪文件变动（含2个删除），另有5个未跟踪文件；本文生成后会额外出现一个未跟踪MD。

```text
 M .gitignore
 M backend/app/config.py
 M backend/app/main.py
 M backend/test_content_config.py
 M backend/test_initial_media.py
 M backend/test_readiness.py
 M backend/test_remote_control.py
 M backend/test_udp_release.py
 M backend/test_wakefusion.py
 M config/app.json
 M config/points.json
 M config/wakefusion.json
 D content/backgrounds/p03-glacier-source.png
 D content/backgrounds/p04-plateau-spirit.png
 M docs/中控平板接入交接-青藏高原滑轨屏.md
 M docs/自动巡展规则与配置.md
 M frontend/src/exhibit.css
 M frontend/src/main.tsx
 M packaging/build_release.py
 M packaging/部署步骤.md
?? content/backgrounds/p03-plateau-spirit.png
?? content/backgrounds/p04-everest-exhibition-v3.png
?? content/backgrounds/p04-glacier-source.png
?? content/backgrounds/p04-plateau-exhibition-v2.png
?? docs/4号点位竖屏界面设计说明.md
```

## 其他工作树及合并状态

| 分支 | HEAD | 工作区 | 与main分歧计数（main独有/该分支独有） | 未出现在本地远端引用中的提交数 |
| --- | --- | --- | --- | ---: |
| anniversary-player-lite | `22e1fb7ffe459dc607fe66c972593eca513f2df9` | 干净 | 17 / 7 | 7 |
| codex/projector-player | `15c5a165a96ff61440638bc9c492531f8f38dd72` | 干净 | 17 / 13 | 13 |

这两个分支没有显示上游跟踪配置。独有提交没有合并到main；远端是否已有其他引用承载这些成果不确定。三套产品有意独立演进，并没有既定的“最后必须合并main”要求。

冲突风险：三个分支的`main.tsx`、配置、业务服务、启动器及文档同名但语义分化。不要直接合并整个产品分支，不要在脏主工作树执行reset/clean/rebase。若将来复用公共修复，先看差异和需求，按具体文件/提交迁移并回归。

## 账号/电脑迁移必须保留的内容

1. 仅换Codex账号且电脑不变时，保留三个路径，确认新账号可以访问磁盘即可；聊天是否同步不作为恢复前提。
2. 换电脑/迁移目录时，保存主仓库`.git`及所有未提交、未跟踪文件，同时保存另两个工作树文件。工作树`.git`通常是指向主仓库元数据的文本文件，孤立复制某一个目录不能保证其Git仍可用。
3. 可在用户确认保存策略后提交各分支，或额外用`git bundle create <备份路径> --all`保存已提交历史；bundle不包含未提交文件、未跟踪文件、视频和密钥，必须另行备份。本文未执行commit/push/bundle。
4. 新电脑恢复共享Git后，用`git worktree list`核对；按实际恢复方式`git worktree repair`或重建相应分支的工作树，不要盲目修改`.git`。
5. 另行备份视频、现场`config`、背景、安装密钥、交付目录及必要预览截图。`.gitignore`忽略`release/`、`tmp/`、`backend/static/`、`browser-profile/`、`config/admin.json`、`config/remote-control.key`和常见视频文件，普通clone不会带回来。
6. 文档不包含真实密钥，不复制Host Token；账号凭据、GitHub权限、插件和依赖缓存需要新环境重新核对。最终背景已保存在项目content目录，不依赖原Codex生成图片缓存。

# 7. 重要文件索引

除另行注明，路径相对`D:\滑轨屏轮播程序`。

| 文件 | 作用 | 重要程度 | 修改注意事项 |
| --- | --- | --- | --- |
| `backend/app/services.py` | 电机、媒体、场景、巡展状态机 | 极高 | 不随意改MOVE重试、取消/STOP、到位与播放关系；需模拟回归 |
| `frontend/src/media-controller.ts` | 浏览器媒体生命周期 | 极高 | 不因每次状态更新seek/重播；保留会话与结束有效性检查 |
| `backend/app/main.py` | API、Host标准、管理员、ready、版本 | 极高 | 保持V1.1协议、鉴权与幂等；业务ready不依赖电机在线 |
| `backend/app/remote_control.py` | 远程8001安全边界 | 极高 | 不开放管理员/素材，不用Host Token或2468替代中控密钥 |
| `backend/portable_launcher.py` | 双监听、全屏、退出 | 极高 | 两端口先占用再初始化硬件；只管理本程序浏览器进程 |
| `backend/app/config.py` | 配置规范化、素材检测、原子保存 | 高 | points为坐标源；保留字段校验和原子写入 |
| `frontend/src/main.tsx` | 页面、管理员、音量、触屏 | 高 | demo/compact/visit独立；不要暴露技术提示到观众页 |
| `frontend/src/exhibit.css` | 当前竖屏布局 | 高 | 2160×3840、9:16视频、Host安全区；不能改错旧styles.css |
| `config/points.json` | 点位、坐标、背景、媒体 | 极高 | ID和路径不混淆；p03背景目前缺失；重命名检查引用 |
| `config/app.json` | 标题、显示模式、按钮、端口 | 高 | demo两个p04；showMascots=false；apiHost保持127.0.0.1 |
| `config/machine.json` | 厂家UDP目标与超时 | 极高 | 当前127.0.0.1:53500；不要自动改回192.168.1.104或负坐标 |
| `config/remote-control.json` | 中控监听与来源 | 极高 | 当前8001、0.0.0.0、127.0.0.1/32与192.168.1.0/24 |
| `config/remote-control.key` | 每安装密钥 | 极高 | 不入Git/通用包/文档；升级原样保留 |
| `config/admin.json` | 本机管理员密码 | 高 | 默认`{"password":"2468"}`；和远程鉴权无关 |
| `config/wakefusion.json` | 数字人动作、关键词、版本 | 极高 | 稳定action id，按协议更新公开文本，不固定index猜目标 |
| `wakefusion/app.json` | Host发现与启动入口 | 极高 | appId=cdut-slider-screen；pageUrl端口与模式一致 |
| `wakefusion/start.bat`、`start-standalone.bat` | 两种启动方式 | 高 | ASCII内容+CRLF，避免中文路径编码问题 |
| `packaging/build_release.py` | 构建/归档排除规则 | 高 | 不打入视频、密钥、浏览器缓存；拒绝覆盖同名包 |
| `packaging/verify_release.py` | 交付验证与报告 | 高 | 在隔离副本运行假UDP，不接现场电机；失败不可伪造passed |
| `content/backgrounds/p04-everest-exhibition-v3.png` | 当前4号珠峰主题图 | 高 | AI氛围图；标题由网页绘制，不能烧入按钮/假数字人 |
| `运动控制通讯文档(1).pdf` | 厂家命令依据 | 高 | 使用命令前查原文；本交接未重新解析PDF，不扩展未核实命令 |
| `docs/第三方对接标准/WakeFusion嵌入应用开发与部署约定V1.1.md` | Host对齐标准 | 极高 | 优先于V1旧版和聊天里的过时猜测 |
| `docs/中控平板接入交接-青藏高原滑轨屏.md` | 交给中控线程的接口手册 | 高 | 中控只调用播放器，不直接驱动厂家软件 |
| `packaging/部署步骤.md` | 当前交付操作说明 | 高 | 存在恢复p1的过时一句，见第9节 |
| `README.md` | 早期入门 | 低（待更新） | 仍写极地、硬件未实现、scenes等，不能当当前事实 |
| `tmp/portrait-preview.py` | 无电机UI预览，8016 | 辅助 | Git忽略，不是正式后台；返回模拟播控状态 |
| `tmp/check-portrait-v2.cjs` | 本机布局检查/截图 | 辅助 | Playwright依赖路径含原账号缓存；迁移需调整 |

另两套关键入口（相对各自工作树）：

| 产品 | 文件 | 作用及注意事项 |
| --- | --- | --- |
| 大屏 | `docs/70周年播放器-工程设计与新任务交接.md` | 历史总体设计；结合最新README/9月15日接口说明看，旧提交状态不可照抄 |
| 大屏 | `docs/中控API与部署.md`、`config/control.json` | 8010/8020、本机与远程入口、可选中控Token |
| 大屏 | `frontend/src/main.tsx`、`backend/app/control.py` | 无人值守展示、Host形象显隐、整片循环 |
| 投影 | `docs/沙盘投影播放器-新线程交接.md` | 投影专项上下文，有首段最新修订说明 |
| 投影 | `docs/沙盘部署与维护操作.md` | 当前维护、升级和现场验收主文档 |
| 投影 | `docs/20260915-沙盘点位播控-中控与管理员交接.md` | 媒体点位/区间API和导出 |
| 投影 | `config/projector-catalog.json` | 发布点位目录；不是滑轨点位，不能用positionMm替代 |
| 投影 | `backend/projector_window.py` | 单实例、窗口唤回、退出生命周期 |
| 两套 | `tools/build_release.py` | 各自打包脚本；不是滑轨packaging脚本 |

# 8. 环境与运行方式

## 安装步骤与运行命令（滑轨）

```powershell
Set-Location 'D:\滑轨屏轮播程序'
python -m pip install -r requirements.txt
npm.cmd --prefix frontend ci
npm.cmd run check
npm.cmd run build
```

`npm.cmd run build`将前端输出到`backend/static`，不会生成交付ZIP。现场包自带Python运行时，不需要现场pip/npm。

正式开发后端：

```powershell
python backend/portable_launcher.py --no-browser
```

该命令读取真实`config/machine.json`，启动时会PING/STATUS厂家软件；页面点击切点会移动。仅做UI检查时使用已存在的隔离预览：

```powershell
python tmp/portrait-preview.py
# 打开 http://127.0.0.1:8016/?embed=1&avatarAnchor=right
```

隔离预览不导入电机服务；它不是可交付的业务实现。若tmp没有迁移，先创建独立预览或测试配置，不能为了看界面误用现场默认配置发动作。

真实独立运行：`python backend/portable_launcher.py --standalone`，自动打开Edge kiosk。独立模式关闭受管理浏览器会请求后台退出；托管模式`--no-browser`由Host负责进程管理。Host退出是否带走全部子进程须在真实Host版本验证，不能凭播放器启动脚本保证。

前端热更新可用`npm.cmd run dev`，Vite配置将`/api`、`/ws`代理8000；素材是否经该开发入口正确加载需核对，完整预览优先用构建后的后端页。直接`uvicorn app.main:app --host 0.0.0.0`绕过双端口保护，不作为当前正式部署命令。

## 测试命令

```powershell
npm.cmd run check
node frontend/test-media-controller.mjs
python backend/test_initial_media.py
python backend/test_motion_playback.py
python backend/test_carousel.py
python backend/test_content_config.py
python backend/test_remote_control.py
python backend/test_udp_motor.py
python backend/test_wakefusion.py
python backend/test_readiness.py
```

这些脚本各有测试入口，不能只运行unittest discover看到“0 tests”就当已通过。已有交付验证器串联11组检查，其中含打包EXE的正常/不回应假UDP场景。浏览器测试`node tmp/check-portrait-v2.cjs`依赖8016隔离预览和原账号缓存路径中的Playwright；新账号须调整依赖加载位置，不要将旧绝对缓存路径当项目依赖。

## 构建命令

```powershell
python packaging/build_release.py prepare
# 使用上一步实际打印的目录，不硬编码旧日期：
python packaging/verify_release.py 'D:\滑轨屏轮播程序\release\<本次生成目录>'
python packaging/build_release.py archive 'D:\滑轨屏轮播程序\release\<本次生成目录>'
```

再次发布时同步`backend/app/main.py::SERVICE_VERSION`、`config/wakefusion.json.version`和相关版本断言。脚本拒绝覆盖已有同名目录/ZIP；同日再次构建需安排新版本或明确保存旧产物，不删除唯一交付备份来绕过检查。`archive`要求有效verification，排除浏览器缓存，并做ZIP CRC与SHA-256。

## 最新交付依据

- 当前保留目录：`D:\滑轨屏轮播程序\release\WakeFusion滑轨屏-中控巡展版-V1.1.7-20260913`。
- `release-info.json`：版本1.1.7，创建2026-09-13 22:04:32+08:00，kind=portable-web-service，视频/密钥均未携带。
- `verification.json`：2026-09-13 22:07:00+08:00，11组检查通过，`physicalControllerContacted=false`、`packagedExeTested=true`、`browserVisualTested=false`。
- 本线程此前另做源码页面2160×3840等尺寸截图及真视频播放/暂停/停止检查；不应把它写成“打包EXE已在真实Host做视觉验收”。
- 历史ZIP：`WakeFusion滑轨屏-中控巡展版-V1.1.7-20260913.zip`，54,562,552字节，SHA-256 `906657ef063dc475dd40b92df8d4f6729a9b083285f86f72e6cff953b4870be7`。**9月16日该ZIP及校验文件已不在当前release根目录，原因未知；只确认解压目录仍在。** 重归档后的哈希需重算，不能沿用历史值。

## 现场部署

1. 退出Host及旧播放器，将旧app整体留作备份，尤其保存`runtime/config`、`runtime/content`、`remote-control.key`。
2. 从新交付目录取`app`，放在Host约定的同级位置，通常`C:\数字人\host`与`C:\数字人\app`并列，不要多套一层app。
3. 将现场视频复制到`app/runtime/content/videos`；当前p04路径映射为`p04.mp4`。保留新珠峰背景路径，不用旧points.json整份覆盖回去；逐项迁移现场标题、坐标、端口。
4. 原中控密钥原样复制到新版`app/runtime/config/remote-control.key`，不把中控数据库的保留当作播放器文件已恢复。
5. 联动启动Host，由`app/start.bat`启动无浏览器服务并注入Token。独立测试用`app/start-standalone.bat`；不要同时启动两份占用8000/8001。
6. 中控目标仍为`http://192.168.1.105:8001`加Bearer；由现场管理员按可信局域网需要放行8001入站。厂家软件保持运行并打开53500网络服务。
7. 先核对状态/素材、p04画面、背景、数字人位置和触摸；需要机械动作时由现场确认路线和急停条件。

当前默认管理员文件格式：`{"password":"2468"}`。这是页面管理员密码，不是中控或Host密钥。中控源默认允许127.0.0.1/32与192.168.1.0/24；若平板经另一台中控后端转发，按播放器实际看到的来源核对网段和Origin。

## 环境变量、外部服务、数据库与权限

- `WAKEFUSION_APP_TOKEN`：Host启动时注入；仅数字人标准接口使用，不写进公开配置/日志。
- `RAIL_DISPLAY_ROOT`：配置模块的数据根；直接模块测试可通过它隔离环境。正式portable_launcher会设置为源码根或EXE所在目录，不能指望预设该变量让启动器自动改用别处配置。
- 滑轨数据库：无。业务配置为JSON，密钥文件持久化，运行状态主要在内存；音量/静音在浏览器localStorage。重启不是从数据库恢复实际机械位置。
- 外部依赖：厂家控制软件及其硬件、数字人Host（融合模式）、中控客户端；独立运行需要Edge。数字人对话模型/资产不属于此仓库。
- 日常运行目录应当前用户可写，便于配置保存、密钥与浏览器profile；配置防火墙由具权限的现场人员操作，程序不自动改防火墙。
- 新Codex账号无需持有旧会话即可读代码；GitHub读写权限要另核实。只读/公开克隆与推送权限是两回事。

## 另两个工作树的运行与部署（分别操作）

大屏目录：`D:\成都理工大学70周年视频播放器`。用其自身requirements、锁文件安装，`npm.cmd run build`后`python backend/portable_launcher.py --no-browser`。现场由Host启动同级app；视频默认`app/runtime/content/videos/main.mp4`。`python tools/build_release.py`为该工作树打包命令。播放/暂停期间默认隐藏数字人，不能照搬到滑轨。中控8020的Token可由`config/control.json`或`PLAYER_CONTROL_TOKEN`配置，与Host Token独立。

投影目录：`D:\成都理工大学70周年投影播放器`。安装/构建命令在该目录执行；正式交付根有`start.bat`、`enable-autostart.bat`、`disable-autostart.bat`和`runtime`，不是强制套Host同级app。全景视频`runtime/content/videos/main.mp4`，其他点位素材由维护页管理。首启静态背景、不自动播放；Ctrl+Shift+M维护，Alt+F4退出并释放端口；自启动是Windows登录后启动。`python tools/build_release.py`打包，相关验证位于`tools/test_release.py`、`test_browser.cjs`、`test_window_lifecycle.cjs`。API包含媒体点位`/api/control/v1/points/{id}/play|loop|play-once|pause|resume|stop`，与滑轨点位命令不可混用。

# 9. 已知问题和坑

## 已核实的问题

1. **p03背景缺失。** 当前points引用`content/backgrounds/p03-glacier-source.png`，源码与V1.1.7交付目录均无该文件。Git显示它被删除，同时存在未跟踪`p03-plateau-spirit.png`、`p04-glacier-source.png`。疑似人工换名/调换，但目的不确定；不能擅自把用户图片恢复覆盖。当前默认只展示p04，未暴露不代表p03正常。
2. **最新代码未进入提交。** 克隆当前远端、切回HEAD或清理工作区会丢掉V1.1.7最新UI及部分管理功能。前端构建产物不是源码保存替代品。
3. **文档有过时内容。** 根README仍称极地、真实协议未实现且提scenes.json；历史TCP实机说明不适用于当前UDP默认。部署步骤仍有“前往p4到位后恢复p1”一句，实际代码按`demoContentPointId`恢复、当前是p04。新文档应按本文核对后的配置/源码理解。
4. **旧ZIP缺失。** 9月13日完成归档不等于9月16日文件仍在；当前应交付/恢复哪一份需基于实际目录。
5. **版本字段分散。** 滑轨运行版本为1.1.7，但前端package元数据仍1.0.0；测试有显式服务版本断言。另两套1.1.0也独立，不能全仓库搜索替换成同一版本。
6. **预览脚本不随Git。** `tmp`被忽略，Playwright路径含旧账号缓存；新环境先核对再运行。

## 技术债与待现场确认

- 源码有控制台logging和管理员播放诊断，未查到滑轨正式持久滚动日志配置。不要把投影版`runtime/logs/player.log`能力归到滑轨。
- 真实Host加载后的层级、点击穿透、数字人缩放和视频解码长时稳定性尚无V1.1.7新反馈。Host软件不在本工作树中，不能在这里凭空修改其覆盖层。
- 后端动作accepted只代表任务受理；到位需要后续状态/正确UDP回包。`ready=true`也不等于电机在线，不能互相替代。
- 目前页面左右数字人安全区在本机浏览器测试通过；没有生成或嵌入伪数字人截图作为Host完成证据。
- 视频自身含字幕和黑边。不要通过修改框比例、拉伸或裁切冒充修复原片；若需要真正改变内容，另行确认剪辑需求。
- 当前视频实文件`P04.mp4`与配置`p04.mp4`在Windows匹配；跨到大小写敏感文件系统需统一名称。
- 4号新背景已入目录但仍未被Git跟踪；复制代码忘记该文件会只看到底色。
- 管理员Ctrl+Shift+Alt+M是遗留调试快捷键，本机代码能直接切换调试状态；不能把四位管理员密码当安全边界。远程写仍由网关/Bearer隔离。
- 素材复制发生在程序启动后时需“重新扫描素材”或点击播放触发扫描；看见配置路径不代表文件已存在/解码成功。
- 隐藏访客按钮不撤销中控/管理员能力；demo模式也不是机械锁或权限隔离，误调用点位API仍可能移动。
- 服务启动PING/STATUS、退出取消动作可能触发协议操作；仅看UI请选择无硬件预览/隔离测试。
- 止巡展只停止排程；视频停止只停止媒体；软停才发送STOP；三者不可随意合并语义。
- 浏览器关闭、Host退出、服务退出是不同生命周期。独立模式有浏览器监督，Host模式要验收Host是否管理整个进程树。

新Codex最容易犯的错误：进入错误工作树；按README而不是当前代码开服务；把8001鉴权降到另两套的默认无Token；把播放改回等电机到位；把2160×3840当横屏；用16:9挤压竖视频；在真实配置下自动测试MOVE；把Git干净、测试通过或包已生成等同现场验收。

# 10. Codex 下一步工作指南

## 第一优先级任务

任务：确保迁移后的状态可恢复，并明确p03资源缺口。

- 先在正确目录执行`git status --short`、`git branch -vv`、`git worktree list --porcelain`，核对本文的三个HEAD和脏文件；保留新变化。
- 核对V1.1.7源码、珠峰图、p04视频和交付目录是否完整到位。未获新指示前只读检查，不自动清理或覆盖现场配置。
- 如果用户授权修复/继续发布，检查p03原图与现重命名图片，确定应恢复旧路径还是更新引用；只改该资源映射，并加适合的构建资产存在性检查，不能改掉用户对p04的珠峰选择。
- 在用户要求Git保存时，把实际最新源码、目标素材和交接文档保存为提交；视频/真实密钥/构建缓存不提交。新账号不会因读取本文自动获得推送或改仓库公开性的授权。
- 验收：三工作树分支明确；p01/p02/p04必要背景可读；p03问题被修复或明确保留；最新成果有可恢复副本；没有机械动作和非预期数据丢失。

## 第二优先级任务

任务：安排一次基于真实Host和现场视频的UI/播放验收，再决定下一次版本。

- 先确认8000健康和动作目录、正式浏览器实例数，再检查2160×3840下标题、9:16框、按钮、右侧数字人及点击。
- 若Host融合后点击失败，收集Host版本、覆盖区域和命中行为；若卡顿，读取管理员复制的播放诊断、素材编码/分辨率、掉帧和缓冲数据。不能未看证据就把ready改成依赖硬件或反复重载视频。
- 按需修改`main.tsx`、`exhibit.css`、`media-controller.ts`；接口/设备层只有确认涉及问题时才改。持久日志可作为独立小任务。
- 同步清理根README、部署说明中的过时描述。下一版打包继续走prepare→verify→archive，新增资源完整性核对。
- 验收：真实Host画面、触控和目标视频长时播放有记录；到位不暂停/重播；暂停和停止在到位后仍保持；受保护中控接口兼容；包无视频/真实密钥。

## 暂时不要做的事情

- 不恢复Tauri、不把后台服务变成只有静态网页；不换掉既有WakeFusion V1.1接口。
- 不改回负坐标、192.168.1.104或TCP默认，不自动ZERO/HOME，不对MOVE加重试。
- 不要求中控直接发送UDP或管理毫米坐标，不删除8001 Bearer鉴权。
- 不因隐藏点位按钮就移除四点/巡展功能，不把视频停止等同机械急停。
- 不添加视频全屏、假数字人、示例对话气泡或英文装饰；不重新给玩偶换服装。
- 不把70周年大屏“播放时隐藏数字人”的行为同步到滑轨；不把投影维护入口直接移植到滑轨。
- 不直接合并三个产品分支，不创建无需求的新工作树，不承诺main必须最终合并。
- 不覆盖现场密钥、视频、坐标；不把原包唯一备份删除；不假设聊天/账号缓存能替代工程文件。

# 11. 关键决策记录（ADR格式）

## ADR-01：三个工作树保留独立产品

### 决策：
滑轨、大屏和沙盘分别使用已有worktree/分支。

### 背景：
它们复用了基础播放与数字人框架，但现场硬件、UI和接口开始分化。

### 选择方案：
独立目录开发、按明确需求迁移公共修复。

### 放弃方案：
复制覆盖整个目录、将投影当滑轨分支随意合并。

### 原因：
相同文件名不意味着相同业务；误混合会改变机械、权限和展示行为。

## ADR-02：本地Web服务与Host内嵌

### 决策：
FastAPI提供页面和接口，Host显示页面并叠加数字人；保留独立Edge启动。

### 背景：
数字人团队明确要求给链接和标准API，不需要Tauri壳。

### 选择方案：
PyInstaller封装Web服务运行时，外置配置/素材，app与host按约定并列。

### 放弃方案：
继续Tauri打包、只交静态HTML不交后端。

### 原因：
兼顾Host融合、现场免安装和真实硬件/中控服务。

## ADR-03：业务ready与硬件状态解耦

### 决策：
业务可用即可ready，硬件后台初始化并单独报告。

### 背景：
硬件未通曾使健康持续503，Host不展示页面。

### 选择方案：
加载配置后就绪；初始化有限时，动作期间检查状态。

### 放弃方案：
等待电机成功连接后才允许Host展示。

### 原因：
离线硬件不应阻断内容展示和故障诊断。

## ADR-04：厂家本机UDP与正绝对坐标

### 决策：
默认向127.0.0.1:53500发送UDP；点位0/1600/3200/4800/6400。

### 背景：
厂家软件同机，用户实测正100就是正方向绝对位置。

### 选择方案：
播放器封装MOVE/STATUS/PING/STOP，回原点MOVE 0，超时不重复动作。

### 放弃方案：
负数转换、向误认的硬件IP发包、用ZERO回原点、UDP使用WATCH。

### 原因：
以原协议和现场结果为准，避免改零点或重复物理动作。

## ADR-05：移动与播放并行，巡展等待真实结束

### 决策：
切点立即播放并移动；到位不重启媒体；巡展等视频结束且到位。

### 背景：
长距离移动等待体验差，机械状态广播曾引发媒体连续性疑问。

### 选择方案：
独立展示ID、媒体会话/修订、浏览器有效ended反馈；图文到位后统一停留。

### 放弃方案：
到位才播、每条状态都重载视频、只按固定秒数切有视频点位。

### 原因：
保持观看连续性，避免迟到事件推进错误点位。

## ADR-06：中控与Host分端口和密钥

### 决策：
Host/UI在回环8000，中控8001单独Bearer与路由白名单。

### 背景：
中控来自平板/其他电脑，用户已确认支持空POST、GET读取及Bearer，并由中控入库保存密钥。

### 选择方案：
安装级随机密钥首次生成、升级保留，单业务运行时双监听。

### 放弃方案：
直接向局域网公开整个8000、用管理员2468或Host Token共用、去掉中控鉴权。

### 原因：
稳定中控调用且不暴露管理页、素材和数字人内部接口。

## ADR-07：固定竖屏布局与数字人留白

### 决策：
左侧9:16竖向卡片，右侧至少28%安全区，当前默认固定p04。

### 背景：
现场屏幕与视频均竖向，旧横向框太小；Host形象要常驻。

### 选择方案：
标题/按钮配置化，空素材也保持框尺寸，仅p04使用珠峰主题背景。

### 放弃方案：
16:9强制框、随素材有无变化布局、视频全屏、网页再绘制数字人/气泡。

### 原因：
让视频与实际数字人同时可见、触屏操作稳定，并对应珠峰攀登内容。

## ADR-08：通用包不携带现场媒体和凭据

### 决策：
包只含运行时、前端、默认配置和静态图片；视频与密钥现场迁移。

### 背景：
视频大且持续替换，中控数据库需要稳定密钥，用户明确要求不打包视频。

### 选择方案：
排除媒体扩展名与.key；默认管理员2468；ASCII/CRLF启动脚本；保留备份升级。

### 放弃方案：
内置统一中控密钥、把开发机视频/浏览器缓存打进通用包、升级直接删除唯一旧app。

### 原因：
缩小交付、避免凭据泄露、减少编码故障并保留现场资产。

# 12. 给新 Codex 的启动指令

将下面内容直接复制到新线程；先确保本文和工程文件已在新账号可访问的位置。

```text
请始终用中文作为技术负责人继续维护“成都理工大学青藏高原科考滑轨屏”。

先完整阅读 D:\滑轨屏轮播程序\PROJECT_HANDOFF_青藏高原滑轨屏_2026-09-16.md，
再核对 git status --short、git branch -vv、git worktree list --porcelain。

当前主工作树 D:\滑轨屏轮播程序，分支 main，历史HEAD 8971e94（V1.1.5），
工作目录/最近交付已为V1.1.7且含未提交修改。不要reset、clean或从HEAD覆盖这些成果。
另外两个工作树独立：
  D:\成都理工大学70周年视频播放器 → anniversary-player-lite，22e1fb7；
  D:\成都理工大学70周年投影播放器 → codex/projector-player，15c5a16。
除非我明确要求，不修改或合并它们。新Git状态比历史快照更新时保留新变化。

滑轨现场为2160×3840竖屏，视频也是竖屏，当前p04固定展示。
左侧9:16视频框，右侧Host数字人预留区，默认无玩偶、无气泡、无点位栏、无全屏。
默认p04背景为content/backgrounds/p04-everest-exhibition-v3.png。
视频、字幕与黑边属于原素材，未经要求不要裁切或改写。

本机UI/Host为127.0.0.1:8000，中控为8001强制独立Bearer，
厂家软件与播放器同机，UDP127.0.0.1:53500，点位正坐标0/1600/3200/4800/6400。
播放与移动同时开始；到位不能重播/暂停视频。业务ready不能依赖硬件连接。
中控只调用播放器API，不直接发厂家命令；不改负坐标、不ZERO、不重试MOVE。
只看UI用无电机预览/隔离测试，不能使用真实机械配置自动跑动作。

第一件事：输出简短的恢复核对结果，确认源码、版本、资源和三个工作树状态。
重点检查p03背景引用缺失、未提交修改、现场视频/密钥的备份和V1.1.7交付目录。
9月13日ZIP历史已验证，但9月16日根目录无该ZIP，只保留解压目录，不能假报文件存在。
11项交付模拟检查通过不等于Host现场视觉/触屏/长时视频验收通过。

这段提示用于恢复上下文，不自动授权Git推送、改仓库权限、控制实体电机或再次打包。
完成只读核对后，按我随后给出的具体开发任务推进；若我已明确要求修复，则完成相应修改和验证。
视频和真实密钥不进Git/通用包；升级保留现场remote-control.key、媒体和自定义配置。
```

文档维护原则：有新的现场证据、发布包或Git提交时更新相应段落；保留“源码验证”“交付程序验证”“现场验收”的区别，不把推测写成既定结果。
