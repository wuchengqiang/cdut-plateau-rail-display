# WakeFusion 嵌入应用开发与部署约定 V1

文档版本：1.0  
协议标识：`wakefusion.embedded-app/v1`  
适用对象：业务页面开发人员、UI 设计人员、项目交付人员、WakeFusion Host 开发人员  
状态：正式开发约定

---

## 1. 目标

WakeFusion Host 负责数字人、语音交互、业务应用启动、页面承载和 API 调用。业务应用负责自己的页面与业务逻辑。

每个项目只需要交付一个符合本约定的“应用包”。Host 程序本身不因客户页面、行业页面或项目接口不同而重新定制。

本约定要求：

1. 只有一个固定应用目录；
2. 只有一个应用描述文件；
3. 只有一套标准 API；
4. Host 启动时自动识别、自动拉起、自动健康检查、自动加载；
5. 数字人只能通过动作 `index` 控制业务应用，不接触 URL、设备编号、IP、端口或底层控制参数；
6. 更换项目时只替换应用目录内容，不修改 Host。

---

## 2. 固定部署目录

业务应用必须放在 Host 程序所在目录的一级子目录 `app` 中：

```text
<Host目录>\
├─ wakefusion-terminal-host.exe
├─ app\
│  ├─ app.json
│  ├─ start.bat                 # 本地 Web 应用需要；远程网页或纯图片可不提供
│  ├─ background.png            # 图片背景模式使用
│  └─ runtime\                  # 业务程序、前端资源、后端资源等
└─ managed\                     # Host 自身运行数据，业务开发人员不要修改
```

以当前本地测试部署为例，固定目录是：

```text
D:\git\industrial-assistant\dist\wakefusion-terminal\app\
```

强制规则：

- Host 只读取 `<Host目录>\app\app.json`；
- Host 不递归搜索其他 `app.json`；
- 不设置“当前应用”、应用 ID 指针或额外 Host 配置；
- 同一台 Host 同一时间只承载一个业务应用；
- 更换项目时，整体替换 `app` 目录；
- `app.json` 必须使用 UTF-8 编码，不允许注释；
- 文件名固定为小写 `app.json` 和 `start.bat`。

`app.json` 是应用包的一部分，不是交付现场需要手工填写的 Host 配置。

---

## 3. Host 自动处理流程

Host 每次启动必须执行以下固定流程：

```text
启动 Host
  → 检查 app\app.json
  → 校验协议版本和文件路径
  → 识别 image / web 类型
  → 请求 pageUrl 并读取页面 metadata
  → 本地页面不可达时隐藏执行 start.bat
  → 页面声明 V1 时等待健康接口 ready=true
  → 加载图片或网页背景
  → 页面声明 V1 时读取标准动作目录
  → 页面声明 V1 时向数字人开放 index 控制工具
```

处理原则：

- `app.json` 不存在：Host 使用自己的默认背景，不报致命错误；
- `app.json` 不符合标准：Host 不启动该应用，显示“应用包配置错误”；
- `pageUrl` 已经可以访问：Host 不重复执行 `start.bat`；
- `pageUrl` 不可访问且存在 `start.bat`：Host 隐藏执行 `start.bat`；
- 页面 metadata 声明支持 V1：Host 执行健康检查并加载动作目录；
- 页面未声明支持 V1：Host 只加载页面，不探测健康接口、不注册控制工具；
- 页面或健康检查启动超时：Host 保留数字人和默认背景，显示“业务应用暂时不可用”，并自动重试；
- Host 拉起的业务进程，在 Host 正常退出时由 Host 结束；
- 远程网页不由 Host 启动；是否执行健康检查由页面 metadata 决定。

---

## 4. `app.json` 唯一格式

