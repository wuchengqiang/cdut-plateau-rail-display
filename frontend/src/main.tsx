import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type TouchEvent as ReactTouchEvent } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Point = { id: string; order: number; title: string; navLabel: string; subtitle: string; videoPath: string; posterPath: string; backgroundPath: string; mascotKey?: string };
type Status = {
  currentScene: string | null; targetScene: string | null; currentPointId?: string | null; targetPointId?: string | null;
  motorState: string; playbackState: string; carouselMode: boolean; carouselDirection: string; videoId: string | null; error: string | null;
};
type Labels = Record<string, string>;
type DisplayConfig = {
  title: string; themeTitle: string; themeSubtitle: string; brandEnglish: string; coordinatePrimary: string; coordinateSecondary: string; pointPrefix: string; coordinateLabel: string; emblemPath: string;
  labels: Labels; mascots: Record<string, string>; points: Point[];
};

const fallbackPoints: Point[] = [
  { id: 'p01', order: 10, title: '高原启程', navLabel: '启程', subtitle: '从成都出发，走进青藏高原的科学现场', videoPath: '/content/videos/p01.mp4', posterPath: '/content/posters/p01.svg', backgroundPath: '/content/backgrounds/p01-plateau-base.png', mascotKey: 'main' },
  { id: 'p02', order: 20, title: '地质巡测', navLabel: '巡测', subtitle: '循着岩层与断裂带，解读高原的地质密码', videoPath: '/content/videos/p02.mp4', posterPath: '/content/posters/p02.svg', backgroundPath: '/content/backgrounds/p02-geology-route.png', mascotKey: 'moving' },
  { id: 'p03', order: 30, title: '冰川源区', navLabel: '冰川', subtitle: '追踪冰川变化，守护江河源头生态', videoPath: '/content/videos/p03.mp4', posterPath: '/content/posters/p03.svg', backgroundPath: '/content/backgrounds/p03-glacier-source.png', mascotKey: 'playing' },
  { id: 'p04', order: 40, title: '高原守望', navLabel: '守望', subtitle: '以科学之志，守望世界屋脊', videoPath: '/content/videos/p04.mp4', posterPath: '/content/posters/p04.svg', backgroundPath: '/content/backgrounds/p04-plateau-spirit.png', mascotKey: 'guide' }
];

const fallbackConfig: DisplayConfig = {
  title: '成都理工大学校史馆', themeTitle: '青藏高原科考', themeSubtitle: '青藏高原地质与生态科考专题展',
  brandEnglish: 'QINGHAI–TIBET PLATEAU SCIENTIFIC EXPEDITION', coordinatePrimary: 'QINGHAI–TIBET PLATEAU', coordinateSecondary: 'EXPEDITION', pointPrefix: 'POINT', coordinateLabel: '高海拔综合科学考察', emblemPath: '/content/branding/cdut-emblem.svg',
  points: fallbackPoints,
  mascots: { main: '/content/mascots/mascot-main-original.png', moving: '/content/mascots/mascot-moving-original.png', playing: '/content/mascots/mascot-playing-original.png', guide: '/content/mascots/mascot-guide-original.png', error: '/content/mascots/mascot-guide-original.png' },
  labels: { play: '播放', pause: '暂停', stop: '停止', mute: '静音', unmute: '开启声音', volume: '音量', autoTour: '自动巡展', stopTour: '停止巡展', home: '回原点', fullScreen: '全屏播放', exitFullScreen: '退出全屏', playCurrent: '播放当前视频', swipeHint: '左右滑动切换展项', swipeLocked: '滑轨移动中，请稍候', swipeBoundary: '已到达当前方向的最后展项', swipeSwitching: '正在切换到', adminEntry: '管理员入口', adminLoginTitle: '管理员验证', adminPassword: '请输入管理密码', adminLogin: '进入面板', adminCancel: '取消', adminPasswordError: '密码不正确，请重试', hardwarePing: '硬件 Ping', hardwarePingSuccess: '控制器响应：', hardwarePingFailed: '控制器未通过 Ping：', arriving: '正在前往', arrivedHint: '抵达后将自动播放对应内容', mascotMainTitle: '地质科考伙伴', mascotGuideTitle: '科考导览伙伴', mascotMainText: '地质锤，敲开探索之门', mascotGuideText: '探索，从这里出发' }
};
const defaultStatus: Status = { currentScene: 'p01', targetScene: null, motorState: 'arrived', playbackState: 'idle', carouselMode: false, carouselDirection: 'forward', videoId: null, error: null };
const stateLabel: Record<string, string> = { idle: '待命', moving: '滑轨移动中', arrived: '已到位', loading: '内容装载中', playing: '正在播放', paused: '已暂停', stopped: '已停止', error: '需要关注' };
const pageParameters = new URLSearchParams(window.location.search);
const embedMode = pageParameters.get('embed') === '1';
const avatarAnchor = pageParameters.get('avatarAnchor') === 'left' ? 'left' : 'right';

