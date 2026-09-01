# WakeFusion 数字人接入说明

本项目以本地 Web 服务方式接入 WakeFusion，不使用 Tauri 或独立桌面窗口。控制器网络参数、毫米坐标和原始通讯报文只保留在 `runtime\\config` 内，不会通过 WakeFusion 接口暴露。

## 部署

将交付包中的整个 `app` 文件夹复制为 WakeFusion Host 所在目录的一级子目录：

```text
<WakeFusion Host目录>\\
├─ wakefusion-terminal-host.exe
└─ app\\
   ├─ app.json
   ├─ start.bat
   └─ runtime\\
```

Host 会先请求健康接口；未就绪时自动隐藏执行 `app\\start.bat`。脚本以前台方式运行服务，不打开浏览器，也不使用 `start` 脱离 Host 进程树。

## 页面和健康地址

- 嵌入页面：`http://127.0.0.1:8000/?embed=1&avatarAnchor=right`
- 健康检查：`http://127.0.0.1:8000/api/wakefusion/v1/health`
- 状态：`http://127.0.0.1:8000/api/wakefusion/v1/status`
- 动作目录：`http://127.0.0.1:8000/api/wakefusion/v1/actions`

服务只监听 `127.0.0.1:8000`。这不会影响服务端主动连接滑轨控制器 `192.168.1.104`，但会阻止局域网其他设备直接调用播控接口。

## 嵌入页面行为

`embed=1` 时，页面隐藏自身玩偶、管理员入口和全屏按钮；右侧预留约 28% 宽度给数字人。将 `avatarAnchor=right` 改为 `left` 可使用左侧安全区布局。

普通滑轨屏页面仍使用：`http://127.0.0.1:8000/`。

## 数字人动作

数字人只通过 `POST /api/wakefusion/v1/actions/{index}/execute` 执行下列稳定动作：

| index | 动作 |
| ---: | --- |
| 1–4 | 切换四个展项 |
| 5–7 | 播放、暂停、停止视频 |
| 8 | 返回首页/机械原点 |
| 9–10 | 开始、停止自动巡展 |

动作的名称、关键词和内部映射由 `runtime\\config\\wakefusion.json` 管理。不要重排已经发布的 index；新增动作请使用新的正整数。

## 现场配置

首次使用请保持 `runtime\\config\\machine.json` 中的 `provider: "mock"`。确认控制器协议、IP、端口和安全条件后，再改为 `tcp`。WakeFusion 接入测试不应直接执行真实滑轨移动。