### 4.1 本地 Web 应用

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "appId": "cdut-slider-screen",
  "name": "青藏高原科考滑轨屏",
  "type": "web",
  "pageUrl": "http://127.0.0.1:8000/?embed=1&avatarAnchor=right",
  "interactive": true,
  "startupTimeoutMs": 30000,
  "start": {
    "file": "start.bat",
    "args": []
  }
}
```

### 4.2 远程网页

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "appId": "remote-business-page",
  "name": "远程业务页面",
  "type": "web",
  "pageUrl": "https://example.com/display?embed=1&avatarAnchor=right",
  "interactive": true,
  "startupTimeoutMs": 30000
}
```

远程网页不提供 `start`，Host 不执行本地启动命令。

### 4.3 图片背景

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "appId": "static-reception-background",
  "name": "接待背景",
  "type": "image",
  "image": "background.png"
}
```

图片模式不要求实现控制 API。

### 4.4 字段定义

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `schemaVersion` | 是 | 固定为 `wakefusion.embedded-app/v1` |
| `appId` | 是 | 1～64 位，只允许字母、数字、`-`、`_`；发布后保持稳定 |
| `name` | 是 | 面向运维人员的中文应用名称，最长 100 字符 |
| `type` | 是 | 只能是 `web` 或 `image` |
| `pageUrl` | Web 必填 | 仅允许 `http://` 或 `https://`，不得包含用户名和密码 |
| `interactive` | 否 | 默认 `true`；`false` 时页面只展示、不接收触控 |
| `startupTimeoutMs` | 否 | 默认 30000；允许 3000～120000 |
| `start.file` | 本地 Web 必填 | V1 固定使用 `start.bat` |
| `start.args` | 否 | 字符串数组，不通过 shell 拼接 |
| `image` | 图片必填 | 必须是 `app` 目录内的相对路径 |

以下内容一律禁止：

- 绝对磁盘路径；
- `..` 跳出 `app` 目录；
- `file://`、`javascript:` 等协议；
- URL 中携带用户名、密码或永久密钥；
- 在 `app.json` 中保存设备控制地址、PLC 地址或底层设备参数。

### 4.5 Web 应用 metadata 声明

Web 应用通过 HTML `<meta>` 声明是否支持 WakeFusion V1 API，不在 `app.json` 中填写健康检查地址。

支持 V1 API 的页面必须在 HTML `<head>` 中提供：

```html
<meta name="wakefusion:embedded-app" content="v1">
```

Host 请求 `pageUrl` 并读取该 metadata：

- metadata 存在且 `content="v1"`：Host 按页面同源地址自动派生 `/api/wakefusion/v1/*`，执行健康检查并加载动作工具；
- metadata 不存在：该页面被视为纯展示页面，Host 不执行健康检查、不读取状态和动作目录；
- metadata 值不是 `v1`：Host 不启用控制能力，并记录“不支持的嵌入应用协议”；
- 标准 API 必须与 `pageUrl` 同协议、同主机、同端口；
- Host 不接受 metadata 指定其他 API URL，避免产生第二套配置或跨域控制地址。

页面使用前端框架时，该 `<meta>` 必须直接存在于服务器返回的初始 HTML 中，不能等 JavaScript 执行后再动态插入。

---

## 5. `start.bat` 启动约定

本地 Web 应用必须提供：

```text
<Host目录>\app\start.bat
```

Host 行为：

