# 青藏高原科考滑轨屏：WakeFusion 数字人接入与部署交接手册

> 版本：2026-09-03  
> 应用 ID：`cdut-slider-screen`  
> 协议：`wakefusion.embedded-app/v1`  
> 本文是本项目数字人接入、部署和现场联调的唯一交接依据。

## 1. 交付内容

交付给数字人团队的文件：

- `WakeFusion青藏高原科考滑轨屏应用包-Token版-20260903-更新版.zip`
- 本文档

应用包内包含一个固定的 `app` 目录。数字人团队不需要修改或重新编译 WakeFusion Host，不需要 Tauri，也不需要手工打开浏览器。

## 2. 部署步骤

1. 在部署电脑上停止 WakeFusion Host。
2. 解压最新的 Token 版应用包。
3. 将解压得到的 `app` 文件夹整体放到 WakeFusion Host 根目录；如果已有 `app`，先由现场人员备份，再整体替换。
4. 确认目录层级如下，文件和文件夹名称不要改动：

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

5. 启动 WakeFusion Host。Host 会先访问页面；页面不可访问时自动隐藏运行 `app\start.bat`，无需另行启动 EXE。
6. Host 健康检查通过后自动加载页面和动作目录，数字人即可调用动作。

## 3. Token 与安全边界

- WakeFusion Host 必须通过进程环境变量传入 `WAKEFUSION_APP_TOKEN`。
- Host 调用所有 V1 接口时必须携带：

  ```http
  Authorization: Bearer <WAKEFUSION_APP_TOKEN>
  ```

- Token 不得写入 `app.json`、前端代码、配置文件、URL、日志或交接群消息。
- 本应用只监听 `127.0.0.1:8000`，只允许同机 Host 调用；局域网其他设备不能直接访问播控接口。
- 数字人只接触动作索引，不接触滑轨控制器 IP、端口、坐标或原始通讯报文。

## 4. 页面地址与接口

嵌入页面：

```text
http://127.0.0.1:8000/?embed=1&avatarAnchor=right
```

