# 成都理工大学校史馆｜极地科考滑轨屏联动播控系统

当前实现覆盖开发文档的 Phase 1–4：极地科考展陈界面、外置内容配置、媒体与场景服务、GET/POST 控制 API、Mock 滑轨与往返轮播。真实硬件协议未实现。

## 开发运行

```powershell
npm.cmd --prefix frontend install
python -m pip install -r requirements.txt
npm.cmd --prefix frontend run build
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

访问 `http://127.0.0.1:8000`；按 `Ctrl + Shift + Alt + M` 打开调试控制面板。

## 可替换资源

- 场景：`config/scenes.json`
- 应用和玩偶映射：`config/app.json`
- 模拟滑轨参数和未来硬件预留：`config/machine.json`
- 视频：`content/videos/`
- 海报：`content/posters/`
- 玩偶：`content/mascots/`

在尚未获得厂家协议前，请保持 `config/machine.json` 的 `provider` 为 `mock`。

硬件协议已实现 TCP/UDP 接入，现场配置与首次联调流程见 [`config/硬件接入说明.md`](config/硬件接入说明.md)。

四段正式影片的命名和放置位置详见 [`content/videos/视频放置说明.md`](content/videos/视频放置说明.md)。
