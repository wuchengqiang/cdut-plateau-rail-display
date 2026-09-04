# 青藏高原科考滑轨屏：WakeFusion 数字人接入与部署交接手册

> 版本：2026-09-04
>
> 应用 ID：`cdut-slider-screen`
>
> 协议：WakeFusion 嵌入应用 V1.1（`wakefusion.embedded-app/v1`）
>
> 本文是本项目数字人接入、部署和现场联调的唯一交接依据。

## 1. 交付内容

交付给数字人团队：

- `WakeFusion青藏高原科考滑轨屏应用包-V1.1-Token版-20260904.zip`
- 本交接手册
- 参考协议：`第三方对接标准/WakeFusion嵌入应用开发与部署约定V1.1.md`

应用包 SHA-256：`C6CFC49A7B7E68AAB18BEF3770CDB6A36864BD8FEC9676CA1A2C254DAC19193B`。

应用包内只有一个固定的 `app` 目录。它是由 WakeFusion Host 托管的本机 Web 服务，不需要 Tauri，也不应由现场人员手工双击 EXE、设置开机自启或另开浏览器。

## 2. 部署步骤

1. 停止部署电脑上的 WakeFusion Host。
2. 解压 V1.1 应用包。
3. 将解压得到的 `app` 文件夹整体放入 WakeFusion Host 根目录；如已有旧 `app`，先备份再整体替换。
4. `app/runtime/config/admin.json` 的默认管理员密码是 `2468`；如需修改，密码不得少于 4 位。
5. 确认目录层级：

   ```text
   <WakeFusion Host目录>\
   ├─ wakefusion-terminal-host.exe
   └─ app\
      ├─ app.json
      ├─ start.bat
      └─ runtime\
         ├─ 青藏高原科考滑轨屏服务.exe
         ├─ config\
         └─ content\
   ```

6. 启动 WakeFusion Host。Host 检测页面不可访问时，会隐藏运行 `app/start.bat` 并等待健康检查通过。
7. Host 加载页面和动作目录后，数字人即可调用动作。

## 3. Token 与安全边界

- Host 必须通过进程环境变量传入 `WAKEFUSION_APP_TOKEN`。
- Host 调用四个 V1 接口时必须携带：

  ```http
  Authorization: Bearer <WAKEFUSION_APP_TOKEN>
  ```

- Token 不得写入 `app.json`、前端、配置文件、URL、日志或交接消息。
- 应用仅监听 `127.0.0.1:8000`；数字人不接触控制器 IP、端口、点位坐标和底层通讯报文。
- WakeFusion 只能调用本手册列出的 V1 接口，不能直接调用项目内部 `/api/control/*` 接口。

## 4. 页面地址与标准接口

嵌入页面：

