# WakeFusion 嵌入应用开发与部署约定 V1.1

文档版本：1.1
协议标识：`wakefusion.embedded-app/v1`
适用对象：业务页面开发人员、UI 设计人员、项目交付人员、WakeFusion Host 开发人员
状态：正式开发约定，取代 V1.0（`wakefusion-embedded-app-standard-v1.md`）

本文自足。第三方只读这一份即可完成开发与交付，不需要再对照 V1.0。
从 V1.0 迁移的差异集中在第 18 节。

---

## 1. 目标

WakeFusion Host 负责数字人、语音交互、业务应用承载和动作调用。业务应用负责自己的页面与业务逻辑。

每个项目只交付一个符合本约定的"应用包"。Host 不因客户页面、行业页面或项目接口不同而重新定制。

本约定要求：

1. 只有一个固定应用目录；
2. 只有一个应用描述文件；
3. 只有一套标准接口；
4. Host 启动时自动识别、自动拉起、自动健康检查、自动加载；
5. 数字人只能通过动作下标控制业务应用，不接触 URL、设备编号、IP、端口或底层控制参数；
6. 更换项目时只替换应用目录内容，不修改 Host。

---

## 2. 两档形态与义务矩阵

V1.1 起，应用包分两档，由第三方按项目自行选择。**判据是配置能不能存住、要不要碰硬件**：

| | **服务档**（`type: "service"`） | **静态档**（`type: "static"`） |
| --- | --- | --- |
| 交付物 | `app.json` + `start.bat` + 业务服务 | `app.json` + 一个静态文件夹 |
| 进程 | Host 隐藏拉起，注入 `WAKEFUSION_APP_TOKEN` | 无进程，Host 托管静态文件 |
| 页面地址 | 第三方在 `app.json` 里写 `pageUrl` | **由 Host 派生**，第三方不写 |
| 控制通道 | HTTP `/api/wakefusion/v1/*` + Bearer | **本版无**（纯展示；postMessage 见第 10 节，规划中） |
| 配置持久化 | 落盘到应用包内，重启保持 | 只能存 `localStorage`，清缓存即丢 |
| 适用 | 要碰机械、PLC、数据库、带密钥的外部接口 | 纯展示 |

> **本版静态档只做展示。** 数字人控制一律走服务档。
> 需要数字人能控制页面，就选服务档——哪怕业务逻辑全在前端，也要有一个最小的本地服务
> 来承载四个 V1 接口。

义务矩阵（**"Host 出力拉起进程，第三方就必须让 Host 能判断它活没活、能不能控"**）：

| 能力 | 服务档 | 静态档 | 图片档 |
| --- | --- | --- | --- |
| `<meta name="wakefusion:embedded-app" content="v1">` | **必须** | 不适用 | 不适用 |
| `GET /api/wakefusion/v1/health` | **必须** | 不适用 | 不适用 |
| `GET /api/wakefusion/v1/status` | **必须** | 不适用 | 不适用 |
| `GET /api/wakefusion/v1/actions` | **必须实现**，可返回空数组 | 不适用 | 不适用 |
| `POST /api/wakefusion/v1/actions/{index}/execute` | **必须** | 不适用 | 不适用 |
| 动作 `description` / `keywords` | 可缺省 | 可缺省 | 不适用 |

**"接口没实现"和"目录暂时为空"是两回事。** 服务档下 `/actions` 必须存在并返回 `200`，
但 `"actions": []` 是合法的（例如动作全被停用）。Host 照常显示页面，只是不注册控制工具。
这样第三方可以先交骨架，不会因为动作还没定就整包失效。

---

## 3. 固定部署目录

应用包必须放在 Host 程序所在目录的一级子目录 `app` 中。

服务档：

```text
<Host目录>\
├─ wakefusion-terminal-host.exe
└─ app\
   ├─ app.json
   ├─ start.bat
   └─ runtime\                 # 业务程序、前端资源、配置
```

静态档：

```text
<Host目录>\
├─ wakefusion-terminal-host.exe
└─ app\
   ├─ app.json
   └─ site\                    # 静态站根目录，名字由 app.json 的 root 指定
      ├─ index.html
      ├─ subscriptconfig.html
      └─ assets\
```