- 工作目录固定为 `<Host目录>\app\`；
- 使用隐藏窗口方式运行；
- 标准输入、标准输出和错误输出由 Host 接管；
- Host 在启动前先检查 `pageUrl` 是否可访问，避免重复拉起；
- Host 启动本地应用时，通过进程环境变量传入本机安装实例的 `WAKEFUSION_APP_TOKEN`；
- Host 不打开浏览器；
- Host 不要求项目安装到系统目录或注册 Windows 服务。

`start.bat` 强制要求：

- 不得使用 `pause`；
- 不得弹出交互提示；
- 不得调用默认浏览器；
- 不得使用 `start` 将主程序脱离 Host 进程树；
- 必须以前台方式运行实际服务进程；
- 重复执行时不得破坏已有数据；
- 所有路径必须基于 `%~dp0`；
- 应向业务程序传入“不打开浏览器”参数。
- 业务后端必须从进程环境变量读取 `WAKEFUSION_APP_TOKEN`，不得把它写入配置文件或日志。

推荐模板：

```bat
@echo off
setlocal
cd /d "%~dp0"
"%~dp0runtime\business-app.exe" --no-browser
exit /b %errorlevel%
```

如果业务程序本身就是单个 EXE，也仍然建议由固定的 `start.bat` 负责启动。这样 Host 不需要识别不同 EXE 名称。

---

## 6. 唯一标准 API

所有可控制的 Web 应用必须只实现以下 V1 API 命名空间：

```text
/api/wakefusion/v1
```

V1 对 Host 公开且必须保持稳定的接口只有四个：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/wakefusion/v1/health` | 启动与健康检查 |
| `GET` | `/api/wakefusion/v1/status` | 读取业务应用当前状态 |
| `GET` | `/api/wakefusion/v1/actions` | 读取允许数字人执行的动作目录 |
| `POST` | `/api/wakefusion/v1/actions/{index}/execute` | 按动作索引执行控制 |

页面可以保留自己的内部 API，但 Host 和数字人不得调用这些内部 API。

### 6.1 通用响应头

Host 调用四个 V1 API 时只使用一种鉴权方式：

```http
Authorization: Bearer <WAKEFUSION_APP_TOKEN>
```

鉴权规则：

- 本地应用的 Token 由 Host 首次加载应用时随机生成，保存在 Host 自己的受保护运行状态中，并通过进程环境变量 `WAKEFUSION_APP_TOKEN` 传给业务应用；
- Host 调用健康、状态、动作目录和动作执行接口时都携带同一个标准请求头；
- 业务应用必须校验 Bearer Token，不得把 Token 写入 `app.json`、`pageUrl`、前端 JavaScript 或日志；
- Token 不写入业务应用目录；同一 Host 安装实例重启时继续使用，检测到 `appId` 变化后由 Host 自动轮换；
- 远程应用的 Token 由 WakeFusion 平台安全下发给 Host 和远程应用，不增加第二种鉴权协议；
- Host 未取得远程应用 Token 时，只加载远程页面，不调用 V1 API、不注册控制工具；
- 鉴权失败返回 HTTP `401` 和标准错误码 `auth_failed`。

所有接口必须返回：

```http
Content-Type: application/json; charset=utf-8
Cache-Control: no-store
```

本地应用必须只监听 `127.0.0.1`，不得默认监听 `0.0.0.0`。

### 6.2 健康检查

请求：

```http
GET /api/wakefusion/v1/health
```

成功响应：

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "ok": true,
  "ready": true,
  "appId": "cdut-slider-screen",
  "version": "1.0.0"
}
```

规则：

- HTTP 状态必须是 `200`；
- `ok` 和 `ready` 都必须为 `true`，Host 才加载页面；
- 正在初始化时返回 HTTP `503`，并设置 `ready: false`；
- 接口应在 1 秒内返回；
- 健康接口不得触发业务动作。

初始化响应示例：

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "ok": true,
  "ready": false,
  "appId": "cdut-slider-screen",
  "version": "1.0.0",
  "message": "正在加载业务数据"
}
```

### 6.3 读取状态

请求：

```http
GET /api/wakefusion/v1/status
```

