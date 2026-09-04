# 动态点位与业务控制 API

所有点位只在 `config/points.json` 中维护。新增一个对象后，按 `order` 排序自动进入界面导航、轮播轨迹和 API；修改完成后调用 `POST /api/admin/reload`，无需改前端代码。

```json
{
  "id": "p05",
  "order": 50,
  "title": "新点位标题",
  "navLabel": "短名称",
  "subtitle": "展项说明",
  "videoPath": "content/videos/p05.mp4",
  "posterPath": "content/posters/p05.svg",
  "backgroundPath": "content/backgrounds/p05.png",
  "mascotKey": "main",
  "positionMm": 4800,
  "enabled": true
}
```

以下接口供本项目页面及获授权的普通业务系统调用：

| 目的 | 请求 |
| --- | --- |
| 读取全部可用点位 | `GET /api/points` |
| 切换到一个点位 | `POST /api/control/points/{pointId}/activate` |
| 播放 / 暂停 / 停止 | `POST /api/control/play`、`/pause`、`/stop` |
| 回原点 | `POST /api/control/home` |
| 启动 / 停止自动巡展 | `POST /api/control/carousel/start`、`/carousel/stop` |
| 读取实时状态 | `GET /api/status` 或 WebSocket `/ws` |
| 重新读取配置 | `POST /api/admin/reload` |

`id` 是稳定的外部标识，建议一直使用 `p01`、`p02` 这类格式。`positionMm` 是滑轨的毫米绝对坐标；真实控制器启用后，后端会根据它映射为电机位置。`mascotKey` 可指定 `main`、`moving`、`playing`、`guide` 四个原始玩偶；未指定时页面会按此顺序自动循环。保留的旧接口 `POST /api/control/scene/{id}` 也可使用，但新接入请使用 `/points/{pointId}/activate`。

> WakeFusion 数字人不得直接调用上述内部接口。数字人只调用带 Bearer Token 的 `/api/wakefusion/v1/*` 标准接口，并按 `/actions` 当前返回数组的 0 基索引执行动作。详见《青藏高原科考滑轨屏-WakeFusion数字人接入与部署交接手册》；禁用动作会导致后续索引动态前移。

管理员入口在页面右上角。密码保存于本机 `config/admin.json`（该文件不会提交到 Git）；首次部署时复制 `config/admin.example.json` 为 `config/admin.json` 后修改 `password`。管理员登录成功后，浏览器会获得仅本机有效的会话 Cookie，配置重载和硬件诊断接口都需要该登录状态。