function App() {
  const [status, setStatus] = useState<Status>(defaultStatus);
  const [admin, setAdmin] = useState(false);
  const [adminLoginOpen, setAdminLoginOpen] = useState(false);
  const [adminPassword, setAdminPassword] = useState('');
  const [adminLoginError, setAdminLoginError] = useState('');
  const [hardwareMessage, setHardwareMessage] = useState('');
  const [displayConfig, setDisplayConfig] = useState<DisplayConfig>(fallbackConfig);
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<HTMLDivElement>(null);
  const swipeStart = useRef<{ x: number; y: number } | null>(null);
  const [fullScreen, setFullScreen] = useState(false);
  const [videoMuted, setVideoMuted] = useState(() => localStorage.getItem('rail-video-muted') !== 'false');
  const [volume, setVolume] = useState(() => {
    const saved = Number(localStorage.getItem('rail-video-volume'));
    return Number.isFinite(saved) && saved >= 0 && saved <= 1 ? saved : .6;
  });
  const [swipeMessage, setSwipeMessage] = useState('');
  const activeId = status.targetPointId ?? status.targetScene ?? status.currentPointId ?? status.currentScene ?? displayConfig.points[0]?.id;
  const activePoint = useMemo(() => displayConfig.points.find((point) => point.id === activeId) ?? displayConfig.points[0], [activeId, displayConfig]);
  const labels = { ...fallbackConfig.labels, ...displayConfig.labels };

  const loadStatus = useCallback(async () => {
    try { setStatus(await (await fetch('/api/status')).json() as Status); } catch { /* 离线演示仍可查看界面 */ }
  }, []);
  const command = useCallback(async (path: string) => { await fetch(`/api/control/${path}`, { method: 'POST' }); await loadStatus(); }, [loadStatus]);
  const activate = useCallback(async (id: string) => { await fetch(`/api/control/points/${encodeURIComponent(id)}/activate`, { method: 'POST' }); await loadStatus(); }, [loadStatus]);

  useEffect(() => {
    void loadStatus();
    void fetch('/api/display-config').then((response) => response.ok ? response.json() as Promise<DisplayConfig> : Promise.reject()).then((config) => setDisplayConfig({ ...fallbackConfig, ...config, points: config.points?.length ? config.points : fallbackPoints, labels: { ...fallbackConfig.labels, ...config.labels } })).catch(() => undefined);
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
    socket.onmessage = (event) => { const message = JSON.parse(event.data) as { type: string; data: Status }; if (message.type === 'status') setStatus(message.data); };
    return () => socket.close();
  }, [loadStatus]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if (event.ctrlKey && event.shiftKey && event.altKey && event.key.toLowerCase() === 'm') setAdmin((value) => !value); };
    addEventListener('keydown', handler);
    return () => removeEventListener('keydown', handler);
  }, []);

  useEffect(() => {
    const handleFullscreen = () => setFullScreen(document.fullscreenElement === playerRef.current);
    document.addEventListener('fullscreenchange', handleFullscreen);
    return () => document.removeEventListener('fullscreenchange', handleFullscreen);
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (status.playbackState === 'playing') void video.play().catch(() => undefined);
    if (status.playbackState === 'paused') video.pause();
    if (status.playbackState === 'stopped') { video.pause(); video.currentTime = 0; }
  }, [status.playbackState, activeId]);

  useEffect(() => {
    const video = videoRef.current;
    if (video) {
      video.muted = videoMuted;
      video.volume = volume;
    }
    localStorage.setItem('rail-video-muted', String(videoMuted));
    localStorage.setItem('rail-video-volume', String(volume));
  }, [videoMuted, volume, activeId]);

  if (!activePoint) return null;
  const videoVisible = status.playbackState === 'playing' || status.playbackState === 'paused';
  const pointNumber = String(displayConfig.points.findIndex((point) => point.id === activePoint.id) + 1).padStart(2, '0');
  const mascotKeys = ['main', 'moving', 'playing', 'guide'];
  const mascotKey = activePoint.mascotKey ?? mascotKeys[(Number(pointNumber) - 1) % mascotKeys.length];
  const toggleFullscreen = async () => {
    if (embedMode) return;
    if (document.fullscreenElement) await document.exitFullscreen();
    else await playerRef.current?.requestFullscreen();
  };
  const loginAdmin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAdminLoginError('');
    const response = await fetch('/api/admin/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: adminPassword }) });
    if (!response.ok) { setAdminLoginError(labels.adminPasswordError); return; }
    await fetch('/api/admin/reload', { method: 'POST' });
    setAdminPassword('');
    setAdminLoginOpen(false);
    setAdmin(true);
  };
  const hardwarePing = async () => {
    try {
      const response = await fetch('/api/admin/hardware/ping', { method: 'POST' });
      const result = await response.json() as { success: boolean; reply?: string; message?: string };
      setHardwareMessage(result.success ? `${labels.hardwarePingSuccess}${result.reply ?? 'PONG'}` : `${labels.hardwarePingFailed}${result.message ?? '未知错误'}`);
    } catch {
      setHardwareMessage(`${labels.hardwarePingFailed}网络请求失败`);
    }
  };
  const setVideoVolume = (value: number) => {
    setVolume(value);
    setVideoMuted(value === 0);
  };
  const toggleMute = () => {
    if (videoMuted && volume === 0) setVolume(.6);
    setVideoMuted((muted) => !muted);
  };
  const beginSwipe = (event: ReactTouchEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('button, input')) return;
    const touch = event.touches[0];
    if (touch) swipeStart.current = { x: touch.clientX, y: touch.clientY };
  };
  const finishSwipe = (event: ReactTouchEvent<HTMLDivElement>) => {
    const start = swipeStart.current;
    swipeStart.current = null;
    const touch = event.changedTouches[0];
    if (!start || !touch) return;
    const distanceX = touch.clientX - start.x;
    const distanceY = touch.clientY - start.y;
    const threshold = Math.max(56, window.innerWidth * .05);
    if (Math.abs(distanceX) < threshold || Math.abs(distanceX) < Math.abs(distanceY) * 1.3) return;
    if (status.motorState === 'moving' || status.targetPointId || status.targetScene) {
      setSwipeMessage(labels.swipeLocked);
      return;
    }
    const currentIndex = displayConfig.points.findIndex((point) => point.id === activePoint.id);
    const nextIndex = currentIndex + (distanceX < 0 ? 1 : -1);
    const nextPoint = displayConfig.points[nextIndex];
    if (!nextPoint) {
      setSwipeMessage(labels.swipeBoundary);
      return;
    }
    setSwipeMessage(`${labels.swipeSwitching} ${nextPoint.navLabel}`);
    void activate(nextPoint.id);
  };

  return <main className={`exhibit-shell ${embedMode ? `embed-mode avatar-anchor-${avatarAnchor}` : ''}`} style={{ backgroundImage: `url("${activePoint.backgroundPath}")` }}>
    <div className="terrain-lines" />
    <header className="masthead">
      <div className="brand"><img className="brand-emblem" src={displayConfig.emblemPath} alt="成都理工大学校徽" /><div><p>{displayConfig.title}</p><h1>{displayConfig.themeTitle} <i>{displayConfig.brandEnglish}</i></h1></div></div>
      <div className="header-actions"><div className="coordinate"><span>{displayConfig.coordinatePrimary}</span><b>·</b><span>{displayConfig.coordinateSecondary}</span><small>{displayConfig.coordinateLabel}</small></div>{!embedMode && <button className="admin-entry" type="button" onClick={() => { setAdminLoginError(''); setAdminLoginOpen(true); }}>{labels.adminEntry}</button>}</div>
    </header>
    <section className="presentation">
      <aside className="scene-intro"><span className="eyebrow">{displayConfig.pointPrefix} / {pointNumber}</span><h2>{activePoint.title}</h2><p>{activePoint.subtitle}</p><div className="rule" /><small>{displayConfig.themeSubtitle}</small></aside>
      <div className="media-stack">
      <div ref={playerRef} className={`media-frame ${status.motorState === 'moving' ? 'is-moving' : ''}`}>
        <div className="frame-corner top-left" /><div className="frame-corner top-right" /><div className="frame-corner bottom-left" /><div className="frame-corner bottom-right" />
        <div className="video-stage" onTouchStart={beginSwipe} onTouchEnd={finishSwipe} onTouchCancel={() => { swipeStart.current = null; }}><img className="poster" src={activePoint.posterPath} alt={`${activePoint.title}海报`} /><video ref={videoRef} className={videoVisible ? 'visible' : ''} src={activePoint.videoPath} poster={activePoint.posterPath} muted={videoMuted} playsInline controls={false} onError={() => undefined} />
          {!videoVisible && <button className="poster-play" type="button" onClick={() => void command('play')} aria-label={labels.playCurrent}><span>▶</span>{labels.playCurrent}</button>}
          <button className="fullscreen-exit" type="button" onClick={() => void toggleFullscreen()}>{labels.exitFullScreen}</button>
          <div className="stage-overlay"><span>{displayConfig.title} · {displayConfig.themeTitle}</span><span className="swipe-tip" aria-live="polite">{swipeMessage || labels.swipeHint}</span></div>
          {status.motorState === 'moving' && <div className="moving-cover"><div className="radar" /><strong>{labels.arriving} {activePoint.title}</strong><span>{labels.arrivedHint}</span></div>}
          {status.error && <div className="moving-cover error-cover"><strong>设备正在调整，请稍候</strong><span>{status.error}</span></div>}
        </div>
      </div>
      <div className="control-dock" aria-label="展项控制"><div className="playback-controls" role="group" aria-label="视频播放控制"><button onClick={() => void command('play')}>{labels.play}</button><button onClick={() => void command('pause')}>{labels.pause}</button><button onClick={() => void command('stop')}>{labels.stop}</button><button className={videoMuted ? 'selected' : ''} onClick={toggleMute}>{videoMuted ? labels.unmute : labels.mute}</button><label className="volume-control"><span>{labels.volume}</span><input type="range" min="0" max="1" step="0.05" value={videoMuted ? 0 : volume} onChange={(event) => setVideoVolume(Number(event.target.value))} aria-label={labels.volume} /></label></div><div className="rail-controls" role="group" aria-label="滑轨控制"><button className={status.carouselMode ? 'selected' : ''} onClick={() => void command(`carousel/${status.carouselMode ? 'stop' : 'start'}`)}>{status.carouselMode ? labels.stopTour : labels.autoTour}</button><button onClick={() => void command('home')}>{labels.home}</button>{!embedMode && <button onClick={() => void toggleFullscreen()}>{fullScreen ? labels.exitFullScreen : labels.fullScreen}</button>}</div></div>
      </div>
    </section>
    {!embedMode && <div className="mascot-wrap" data-mode={mascotKey}><div className="mascot-callout"><span>{mascotKey === 'main' ? labels.mascotMainTitle : labels.mascotGuideTitle}</span><b>{mascotKey === 'main' ? labels.mascotMainText : labels.mascotGuideText}</b></div><img src={displayConfig.mascots[mascotKey] ?? displayConfig.mascots.main} alt="科考主题玩偶" /></div>}
    <nav className="station-nav" aria-label="可配置点位">{displayConfig.points.map((point, index) => <button className={point.id === activeId ? 'active' : ''} key={point.id} onClick={() => void activate(point.id)}><em>{String(index + 1).padStart(2, '0')}</em><span>{point.navLabel}</span></button>)}</nav>
    <footer><span>{displayConfig.brandEnglish}</span><div className="track">{displayConfig.points.map((point) => <i key={point.id} className={point.id === activeId ? 'active' : ''} />)}</div><span>{status.carouselMode ? 'PING-PONG AUTO TOUR' : 'PLATEAU RAIL DISPLAY SYSTEM'}</span></footer>
    {!embedMode && adminLoginOpen && <div className="admin-login-backdrop"><form className="admin-login" onSubmit={loginAdmin}><h2>{labels.adminLoginTitle}</h2><label>{labels.adminPassword}<input autoFocus type="password" value={adminPassword} onChange={(event) => setAdminPassword(event.target.value)} required /></label>{adminLoginError && <p role="alert">{adminLoginError}</p>}<div><button type="button" onClick={() => setAdminLoginOpen(false)}>{labels.adminCancel}</button><button type="submit">{labels.adminLogin}</button></div></form></div>}
    {!embedMode && admin && <section className="admin-panel"><button className="close" onClick={() => setAdmin(false)}>×</button><span>管理员调试面板</span><div className="admin-status">滑轨：{stateLabel[status.motorState] ?? status.motorState}　影片：{stateLabel[status.playbackState] ?? status.playbackState}　巡展：{status.carouselMode ? '往返轮播' : '手动控制'}</div><div>{displayConfig.points.map((point) => <button key={point.id} onClick={() => void activate(point.id)}>{point.id} · {point.title}</button>)}</div><div><button onClick={() => void command('play')}>{labels.play}</button><button onClick={() => void command('pause')}>{labels.pause}</button><button onClick={() => void command('stop')}>{labels.stop}</button><button onClick={() => void command('home')}>{labels.home}</button></div><div><button onClick={() => void command('carousel/start')}>启动轮播</button><button onClick={() => void command('carousel/stop')}>停止轮播</button><button onClick={() => void hardwarePing()}>{labels.hardwarePing}</button></div>{hardwareMessage && <small className="hardware-message">{hardwareMessage}</small>}</section>}
  </main>;
}

createRoot(document.getElementById('root')!).render(<App />);