该地址只在部署 WakeFusion Host 的电脑上有效，不是公网访问地址。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/wakefusion/v1/health` | 健康检查；`ready=true` 后加载页面 |
| `GET` | `/api/wakefusion/v1/status` | 获取当前展项、播放状态和应用状态 |
| `GET` | `/api/wakefusion/v1/actions` | 获取数字人可执行动作和 `revision` |
| `POST` | `/api/wakefusion/v1/actions/{index}/execute` | 按索引执行动作 |

执行动作时，Host 还应提供 `Idempotency-Key`，同一幂等键的重复请求不会重复执行控制副作用。写操作失败时 Host 不应自动重试。

## 5. 数字人动作目录

| 索引 | 动作 | 用户可感知结果 | 备注 |
| ---: | --- | --- | --- |
| 1 | 高原启程 | 切换到第一展项 | 对应 `p01` |
| 2 | 地质巡测 | 切换到第二展项 | 对应 `p02` |
| 3 | 冰川源区 | 切换到第三展项 | 对应 `p03` |
| 4 | 高原守望 | 切换到第四展项 | 对应 `p04` |
| 5 | 播放 | 播放当前展项视频 | 不改变点位 |
| 6 | 暂停 | 暂停当前视频 | 不改变点位 |
| 7 | 停止 | 停止视频并回到开头 | 不改变点位 |
| 8 | 返回首页 | 停止巡展并返回机械原点 | 涉及机械动作 |
| 9 | 开始自动巡展 | 按顺序自动切换展项 | 涉及机械动作 |
| 10 | 停止自动巡展 | 停止巡展并保持当前位置 | 不改变当前位置 |

动作名称、说明和关键词可在 `runtime\config\wakefusion.json` 调整。修改后必须同步修改 `revision`，让 Host 重新加载动作目录。

已发布动作的索引不得改变含义、不得重排、不得复用；新增动作请使用新的正整数索引。

## 6. 页面嵌入行为

- `embed=1` 时，页面隐藏本页玩偶、管理员入口和页面全屏入口，避免和数字人重复。
- `avatarAnchor=right` 时，页面右侧预留约 28% 区域给数字人。
- 页面保留主要触控功能：点位切换、视频播放/暂停/停止、静音/音量、左右滑动切换展项。
- 左滑按展项顺序进入下一点位：`p01 → p02 → p03 → p04`；页面视觉导航从右到左显示 `01 → 02 → 03 → 04`。

## 7. 联调验收

数字人团队完成以下检查即可确认接入：

- [ ] Host 启动后，应用在 30 秒内被自动拉起。
- [ ] 健康接口返回 `ok=true` 和 `ready=true`。
- [ ] 数字人显示在右侧，未遮挡页面关键触控区。
- [ ] Host 自动加载 1 至 10 号动作，不需要在 Host 中手工配置动作。
- [ ] 通过数字人调用播放、暂停、停止后，页面视频状态正确变化。
- [ ] 通过数字人切换展项后，页面切换到对应展项。
- [ ] 相同 `Idempotency-Key` 的重复调用不产生重复执行。
- [ ] 接口鉴权失败时返回 `401` 和 `auth_failed`，不泄露敏感配置。

## 8. 现场机械启用

> 安全要求：交付包默认 `runtime\config\machine.json` 为 `provider: "mock"`。模拟模式可验证数字人、页面和动作接口，但不会驱动滑轨。

1. 先在 `mock` 模式完成数字人和页面联调。
2. 由项目实施人员确认急停、限位、运行方向、原点、现场净空以及控制器通讯状态。
3. 仅在上述安全条件确认后，将 `runtime\config\machine.json` 中的 `provider` 改为 `tcp`，并填写现场控制器网络参数。
4. 重启 WakeFusion Host，先做低风险单点测试，再验证四个点位、回原点和自动巡展。
5. 未完成机械确认前，禁止使用数字人语音命令驱动真实滑轨移动。

## 9. 现场可配置项

| 文件 | 可配置内容 | 生效方式 |
| --- | --- | --- |
| `runtime\config\app.json` | 标题、主题文字、按钮名称、品牌与玩偶素材路径 | 管理员面板重新加载或重启 Host |
| `runtime\config\scenes.json` | 视频、海报、展项标题与介绍 | 更新后重新加载或重启 |
| `runtime\config\points.json` | 点位名称、展项绑定、坐标逻辑 | 仅机械调试人员维护 |
| `runtime\config\wakefusion.json` | 动作名称、说明、关键词和 `revision` | 重新加载配置，Host 自动刷新 |
| `runtime\config\machine.json` | 模拟/真实通讯模式及控制器网络参数 | 重启 Host 后生效 |

视频文件放在 `runtime\content\videos`。新增或替换视频时，应同步更新 `scenes.json` 中对应展项的视频路径。

## 10. 常见问题

| 现象 | 优先检查 |
| --- | --- |
| Host 未加载页面 | `app` 目录层级、`app.json` 编码、`start.bat` 是否存在，以及 Host 启动超时设置 |
| 健康检查返回 401 | Host 是否正确传入并携带 `WAKEFUSION_APP_TOKEN`；不要将 Token 写入文件 |
| 数字人没有动作工具 | 页面 metadata、健康接口 `ready`、动作目录授权和 `revision` 是否正常 |
| 页面正常但滑轨不动 | 是否仍为 `mock`；真实模式下检查控制器状态、通讯、限位和安全条件 |
| 修改动作文字后未生效 | 是否更新了 `wakefusion.json` 的 `revision`，并重新加载配置 |

## 11. 交付结论

本应用已按 WakeFusion 嵌入应用 V1 规范完成 Web 服务接入。数字人团队只需替换 `app` 目录、启动 Host 并完成标准动作验收；无需 Tauri 打包、无需改造 Host、无需接触滑轨底层控制参数。
