import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Scene = { id: number; name: string; navLabel: string; subtitle: string; videoPath: string; posterPath: string; backgroundPath: string };
type Status = {
  currentScene: number | null; targetScene: number | null; motorState: string; playbackState: string;
  carouselMode: boolean; carouselDirection: string; videoId: string | null; error: string | null;
};

const fallbackScenes: Scene[] = [
  { id: 1, name: '科考启程', navLabel: '启程', subtitle: '从成都出发，向极地进发', videoPath: '/content/videos/scene-1.mp4', posterPath: '/content/posters/scene-1.svg', backgroundPath: '/content/backgrounds/scene-1-polar-station.png' },
  { id: 2, name: '冰川探索', navLabel: '冰川', subtitle: '穿越冰原，记录地球的年轮', videoPath: '/content/videos/scene-2.mp4', posterPath: '/content/posters/scene-2.svg', backgroundPath: '/content/backgrounds/scene-2-glacier-route.png' },
  { id: 3, name: '科学观测', navLabel: '观测', subtitle: '以严谨丈量极地的脉搏', videoPath: '/content/videos/scene-3.mp4', posterPath: '/content/posters/scene-3.svg', backgroundPath: '/content/backgrounds/scene-3-observation-station.png' },
  { id: 4, name: '科考精神', navLabel: '精神', subtitle: '把探索写进时代的坐标', videoPath: '/content/videos/scene-4.mp4', posterPath: '/content/posters/scene-4.svg', backgroundPath: '/content/backgrounds/scene-4-expedition-spirit.png' }
];

type DisplayConfig = { mascots: Record<string, string>; scenes: Scene[] };
const fallbackConfig: DisplayConfig = {
  scenes: fallbackScenes,
  mascots: {
    main: '/content/mascots/mascot-main.png', moving: '/content/mascots/mascot-moving.png',
    playing: '/content/mascots/mascot-playing.png', guide: '/content/mascots/mascot-guide.png', error: '/content/mascots/mascot-guide.png'
  }
};

const defaultStatus: Status = { currentScene: 1, targetScene: null, motorState: 'arrived', playbackState: 'idle', carouselMode: false, carouselDirection: 'forward', videoId: null, error: null };
const label: Record<string, string> = { idle: '待命', moving: '滑轨移动中', arrived: '已到位', loading: '内容装载中', playing: '正在播放', paused: '已暂停', stopped: '已停止', error: '需要关注' };