成功响应：

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "ok": true,
  "state": "idle",
  "activeActionIndex": 1,
  "activeView": "高原启程",
  "playing": false,
  "updatedAt": "2026-09-01T10:00:00+08:00"
}
```

标准字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `schemaVersion` | 是 | 固定协议标识 |
| `ok` | 是 | 状态读取是否成功 |
| `state` | 是 | `starting`、`idle`、`running`、`paused`、`error` 之一 |
| `activeActionIndex` | 否 | 当前动作索引 |
| `activeView` | 否 | 当前页面或展项名称 |
| `playing` | 否 | 是否正在播放 |
| `updatedAt` | 是 | ISO 8601 时间 |
| `details` | 否 | 面向人类的非敏感补充状态对象 |

`details` 中不得返回密钥、设备序列号、PLC 地址、数据库连接信息或内部异常堆栈。

### 6.4 读取动作目录

请求：

```http
GET /api/wakefusion/v1/actions
```

成功响应：

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "ok": true,
  "revision": "actions-20260901-01",
  "actions": [
    {
      "index": 1,
      "name": "高原启程",
      "description": "切换到高原启程展项",
      "keywords": ["启程", "第一页", "开始"]
    },
    {
      "index": 5,
      "name": "播放",
      "description": "播放当前展项内容",
      "keywords": ["播放", "继续讲解"]
    }
  ]
}
```

动作规则：

- `revision` 是 1～64 位的非空字符串，只用于判断动作目录是否发生变化，不要求递增；
- 动作的 `index`、名称、描述、关键词、启用状态或执行映射发生变化时，必须更换 `revision`；
- 动作目录没有变化时，`revision` 必须保持不变；
- `index` 是唯一控制参数，必须是正整数；
- 同一个应用版本内不得重复；
- 已发布动作的 `index` 必须保持稳定，删除后的 `index` 不得分配给其他含义的动作；
- `name` 是简短动作名，最长 80 字符；
- `description` 必须说明用户可感知的结果，最长 300 字符；
- `keywords` 用于自然语言匹配，每项最长 30 字符，最多 20 项；
- 一个应用最多返回 100 个动作；
- 只返回允许数字人执行的动作；
- 不得返回请求 URL、请求方法、设备编号、控制值、IP、端口或原始报文；
- 禁止提供“执行任意命令”“访问任意 URL”“传入任意设备参数”类动作。

动作名称、描述和关键词可以由业务应用的管理界面修改。修改保存后，业务应用必须立即发布新的 `revision`，不需要重启 Host。

### 6.5 动作目录自动注册为工具

业务应用健康检查通过后，Host 必须自动读取动作目录，并把有效动作加载到数字人的工具上下文中。现场人员不需要在 Host 中再次配置动作。

Host 只注册一个统一控制工具：

```text
wf_execute_action(index)
```