```text
http://127.0.0.1:8000/?embed=1&avatarAnchor=right
```

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/wakefusion/v1/health` | 健康检查，`ready=true` 后加载页面 |
| `GET` | `/api/wakefusion/v1/status` | 当前展项、播放状态及 `actionsHash` |
| `GET` | `/api/wakefusion/v1/actions` | 获取当前启用的动作数组 |
| `POST` | `/api/wakefusion/v1/actions/{index}/execute` | 按当前动作数组的 0 基索引执行 |

执行请求必须同时提供相同的 `requestId` 与 `Idempotency-Key`。同一幂等键的重复请求不会再次产生机械或播放副作用；写操作失败时 Host 不应自动重试。

## 5. 当前动作目录

当前全部动作启用时，动态索引如下：

| 当前索引 | 动作 | 结果 |
| ---: | --- | --- |
| 0 | 高原启程 | 切换到 `p01` |
| 1 | 地质巡测 | 切换到 `p02` |
| 2 | 冰川源区 | 切换到 `p03` |
| 3 | 高原守望 | 切换到 `p04` |
| 4 | 播放 | 播放或继续当前视频 |
| 5 | 暂停 | 暂停当前视频 |
| 6 | 停止 | 停止视频并回到开头 |
| 7 | 返回首页 | 停止巡展并返回机械原点 |
| 8 | 开始自动巡展 | 按展项顺序自动切换 |
| 9 | 停止自动巡展 | 停在当前展项 |

V1.1 索引不是永久编号，而是 `/actions` 当前启用数组的位置。禁用一个动作后，后续索引会前移；Host 必须以最新 `/actions` 响应为准，不得缓存旧索引长期调用。应用状态中的 `actionsHash` 会在公开文字、启用状态或顺序变化时改变，Host 每 5 秒轮询状态并重新拉取动作目录。

## 6. 动作配置页面

管理员在本机访问：

```text
http://127.0.0.1:8000/subscriptconfig.html
```

登录后可以修改动作名称、说明、正向关键词、反向关键词和启用状态。页面会显示保存后的动态索引并自动生成新的 `actionsHash`；不能修改内部处理器、点位目标或排序。

为避免配置保存和机械动作产生索引竞态，只能在滑轨静止、自动巡展停止且视频未播放时保存。不要直接编辑 `config/wakefusion.json`。

## 7. 页面嵌入行为

- `embed=1` 时隐藏本页玩偶、管理员入口和页面全屏入口，避免与数字人叠加。
- `avatarAnchor=right` 时右侧预留数字人区域。
- 页面保留点位触控、播放/暂停/停止、静音/音量和左右滑动切换。
- 左滑按 `p01 → p02 → p03 → p04` 切换，同时发送对应点位移动命令；视觉导航从右到左排列 `01 → 02 → 03 → 04`。
- 不使用浏览器弹窗、新窗口、下载或全屏 API，满足 Host 沙箱约束。

## 8. 联调验收

- [ ] Host 启动后应用在 30 秒内被自动拉起，现场没有手工启动服务。
- [ ] 健康接口返回 `ok=true`、`ready=true`。
- [ ] `/actions` 返回数组，条目不含 `index` 和 `revision`。
- [ ] `/status` 返回 64 位十六进制 `actionsHash`。
- [ ] 数字人位于右侧且不遮挡关键触控区。
- [ ] 调用当前 0–9 动作后，页面和滑轨状态符合预期。
- [ ] 相同幂等键重复调用不重复执行。
- [ ] 非法状态返回 `409 action_conflict`，鉴权失败返回 `401 auth_failed`。
- [ ] 修改一个动作文字或启用状态后，Host 能根据新哈希重新加载动态索引。

## 9. 现场机械启用

> 交付包默认 `runtime/config/machine.json` 为 `provider: "mock"`，不会驱动滑轨。

1. 先在 `mock` 模式完成 Host、数字人、页面和动作接口联调。
2. 现场确认急停、限位、方向、原点、净空和控制器通讯。
3. 仅由实施人员将 `runtime/config/machine.json` 的 `provider` 改为 `tcp`。
4. 重启 Host，先测试单点，再依次验证四个点位、回原点和自动巡展。
5. 未完成机械安全确认前，禁止用数字人语音驱动真实滑轨。

当前已确认参数：控制器 `192.168.1.104:8080`；原点 `0 mm`；展示点依次为 `-1600`、`-3200`、`-4800`、`-6400 mm`；SharedKey 和客户端白名单均未启用。

## 10. 现场可配置项

| 位置 | 可配置内容 | 生效方式 |
| --- | --- | --- |
| `runtime/config/app.json` | 标题、主题、按钮文字、校徽与玩偶路径 | 管理员重载或重启 Host |
| `runtime/config/points.json` | 点位名称、视频、介绍、坐标和素材 | 管理员重载或重启 Host |
| 动作配置页面 | 动作文字、关键词、反向关键词和启用状态 | 保存后哈希自动变化 |
| `runtime/config/machine.json` | `mock/tcp` 和控制器网络参数 | 重启 Host |

视频放在 `runtime/content/videos`，并在 `points.json` 中配置对应路径。点位按钮名称、页面文字和动作提示均不需要写入前端代码。

## 11. 常见问题

| 现象 | 优先检查 |
| --- | --- |
| Host 未加载页面 | `app` 层级、`app.json` UTF-8 编码、`start.bat` 和启动超时 |
| 健康接口返回 401 | Host 是否传入并携带 `WAKEFUSION_APP_TOKEN` |
| 数字人没有动作工具 | 页面 metadata、`ready`、动作授权和 `actionsHash` |
| 修改动作后未生效 | 是否从配置页保存；Host 是否检测到新 `actionsHash` 并重新获取 `/actions` |
| 动作索引调用错误 | 必须使用最新启用动作数组的 0 基位置，不能使用旧固定编号 |
| 页面正常但滑轨不动 | 是否仍为 `mock`；真实模式检查通讯、限位和安全条件 |

## 12. 交付结论

本应用已按 WakeFusion 嵌入应用 V1.1 的 `service` 模式完成对齐。数字人团队只需替换 `app` 目录、由 Host 启动服务并按动态动作目录验收；无需 Tauri、无需改造 Host、无需接触滑轨底层参数。