图片档：

```text
<Host目录>\app\
├─ app.json
└─ background.png
```

强制规则：

- Host 只读取 `<Host目录>\app\app.json`，不递归搜索其他 `app.json`；
- 同一台 Host 同一时间只承载一个业务应用；
- 更换项目时整体替换 `app` 目录；
- `app.json` 必须 UTF-8、无注释、不超过 64 KiB；
- 文件名固定小写 `app.json` / `start.bat`；
- 应用包内所有路径必须是 `app` 目录内的相对路径，不得使用绝对路径或 `..`。

---

## 4. `app.json` 唯一格式

### 4.1 服务档

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "appId": "cdut-slider-screen",
  "name": "青藏高原科考滑轨屏",
  "type": "service",
  "pageUrl": "http://127.0.0.1:8000/?embed=1&avatarAnchor=right",
  "interactive": true,
  "startupTimeoutMs": 30000,
  "start": { "file": "start.bat", "args": [] }
}
```

### 4.2 静态档

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "appId": "hall-intro-static",
  "name": "展厅介绍页",
  "type": "static",
  "root": "site",
  "entry": "index.html",
  "interactive": true
}
```

静态档**不写 `pageUrl`、不写 `start`、不写端口**。Host 会在 `127.0.0.1` 上以随机端口
托管 `root` 目录，并自动拼出带 `?embed=1&avatarAnchor=right` 的页面地址。

### 4.3 图片档

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "appId": "static-reception-background",
  "name": "接待背景",
  "type": "image",
  "image": "background.png"
}
```

### 4.4 远程页面

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "appId": "remote-business-page",
  "name": "远程业务页面",
  "type": "service",
  "pageUrl": "https://example.com/display?embed=1&avatarAnchor=right",
  "interactive": true
}
```

远程页面必须 HTTPS，不得提供 `start`。当前版本 Host 未取得远程应用的控制 Token，
远程页面只加载为背景、不调用标准接口、不注册控制工具。

### 4.5 字段定义

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `schemaVersion` | 是 | 固定 `wakefusion.embedded-app/v1` |
| `appId` | 是 | 1～64 位，字母、数字、`-`、`_`；发布后保持稳定 |
| `name` | 是 | 面向运维的中文名称，最长 100 字符 |
| `type` | 是 | `service`、`static` 或 `image`；`web` 作为 `service` 的兼容别名继续接受 |
| `pageUrl` | 服务档必填 | 仅 `http://` / `https://`；本地必须是 `127.0.0.1` 或 `localhost`；远程必须 HTTPS；不得含用户名、密码或片段 |
| `root` | 静态档必填 | `app` 目录内的相对目录名 |
| `entry` | 否 | 静态档入口文件，默认 `index.html` |
| `interactive` | 否 | 默认 `true`；`false` 时页面只展示、不接收触控 |
| `startupTimeoutMs` | 否 | 默认 30000，允许 3000～120000 |
| `start.file` | 服务档（本地）必填 | 固定 `start.bat` |
| `start.args` | 否 | 字符串数组，最多 32 项，每项 ≤500 字符，不经 shell 拼接 |
| `image` | 图片档必填 | `app` 目录内相对路径，png/jpg/webp |

**`app.json` 不接受未知字段。** 多写任何一个字段（例如顺手加的 `healthUrl`、注释字段）
都会让整包判为配置错误、背景不加载。

一律禁止：绝对磁盘路径；`..` 跳出 `app` 目录；`file://`、`javascript:` 等协议；
URL 中携带用户名、密码或永久密钥；在 `app.json` 中保存设备控制地址、PLC 地址或底层设备参数。

---

## 5. Host 自动处理流程

```text
启动 Host
  → 读 app\app.json，校验协议、字段与路径
  → 按 type 分档
      image  → 直接加载图片背景
      static → 在 127.0.0.1 随机端口托管 root，派生 pageUrl
      service→ 先访问 pageUrl；不可访问且有 start.bat 则隐藏拉起
  → 读取页面初始 HTML 的 metadata
  → 声明 V1 → 健康检查 → 读状态 → 读动作目录 → 注册单一控制工具
  → 未声明 V1（仅静态档/远程页允许）→ 只展示，不探测、不注册工具
```