工具参数 Schema：

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "index": {
      "type": "integer",
      "minimum": 1,
      "description": "从当前业务应用动作目录中选择的动作索引"
    }
  },
  "required": ["index"]
}
```

Host 自动生成的工具描述示例：

```text
控制当前业务应用。只能使用下列动作索引：
1：高原启程——切换到高原启程展项
2：地质巡测——切换到地质巡测展项
5：播放——播放当前展项内容
6：暂停——暂停当前内容
```

工具注册规则：

- Host 不得为每个动作分别注册一个工具；
- Host 不得要求模型先调用另一个工具读取动作目录；
- 动作目录直接进入 `wf_execute_action` 的工具描述；
- 模型只能传入整数 `index`，不得传入 URL、请求方法、设备标识或业务参数；
- Host 收到工具调用后，转换为标准的 `POST /api/wakefusion/v1/actions/{index}/execute`；
- 动作目录为空时，Host 不注册 `wf_execute_action`；
- 动作目录不可用时，Host 保留数字人对话能力，但不提供业务控制工具；
- 工具执行成功后，数字人使用业务接口返回的 `message` 向用户确认；
- 写操作失败或断线时不得自动重试，避免重复控制。

自动刷新规则：

1. Host 在业务应用首次健康就绪后立即读取动作目录；
2. Host 至少每 30 秒检查一次动作目录；
3. Host 每次启动都重新读取当前目录和当前动作目录，不使用历史目录覆盖现场文件；
4. 同一次 Host 运行期间，`revision` 未变化时不重建工具上下文；
5. 同一次 Host 运行期间，`revision` 发生变化时，Host 校验全部动作并生成新的工具快照；
6. 已经开始的一轮对话继续使用该轮开始时冻结的旧快照；
7. 下一轮对话自动使用新快照；
8. 新目录校验失败时，Host 拒绝本次更新并继续使用本次运行期间最后一个有效快照；
9. 业务应用重新启动或健康状态从异常恢复后，Host 立即重新读取动作目录。

可修改范围：

- `name`、`description` 和 `keywords` 可以修改；
- 动作可以新增或停用；
- `index` 对应的业务含义不得修改；
- 如需改变已有 `index` 的含义，必须停用旧动作并使用一个新的 `index`。

动作文本会进入模型上下文，因此还必须满足：

- 只能描述动作的业务含义和用户可感知结果；
- 不得包含要求模型忽略系统规则、改变角色或泄露信息的指令；
- 不得包含 HTML、脚本、控制字符、密钥或内部接口信息；
- Host 必须对文本做长度、控制字符和结构校验；
- Host 将动作文本视为业务数据，不将其解释为新的系统指令。

### 6.6 执行动作

请求：

```http
POST /api/wakefusion/v1/actions/1/execute
Content-Type: application/json
Idempotency-Key: 5a3d1e22-71bc-4b2e-b83e-5933dd5f6558
```

请求体：

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
  "index": 1,
  "message": "已切换到高原启程",
  "state": {
    "activeActionIndex": 1,
    "activeView": "高原启程",
    "playing": false
  }
}
```

规则：

- Host 只提交路径中的 `index`；
- 页面后端负责把 `index` 映射到内部业务逻辑；
- 写操作不得使用 GET；
- 相同 `Idempotency-Key` 的重复请求不得重复执行副作用；
- Host 不自动重试写操作；
- 接口应在 8 秒内返回；
- 长任务应先受理并返回状态，不要长期阻塞连接。

### 6.7 标准错误响应

```json
{
  "schemaVersion": "wakefusion.embedded-app/v1",
  "ok": false,
  "error": {
    "code": "action_not_found",
    "message": "动作不存在或未启用"
  },
  "requestId": "5a3d1e22-71bc-4b2e-b83e-5933dd5f6558"
}
```

标准错误码：

| HTTP | `code` | 含义 |
| --- | --- | --- |
| 400 | `invalid_request` | 请求格式不符合标准 |
| 401 | `auth_failed` | 缺少或未通过标准 Bearer Token 鉴权 |
| 404 | `action_not_found` | 动作不存在或未启用 |
| 409 | `action_conflict` | 当前状态不允许执行 |
| 423 | `application_busy` | 应用正在执行互斥动作 |
| 429 | `too_many_requests` | 请求过快 |
| 500 | `action_failed` | 动作执行失败 |
| 503 | `application_not_ready` | 应用尚未就绪 |

错误响应不得包含内部异常堆栈、文件绝对路径或敏感连接信息。

---

## 7. 页面嵌入模式

Host 会按 `pageUrl` 在内嵌浏览器中打开业务页面。业务页面必须支持查询参数：

```text
?embed=1&avatarAnchor=right
```

### 7.1 `embed=1`

当 `embed=1` 时，页面必须：

- 隐藏自己的全屏按钮；
- 隐藏重复的数字人、吉祥物、聊天入口或语音入口；
- 不弹出新窗口；
- 不自动打开浏览器；
- 不显示桌面窗口边框或调试入口；
- 保留主要业务导航和触控操作；
- 适配 Host 全屏尺寸；
- 页面内容可被 iframe 加载。

### 7.2 `avatarAnchor=right`

表示数字人主要位于右侧。页面应把右侧约 28% 宽度作为数字人安全区：

- 不放置关键标题、主导航、确认按钮；
- 不放置必须持续观察的实时数值；
- 背景装饰可以进入安全区；
- 关键触控区应布置在左侧或中部。