function App() {
  const [status, setStatus] = useState<Status>(defaultStatus);
  const [admin, setAdmin] = useState(() => new URLSearchParams(window.location.search).get('admin') === '1');
  const [displayConfig, setDisplayConfig] = useState<DisplayConfig>(fallbackConfig);
  const videoRef = useRef<HTMLVideoElement>(null);
  const activeId = status.targetScene ?? status.currentScene ?? 1;
  const activeScene = useMemo(() => displayConfig.scenes.find((scene) => scene.id === activeId) ?? displayConfig.scenes[0], [activeId, displayConfig]);

  const loadStatus = useCallback(async () => {
    try { setStatus(await (await fetch('/api/status')).json() as Status); } catch { /* the visual demo also works without the service */ }
  }, []);
  const command = useCallback(async (path: string) => { await fetch(`/api/control/${path}`, { method: 'POST' }); await loadStatus(); }, [loadStatus]);

  useEffect(() => {
    void loadStatus();
    void fetch('/api/display-config').then((response) => response.ok ? response.json() as Promise<DisplayConfig> : Promise.reject()).then(setDisplayConfig).catch(() => undefined);
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as { type: string; data: Status };
      if (message.type === 'status') setStatus(message.data);
    };
    return () => socket.close();
  }, [loadStatus]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.shiftKey && event.altKey && event.key.toLowerCase() === 'm') setAdmin((value) => !value);
    };
    addEventListener('keydown', handler);
    return () => removeEventListener('keydown', handler);
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (status.playbackState === 'playing') void video.play().catch(() => undefined);
    if (status.playbackState === 'paused') video.pause();
    if (status.playbackState === 'stopped') { video.pause(); video.currentTime = 0; }
  }, [status.playbackState, activeId]);

  const videoVisible = status.playbackState === 'playing' || status.playbackState === 'paused';
  const mascotMode = status.error ? 'error' : status.motorState === 'moving' ? 'moving' : status.playbackState === 'playing' ? 'playing' : status.playbackState === 'paused' || status.playbackState === 'stopped' ? 'guide' : 'main';

  return <main className="exhibit-shell">
    <div className="scene-backdrop" style={{ backgroundImage: `url("${activeScene.backgroundPath}")` }} /><div className="snow snow-a" /><div className="snow snow-b" />
    <header className="masthead">
      <div className="brand"><span className="brand-mark">CG</span><div><p>成都理工大学校史馆</p><h1>极地科考 <i>POLAR EXPEDITION</i></h1></div></div>
      <div className="coordinate"><span>71° 18′ S</span><b>·</b><span>12° 06′ E</span><small>SCIENCE · EXPLORATION · HERITAGE</small></div>
    </header>

    <section className="presentation">
      <aside className="scene-intro"><span className="eyebrow">EXHIBIT / {String(activeScene.id).padStart(2, '0')}</span><h2>{activeScene.name}</h2><p>{activeScene.subtitle}</p><div className="rule" /><small>极地地质科考专题展陈</small></aside>
      <div className={`media-frame ${status.motorState === 'moving' ? 'is-moving' : ''}`}>
        <div className="frame-corner top-left" /><div className="frame-corner top-right" /><div className="frame-corner bottom-left" /><div className="frame-corner bottom-right" />
        <div className="video-stage">
          <img className="poster" src={activeScene.posterPath} alt="场景海报" />
          <video ref={videoRef} className={videoVisible ? 'visible' : ''} src={activeScene.videoPath} poster={activeScene.posterPath} muted playsInline onError={() => undefined} />
          <div className="stage-overlay"><span>成都理工大学校史馆 · 极地科考专题展</span></div>
          <div className="touch-controls" role="group" aria-label="触屏播放控制">
            <button type="button" onClick={() => void command('play')}>播放</button>
            <button type="button" onClick={() => void command('pause')}>暂停</button>
            <button type="button" onClick={() => void command('stop')}>停止</button>
            <button type="button" className={status.carouselMode ? 'selected' : ''} onClick={() => void command(`carousel/${status.carouselMode ? 'stop' : 'start'}`)}>{status.carouselMode ? '停止巡展' : '自动巡展'}</button>
            <button type="button" onClick={() => void command('home')}>回原点</button>
          </div>
          {status.motorState === 'moving' && <div className="moving-cover"><div className="radar" /><strong>滑轨正在移动至 P{activeId}</strong><span>抵达后将自动播放对应内容</span></div>}
          {status.error && <div className="moving-cover error-cover"><strong>设备正在调整，请稍候</strong><span>{status.error}</span></div>}
        </div>
      </div>
    </section>

    <div className="mascot-wrap" data-mode={mascotMode}><div className="mascot-callout"><span>{mascotMode === 'main' ? '极地地质科考员' : '极地科考导览员'}</span><b>{status.motorState === 'moving' ? '正在前往新展点' : mascotMode === 'main' ? '地质锤，敲开探索之门' : '探索，从这里出发'}</b></div><img src={displayConfig.mascots[mascotMode] ?? displayConfig.mascots.main} alt="极地科考玩偶" /></div>
    <nav className="station-nav" aria-label="场景点位">{displayConfig.scenes.map((scene) => <button className={scene.id === activeId ? 'active' : ''} key={scene.id} onClick={() => void command(`scene/${scene.id}`)}><em>{String(scene.id).padStart(2, '0')}</em><span>{scene.navLabel}</span></button>)}</nav>
    <footer><span>CHENGDU UNIVERSITY OF TECHNOLOGY · MUSEUM OF HISTORY</span><div className="track"><i /><i /><i /><i /></div><span>{status.carouselMode ? 'PING-PONG AUTO TOUR' : 'POLAR RAIL DISPLAY SYSTEM'}</span></footer>
    {admin && <section className="admin-panel"><button className="close" onClick={() => setAdmin(false)}>×</button><span>管理员调试面板</span><div className="admin-status">滑轨：{label[status.motorState] ?? status.motorState}　影片：{label[status.playbackState] ?? status.playbackState}　巡展：{status.carouselMode ? '往返轮播' : '手动控制'}</div><div>{displayConfig.scenes.map((scene) => <button key={scene.id} onClick={() => void command(`scene/${scene.id}`)}>场景 {scene.id}</button>)}</div><div><button onClick={() => void command('play')}>播放</button><button onClick={() => void command('pause')}>暂停</button><button onClick={() => void command('stop')}>停止</button><button onClick={() => void command('home')}>回原点</button></div><div><button onClick={() => void command('carousel/start')}>启动轮播</button><button onClick={() => void command('carousel/stop')}>停止轮播</button></div><small>快捷键 Ctrl + Shift + Alt + M</small></section>}
  </main>;
}

createRoot(document.getElementById('root')!).render(<App />);