处理原则：

- `app.json` 不存在：Host 使用自己的默认背景，不报致命错误；
- `app.json` 不合法：Host 不加载该应用，管理面板显示配置错误码；
- `pageUrl` 已可访问：Host **不重复执行** `start.bat`；
- 服务档页面未声明 V1 metadata：判为**包做错了**，报 `manifest_declares_service_but_page_is_display_only`，
  不再静默降级为展示模式（否则现场只会看到"背景正常、数字人不听指挥"，最难排查）；
- **动作目录不可用不会拆掉背景**：页面本身正常时，Host 保持页面显示，只关闭控制工具；
- **健康检查驱动恢复**：页面、`health` 或 `status` 探测失败时，前 5 次（约 25 秒）
  **页面保持显示**，Host 只关掉控制工具并在管理面板报错；连续第 6 次判定业务应用假死，
  Host 结束整棵业务进程树并按 1/2/5/10 秒退避重启——**这一刻背景会回落到默认背景**，
  业务应用重新可访问后 Host 自动重新挂载页面；
- Host 拉起的业务进程，在 Host 退出时由 Host 连同进程树一并结束。

---

## 6. `start.bat` 约定（服务档）

```bat
@echo off
setlocal
cd /d "%~dp0"
"%~dp0runtime\business-app.exe" --no-browser
exit /b %errorlevel%
```