未来可能使用 `left`，页面布局应尽量支持左右镜像。

### 7.3 iframe 响应头

页面不得返回阻止 Host 嵌入的响应头：

- 不得设置 `X-Frame-Options: DENY`；
- 不得设置 `X-Frame-Options: SAMEORIGIN`，除非页面与 Host 确实同源；
- 如设置 CSP，`frame-ancestors` 必须允许 WakeFusion Host；
- 页面不能依赖第三方 Cookie 才能显示基础内容。

### 7.4 分辨率与缩放

页面必须满足：

- 首选设计基准：1920 × 1080；
- 最小支持：1280 × 720；
- 使用响应式布局，不锁死像素宽度；
- 浏览器缩放 100% 时无横向滚动条；
- 触控目标建议不小于 44 × 44 CSS 像素；
- 重要文字与背景对比度不低于 4.5:1。

---

## 8. 音频、视频与全屏限制

- 业务页面可以播放自身视频；
- 页面应优先使用用户触控或 Host 动作触发播放；
- 自动播放必须兼容浏览器的 autoplay 限制；
- 页面不得独占麦克风；麦克风由 Host 和数字人统一管理；
- 页面不得启动自己的语音识别；
- 页面不得主动进入浏览器全屏；全屏由 Host 管理；
- 页面播放音频时，应避免与数字人播报同时发声；
- 收到暂停或停止动作后，应及时停止媒体音频。

---

## 9. 安全约定

本地业务应用必须：

- 只监听 `127.0.0.1`；
- 不把控制接口暴露到局域网；
- 不在前端 JavaScript 中保存控制密钥；
- 不在动作目录中暴露设备标识和控制值；
- 对动作 `index` 使用服务端白名单；
- 拒绝未登记的动作；
- 对控制请求记录时间、`requestId`、动作 `index`、执行结果；
- 日志不得记录密钥、完整个人信息或原始设备报文。

远程网页必须使用 HTTPS，并使用与本地应用相同的标准 Bearer Token 请求头。不得把永久 Token 写进 `pageUrl`。

---

## 10. 当前滑轨屏应用的标准动作建议

当前青藏高原科考滑轨屏应对外提供以下稳定动作目录：

| `index` | 名称 | 内部现有功能 |
| ---: | --- | --- |
| 1 | 高原启程 | 切换到 `p01` |
| 2 | 地质巡测 | 切换到 `p02` |
| 3 | 冰川源区 | 切换到 `p03` |
| 4 | 高原守望 | 切换到 `p04` |
| 5 | 播放 | 播放当前内容 |
| 6 | 暂停 | 暂停当前内容 |
| 7 | 停止 | 停止当前内容 |
| 8 | 返回首页 | 回到原点或首页 |
| 9 | 开始自动巡展 | 启动轮播 |
| 10 | 停止自动巡展 | 停止轮播 |

当前滑轨屏应用必须直接实现四个 V1 标准接口。Host 不识别、不调用、不兼容该应用原有的项目接口；其他业务页面也必须按 Host 的 V1 约束进行修改。

---

## 11. 最小开发示例

以下伪代码说明页面后端需要实现的结构：

```python
@app.get("/api/wakefusion/v1/health")
async def wakefusion_health():
    return {
        "schemaVersion": "wakefusion.embedded-app/v1",
        "ok": True,
        "ready": runtime.is_ready,
        "appId": "cdut-slider-screen",
        "version": "1.0.0",
    }

@app.get("/api/wakefusion/v1/actions")
async def wakefusion_actions():
    return {
        "schemaVersion": "wakefusion.embedded-app/v1",
        "ok": True,
        "revision": ACTION_DIRECTORY_REVISION,
        "actions": ACTION_DIRECTORY,
    }

@app.post("/api/wakefusion/v1/actions/{index}/execute")
async def wakefusion_execute(index: int, request: Request):
    action = ACTION_HANDLERS.get(index)
    if action is None:
        raise HTTPException(status_code=404, detail="action_not_found")
    result = await action()
    return {
        "schemaVersion": "wakefusion.embedded-app/v1",
        "ok": True,
        "requestId": request.headers.get("Idempotency-Key"),
        "index": index,
        "message": result.message,
        "state": result.state,
    }
```