Host 行为：工作目录固定为 `<Host目录>\app\`；隐藏窗口运行；标准输出/错误由 Host 接管并落
`embedded-app.log`；通过进程环境变量传入 `WAKEFUSION_APP_TOKEN`；Host 不打开浏览器。

`start.bat` 强制要求：不得使用 `pause`；不得弹交互提示；不得调用默认浏览器；
不得用 `start` 把主程序脱离 Host 进程树；必须前台运行实际服务进程；重复执行不得破坏已有数据；
所有路径基于 `%~dp0`；向业务程序传"不打开浏览器"参数；
**业务后端必须从进程环境变量读取 `WAKEFUSION_APP_TOKEN`，不得写入配置文件或日志。**

> **现场禁令：业务服务只能由 Host 拉起。**
> 禁止手动双击业务 EXE，禁止设开机自启。Token 只通过 spawn 时的环境变量下发；
> 页面已能访问时 Host 会跳过 `start.bat`，手动起的进程手里没有 Token，
> Host 调用健康接口必然 401，结果是"页面在、数字人失控"。

---

## 7. 页面 metadata 声明

支持标准接口的页面必须在初始 HTML 的 `<head>` 中提供，且只能出现一次：

```html
<meta name="wakefusion:embedded-app" content="v1">
```

- Host 请求 `pageUrl` 读取该 metadata，按同源自动派生 `/api/wakefusion/v1/*`；
- Host 不接受 metadata 指定其他 API 地址，避免出现第二套配置或跨域控制地址；
- 使用前端框架时，该 `<meta>` **必须直接存在于服务器返回的初始 HTML**，不能等 JavaScript 执行后插入；
- 页面初始 HTML 必须是 `text/html`、UTF-8、**不超过 2 MB**、**不得有重定向**
  （Host 不跟随 301/302，`/` 跳 `/index.html` 会被判为页面错误）；
- 打包时不要把 JS 全部内联进 HTML（`vite-plugin-singlefile` 一类），很容易超过 2 MB；
  保持 JS/CSS 为外部文件，那些文件不受此限制。

---

## 8. 标准接口（服务档）

命名空间固定：

```text
/api/wakefusion/v1
```

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 启动与健康检查 |
| `GET` | `/status` | 读取业务应用当前状态 |
| `GET` | `/actions` | 读取允许数字人执行的动作目录 |
| `POST` | `/actions/{index}/execute` | 按动作下标执行控制 |

页面可以保留自己的内部 API，Host 和数字人不会调用它们。

### 8.1 通用规则

```http
Authorization: Bearer <WAKEFUSION_APP_TOKEN>
```

- Token 由 Host 首次加载应用时随机生成，保存在 Host 自己的受保护运行状态中，
  通过进程环境变量下发；`appId` 变化时自动轮换；
- 业务应用必须校验 Bearer Token，不得把它写进 `app.json`、`pageUrl`、前端 JS 或日志；
- 鉴权失败返回 HTTP `401` 与错误码 `auth_failed`；
- **所有响应（含 401、503 等错误响应）都必须是 `application/json`**。Host 先看
  `Content-Type` 再看状态码，返回 HTML 错误页会被判为接口不合规；
- 响应头必须带 `Cache-Control: no-store`；
- 本地应用只监听 `127.0.0.1`，不得监听 `0.0.0.0`；
- `health` / `status` / `actions` **必须在 1 秒内返回**，`execute` 在 8 秒内返回。

> **`health` 与 `status` 必须完全非阻塞。**
> 这两个接口每 5 秒被调用一次，超时会触发降级与重启。绝不能在里面等机械动作、
> 等串口、等 PLC 响应或抢业务锁——读一份内存快照就返回。

### 8.2 健康检查

```http
GET /api/wakefusion/v1/health
```

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "ok": true,
  "ready": true,
  "appId": "cdut-slider-screen",
  "version": "1.0.0"
}
```

- HTTP `200`，`ok` 与 `ready` 都为 `true`，Host 才加载页面；
- **`appId` 必须与 `app.json` 完全一致**；
- **`version` 必须非空且不超过 100 字符**；
- 初始化中返回 HTTP `503` 且 `ready: false`，可带 `message`；
- 健康接口不得触发任何业务动作。

### 8.3 读取状态

```http
GET /api/wakefusion/v1/status
```

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "ok": true,
  "state": "idle",
  "activeActionIndex": 2,
  "activeView": "冰川源区",
  "playing": true,
  "actionsHash": "9f2c1ab4",
  "updatedAt": "2026-09-04T10:00:00+08:00"
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `schemaVersion` | 是 | 固定协议标识 |
| `ok` | 是 | 状态读取是否成功 |
| `state` | 是 | `starting`、`idle`、`running`、`paused`、`error` 之一 |
| `activeActionIndex` | 否 | 当前动作下标（0 起） |
| `activeView` | 否 | 当前展项或页面名称 |
| `playing` | 否 | 是否正在播放 |
| `actionsHash` | 否 | 动作目录内容指纹，1～64 位字符串 |
| `updatedAt` | 是 | ISO 8601 时间 |
| `details` | 否 | 面向人类的非敏感补充状态 |

**`actionsHash` 是动作目录的变更信号。** 动作的名称、说明、关键词、启用集合发生任何
变化时换一个新值。Host 每 5 秒读一次状态，发现指纹变化立即重新拉取动作目录并刷新
数字人的工具上下文——配置页保存后 5 秒内生效，不需要重启，也不需要在 Host 里做任何操作。
不提供 `actionsHash` 时 Host 退化为每 30 秒轮询一次动作目录。

`details` 中不得返回密钥、设备序列号、PLC 地址、数据库连接信息或异常堆栈。

`activeActionIndex`、`activeView`、`playing` 会进入数字人的上下文，
让它知道"现在在放什么"，从而正确理解"停一下""下一个""再讲讲这个"。请如实上报。

### 8.4 读取动作目录

```http
GET /api/wakefusion/v1/actions
```

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "ok": true,
  "actions": [
    { "name": "高原启程", "description": "切换到高原启程展项，介绍科考队出发", "keywords": ["启程", "第一页"] },
    { "name": "地质巡测" },
    { "name": "播放", "description": "播放当前展项视频。用户说继续讲、接着放时用这个", "keywords": ["继续讲解"] }
  ]
}
```

**动作目录就是一个数组，没有 `index` 字段，也没有 `revision` 字段。**

- 下标由数组位置现算，**从 0 起**；上例中"高原启程"是 0，"地质巡测"是 1，"播放"是 2；
- **停用的动作不出现在数组里**；停用一项，它后面的动作整体前移；
- 下标是易变的，任何一次保存都可能让目录重排。业务侧不要持久化下标，
  也不要向外承诺某个下标的含义长期不变；
- 数组顺序即语义，所以顺序必须稳定可复现（同样的启用集合每次返回同样的顺序）。

字段规则：

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `name` | 是 | 简短动作名，最长 80 字符 |
| `description` | 否 | 可缺省或为空串；最长 300 字符 |
| `keywords` | 否 | 正例。最多 20 项，每项最长 30 字符 |
| `negativeKeywords` | 否 | 反例：说了这些**不要**选这个动作。最多 20 项，每项最长 30 字符 |

`negativeKeywords` 在数字人的工具召回里是**硬否决**，比正例更能止血。
典型用法是把易混动作互相排除：

```json
{ "name": "停止轮播", "keywords": ["别转了"], "negativeKeywords": ["停一下", "暂停"] }
```

- 一个应用最多返回 100 个动作；
- 只返回允许数字人执行的动作；
- 不得返回请求 URL、请求方法、设备编号、控制值、IP、端口或原始报文；
- 禁止提供"执行任意命令""访问任意 URL""传入任意设备参数"类动作。

**文本硬限制**（`name`、`description`、`keywords` 每一项都适用）：

- 不得包含 `<` 或 `>`；
- 不得包含 `http://`、`https://`、IP 地址或 `IP:端口`；
- 不得包含 `<script`、`javascript:`、`ignore previous`、`system prompt`、
  `忽略系统`、`忽略之前`、`执行任意命令`、`访问任意` 等注入短语；
- 不得包含控制字符。

> **违规是整份拒绝，不是跳过那一条。** 任何一个动作的文本不合规，
> 整个动作目录判为 `action_definition_invalid`，数字人会失去全部控制能力。
> 配置页必须在保存时先做同样的校验（见第 11 节）。

### 8.5 描述里可以写触发条件

`description` 会完整进入数字人的工具上下文，也参与工具召回打分。所以可以这样写：

```json
{ "name": "停止自动巡展", "description": "停止自动巡展并停在当前展项。仅在自动巡展进行中时有意义；用户说停下、别转了、停在这里时用它。不要用于暂停视频。" }
```

**但识别它的是模型，不是 Host。** Host 不解析触发条件、不做规则拦截。
写了"仅在播放时可用"，模型仍可能在未播放时发过来——**业务侧必须自己判状态，
不满足条件时回 HTTP `409` 与 `action_conflict`**，由数字人向用户解释。

### 8.6 执行动作

```http
POST /api/wakefusion/v1/actions/2/execute
Content-Type: application/json
Authorization: Bearer <token>
Idempotency-Key: 5a3d1e22-71bc-4b2e-b83e-5933dd5f6558
```

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "requestId": "5a3d1e22-71bc-4b2e-b83e-5933dd5f6558",
  "source": "wakefusion-host"
}
```

成功响应：

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "ok": true,
  "requestId": "5a3d1e22-71bc-4b2e-b83e-5933dd5f6558",
  "index": 2,
  "message": "已开始播放当前展项",
  "state": { "activeActionIndex": 2, "activeView": "冰川源区", "playing": true }
}
```

规则：

- 路径里的 `index` 是**当前动作目录的下标（0 起）**；
- **`requestId` 必须原样回传请求头 `Idempotency-Key` 的值**，不一致 Host 判为响应不合规；
- **`index` 必须以数字回传且与路径一致**；
- **`message` 必须非空且不超过 500 字符**，数字人会用它向用户确认；
- 相同 `Idempotency-Key` 的重复请求不得重复执行副作用；
- 写操作不得使用 GET；Host 不自动重试写操作；
- 长任务应先受理并返回状态，不要长期阻塞连接。

### 8.7 标准错误响应

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "ok": false,
  "error": { "code": "action_conflict", "message": "当前没有在自动巡展" },
  "requestId": "5a3d1e22-71bc-4b2e-b83e-5933dd5f6558"
}
```

| HTTP | `code` | 含义 |
| --- | --- | --- |
| 400 | `invalid_request` | 请求格式不符合标准 |
| 401 | `auth_failed` | 缺少或未通过 Bearer 鉴权 |
| 404 | `action_not_found` | 下标越界或动作已停用 |
| 409 | `action_conflict` | 当前状态不允许执行 |
| 423 | `application_busy` | 正在执行互斥动作 |
| 429 | `too_many_requests` | 请求过快 |
| 500 | `action_failed` | 动作执行失败 |
| 503 | `application_not_ready` | 应用尚未就绪 |

错误响应不得包含异常堆栈、文件绝对路径或敏感连接信息，并且同样必须是 JSON。

---

## 9. 下标语义与已知窗口

指令组与描述的分工：

- **指令组**（动作的顺序及其对应的内部实现）= 开发期契约，写在代码里；
- **描述**（`name` / `description` / `keywords`）= 运行期配置，可随时通过配置页修改；
- 下标 = 当前启用集合的数组位置，由 Host 现算，不持久化、不需要维护一致性。

> **已知窗口：** 保存那一刻正在飞的调用，可能按旧下标落到相邻动作。
> 这是本设计明确接受的代价，换来的是没有任何需要长期维护一致性的状态。
> **涉及机械动作的项目，配置页保存请避开正在讲解的时段。**

---

## 10. 静态档控制通道（postMessage）——⚠ 规划中，V1.1 未实现

> **本节是设计草案，Host 尚未实现，不要按它开发。**
> 当前版本的静态档只做展示：Host 不监听页面消息，也不会把静态档的动作注册给数字人。
> 需要数字人控制页面，请选服务档（第 8 节的四个 HTTP 接口）。
> 本节保留在这里是为了固定未来的协议形状，实现后会去掉这个标注。

静态档没有后端进程，控制走 `postMessage`。

Host 页面与业务页面**不同源**（Host 在 `tauri://localhost`，业务页在 `127.0.0.1`），
双方都必须校验来源。

页面 → Host：

```js
// 就绪 + 上报动作目录（数组顺序即下标，0 起，字段规则同 8.4）
parent.postMessage({ schemaVersion: "wakefusion.embedded-app/v1", type: "wf.actions",
  actions: [{ name: "下一页" }, { name: "播放" }] }, "*");

// 上报状态（字段同 8.3）
parent.postMessage({ schemaVersion: "wakefusion.embedded-app/v1", type: "wf.status",
  state: "running", activeActionIndex: 1, playing: true }, "*");

// 执行结果
parent.postMessage({ schemaVersion: "wakefusion.embedded-app/v1", type: "wf.result",
  requestId, ok: true, message: "已播放" }, "*");
```

Host → 页面：

```json
{ "schemaVersion": "wakefusion.embedded-app/v1", "type": "wf.execute", "index": 1, "requestId": "..." }
```

- 页面必须校验 `event.source === window.parent`；
- 动作文本仍然要过第 8.4 节的全部硬限制，Host 侧会重复校验，违规同样整份拒绝；
- 页面应在收到 `wf.execute` 后 8 秒内回 `wf.result`；`ok: false` 时带 `errorCode`。

---

## 11. `/subscriptconfig.html` 配置页约定

应用如果允许现场修改动作描述，必须在**页面同源的固定路径** `/subscriptconfig.html`
提供配置页。Host 会探测这个地址，探测到就在管理面板的"嵌入应用"卡片里显示
「打开业务配置」按钮，在 Host 窗口内打开——现场不需要另开浏览器，也不会破坏全屏。

配置页责任：

1. **只允许改文本**：`name`、`description`、`keywords`、启用状态。
   动作的顺序与内部实现是开发期契约，配置页不得提供改动入口；
2. **保存前必须本地校验**，规则与第 8.4 节一字不差（长度、禁 `<` `>`、禁 URL/IP、
   禁注入短语、`keywords` ≤20 项、动作 ≤100 个）。配置页不拦，现场就是
   "改了一句话，数字人所有动作全没了"；
3. **保存后必须更新 `actionsHash`**（内容 hash 或时间戳），由程序自动生成，
   **绝不能让现场人工填写**；
4. **每行实时显示模型看到的下标**（如 `#0`、`#1`，停用行显示 `—`），
   并提示"保存后目录会整体重排"；
5. 配置页自身是运维界面，**不要**声明 `wakefusion:embedded-app` metadata；
6. 静态档的配置页只能存 `localStorage`，换机器或清缓存即丢失；而且本版静态档没有
   动作目录，配置页改的文本**不会进入数字人**，只对页面自己有意义。
   要让描述真正生效，就必须选服务档。

---

## 12. 页面嵌入模式

Host 会在内嵌 iframe 中按下列地址打开业务页面（静态档由 Host 自动附加参数）：

```text
?embed=1&avatarAnchor=right
```

### 12.1 `embed=1`

页面必须：隐藏自己的全屏按钮；隐藏重复的数字人、吉祥物、聊天或语音入口；隐藏管理员入口；
不弹新窗口；不自动打开浏览器；不显示窗口边框或调试入口；保留主要业务导航和触控操作；
适配 Host 全屏尺寸；内容可被 iframe 加载。

### 12.2 `avatarAnchor=right`

数字人主要位于右侧，页面应把右侧约 28% 宽度作为安全区：不放关键标题、主导航、确认按钮；
不放必须持续观察的实时数值；背景装饰可以进入安全区；关键触控区布置在左侧或中部。
未来可能使用 `left`，布局应尽量支持左右镜像。

### 12.3 iframe 限制（两档都适用）

Host 使用的 sandbox 为 `allow-forms allow-pointer-lock allow-same-origin allow-scripts`，
`allow` 仅 `autoplay`。因此：

- **`alert` / `confirm` / `prompt` 会静默失效**（无 `allow-modals`）；
- **`window.open` 无效**（无 `allow-popups`）；
- 页面自己调用全屏 API 无效，全屏由 Host 管理；
- 页面内下载链接不可用；
- 不得返回 `X-Frame-Options: DENY`；如设 CSP，`frame-ancestors` 必须允许 Host；
- 页面不能依赖第三方 Cookie 才能显示基础内容。

### 12.4 分辨率

首选 1920 × 1080，最小支持 1280 × 720；响应式布局，不锁死像素宽度；
100% 缩放无横向滚动条；触控目标不小于 44 × 44 CSS 像素；重要文字对比度不低于 4.5:1。

---

## 13. Host 硬门禁自查清单

以下每一条不满足都会导致加载失败或控制不可用，且现场现象往往只是"背景没出来"：

- [ ] `app.json` 无未知字段、UTF-8、≤64 KiB；
- [ ] 服务档页面初始 HTML 带且只带一个 `wakefusion:embedded-app` metadata；
- [ ] 页面初始 HTML 是 `text/html`、UTF-8、≤2 MB、**无重定向**；
- [ ] `health` 的 `appId` 与 `app.json` 一致，`version` 非空；
- [ ] `status` 已实现，`state` 在五个枚举内，`updatedAt` 非空；
- [ ] `actions` 已实现（可空数组），数组无 `index` 字段；
- [ ] `execute` 回包 `requestId` == `Idempotency-Key`，`index` 为数字且与路径一致，`message` 非空；
- [ ] 所有响应（含 401/503）都是 `application/json`；
- [ ] `health` / `status` / `actions` 1 秒内返回，且不碰机械；
- [ ] 动作文本无 `<` `>`、无 URL/IP、无注入短语；
- [ ] 服务只监听 `127.0.0.1`；
- [ ] `start.bat` 不弹窗、不暂停、不开浏览器、不脱离进程树；
- [ ] 业务服务不设开机自启、现场不手动启动。

---

## 14. 安全约定

本地业务应用必须：只监听 `127.0.0.1`；不把控制接口暴露到局域网；不在前端 JS 中保存控制密钥；
不在动作目录中暴露设备标识和控制值；对下标使用服务端白名单；拒绝越界与未登记的动作；
对控制请求记录时间、`requestId`、下标、执行结果；日志不得记录密钥、完整个人信息或原始设备报文。

远程页面必须 HTTPS，不得把永久 Token 写进 `pageUrl`。

---

## 15. 开发自测

```powershell
$env:WAKEFUSION_APP_TOKEN = "local-development-token"
$h = @{ Authorization = "Bearer $env:WAKEFUSION_APP_TOKEN" }
Invoke-RestMethod http://127.0.0.1:8000/api/wakefusion/v1/health  -Headers $h
Invoke-RestMethod http://127.0.0.1:8000/api/wakefusion/v1/status  -Headers $h
Invoke-RestMethod http://127.0.0.1:8000/api/wakefusion/v1/actions -Headers $h
$rid = [guid]::NewGuid().ToString()
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/wakefusion/v1/actions/0/execute `
  -Headers @{ Authorization = "Bearer $env:WAKEFUSION_APP_TOKEN"; "Idempotency-Key" = $rid } `
  -ContentType "application/json" `
  -Body (@{ schemaVersion = "wakefusion.embedded-app/v1"; requestId = $rid; source = "wakefusion-host" } | ConvertTo-Json -Compress)
```

页面嵌入自测：`http://127.0.0.1:8000/?embed=1&avatarAnchor=right`
配置页自测：`http://127.0.0.1:8000/subscriptconfig.html`

---

## 16. 交付清单

- [ ] 所有文件在一个完整的 `app` 目录内；
- [ ] `app.json` 协议标识与 `type` 正确，无多余字段；
- [ ] 服务档含固定 `start.bat`，且不弹窗、不暂停、不开浏览器；
- [ ] 第 13 节硬门禁逐条通过；
- [ ] 动作目录只暴露名称、说明、关键词，没有下标字段；
- [ ] 改描述并更新 `actionsHash` 后，5 秒内在 Host 生效且无需重启；
- [ ] 相同幂等键不会重复执行控制；
- [ ] `embed=1` 时已隐藏重复数字人、全屏入口和管理员入口；
- [ ] 右侧 28% 安全区没有关键内容；
- [ ] 1920×1080 与 1280×720 正常显示；
- [ ] 提供 `/subscriptconfig.html` 且保存时做完整本地校验；
- [ ] 应用包内没有密码、永久 Token、私钥或客户敏感数据。

---

## 17. 验收标准

1. 把合规 `app` 目录放到 Host 根目录后，无需修改 Host 配置；
2. 启动 Host 后业务应用被自动加载（服务档自动隐藏拉起）；
3. 健康检查通过后业务页面自动成为背景，数字人显示在上层；
4. 用户可以触控业务页面；
5. Host 自动把动作目录加载为单一工具，数字人只用下标执行动作；
6. 在配置页改描述并保存，5 秒内数字人使用新描述，无需重启；
7. 业务应用异常退出或假死时 Host 不退出，能提示并自动重启恢复；
8. 动作目录临时不可用时，业务页面仍然正常显示；
9. 更换另一个合规 `app` 目录后 Host 不需要重新编译。

---

## 18. 从 V1.0 迁移

| 变化 | V1.0 | V1.1 |
| --- | --- | --- |
| `type` | `web` / `image` | `service` / `static` / `image`（`web` 兼容等价 `service`） |
| 静态档 | 无 | 新增，Host 托管目录，不需要服务和 `start.bat` |
| 动作 `index` | 必填、从 1 起、必须永久稳定 | **删除该字段**，下标由数组位置现算，从 0 起，可重排 |
| 动作 `revision` | 必填 | **删除**，改用 `status.actionsHash` 作为变更信号 |
| 动作 `description` | 必填 | 可缺省或为空 |
| 目录刷新 | 30 秒轮询 | `actionsHash` 变化即刷新（约 5 秒） |
| 服务档缺 metadata | 静默降级为展示 | 报配置错误 |
| 动作目录不可用 | 连页面一起降级 | 只关控制，页面继续显示 |
| 健康检查失败 | 只标记降级 | 连续失败驱动进程重启 |
| 配置页 | 无约定 | 固定 `/subscriptconfig.html`，Host 提供入口 |

已按 V1.0 交付的应用包按下列步骤升级：

1. `app.json` 的 `type` 可以保持 `web` 不动；
2. `/actions` 去掉每项的 `index` 字段，按**当前启用顺序**排列数组；
3. 内部把"下标 → 业务动作"的映射改成按数组位置查表，注意**基准从 1 改成 0**；
4. `/actions` 去掉 `revision`，在 `/status` 增加 `actionsHash`；
5. `execute` 按新的下标基准解析路径参数，越界回 `404 action_not_found`；
6. 补 `/subscriptconfig.html`，把描述配置从直接改 JSON 文件改成走配置页。

> **下标基准从 1 改成 0 是本次唯一的破坏性变更。** 与 HD-SCADA 本地指令集
> （`McpGateway`，索引 = 启用集下标、从 0 起）统一，两条指令源并入同一个模型
> 指令集缓存后基准一致，避免差一错误。