业务应用可以使用任意开发语言和框架，只要 HTTP 行为与 JSON 格式符合本约定。

---

## 12. 开发自测命令

应用启动后，开发人员至少执行：

```powershell
$env:WAKEFUSION_APP_TOKEN = "local-development-token"
$authHeaders = @{ Authorization = "Bearer $env:WAKEFUSION_APP_TOKEN" }
Invoke-RestMethod http://127.0.0.1:8000/api/wakefusion/v1/health -Headers $authHeaders
Invoke-RestMethod http://127.0.0.1:8000/api/wakefusion/v1/status -Headers $authHeaders
Invoke-RestMethod http://127.0.0.1:8000/api/wakefusion/v1/actions -Headers $authHeaders
$requestId = [guid]::NewGuid().ToString()
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/wakefusion/v1/actions/1/execute `
  -Headers @{
    Authorization = "Bearer $env:WAKEFUSION_APP_TOKEN"
    "Idempotency-Key" = $requestId
  } `
  -ContentType "application/json" `
  -Body (@{
    schemaVersion = "wakefusion.embedded-app/v1"
    requestId = $requestId
    source = "wakefusion-host"
  } | ConvertTo-Json -Compress)
```

页面嵌入自测地址：

```text
http://127.0.0.1:8000/?embed=1&avatarAnchor=right
```

---

## 13. 交付清单

页面开发团队交付前必须确认：

- [ ] 所有文件已放入一个完整的 `app` 目录；
- [ ] `app.json` 协议标识正确；
- [ ] 本地应用包含固定的 `start.bat`；
- [ ] `start.bat` 不弹窗、不暂停、不打开浏览器；
- [ ] 服务只监听 `127.0.0.1`；
- [ ] 页面初始 HTML 已正确声明 WakeFusion V1 metadata；
- [ ] 四个 V1 API 都校验标准 Bearer Token；
- [ ] 健康接口能正确区分初始化和就绪；
- [ ] 四个 V1 API 全部通过；
- [ ] 动作目录包含稳定且在内容变化时更新的字符串 `revision`；
- [ ] 动作目录只暴露 `index`、名称、说明和关键词；
- [ ] 修改动作描述并增加 `revision` 后，无需重启业务程序即可读取新目录；
- [ ] 相同幂等键不会重复执行控制；
- [ ] `embed=1` 时已隐藏重复数字人和全屏入口；
- [ ] 右侧数字人安全区没有关键内容；
- [ ] 页面可在 1920 × 1080 和 1280 × 720 正常显示；
- [ ] 页面没有阻止 iframe 加载；
- [ ] 断开业务程序时 Host 能显示故障提示；
- [ ] 重新启动业务程序后 Host 能自动恢复页面；
- [ ] 应用包内没有密码、永久 Token、私钥或客户敏感数据。

---

## 14. 验收结论标准

同时满足以下条件才算完成 WakeFusion 嵌入应用接入：

1. 把合规 `app` 目录放到 Host 根目录后，无需修改 Host 配置；
2. 启动 Host 后，业务应用被自动隐藏拉起；
3. 健康检查通过后，业务页面被自动加载为背景；
4. 数字人仍显示在页面上层；
5. 用户可以触控业务页面；
6. Host 自动把动作目录加载为单一工具，数字人只用 `index` 执行动作；
7. Host 重启后自动恢复；
8. 业务应用异常退出时 Host 不退出，并能提示和重试；
9. 更换另一个合规 `app` 目录后，Host 不需要重新编译。
