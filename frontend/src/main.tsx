import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type PointerEvent as ReactPointerEvent, type TouchEvent as ReactTouchEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { makeEndedFeedback, readMediaMetrics, synchronizeMedia } from './media-controller';
import './exhibit.css';

type Point = { id: string; order: number; title: string; navLabel: string; subtitle: string; videoPath: string; posterPath: string; backgroundPath: string; mascotKey?: string; contentType?: 'video' | 'imageText'; videoAvailable?: boolean; imagePath?: string; contentText?: string };
type Status = {
  currentScene: string | null; targetScene: string | null; currentPointId?: string | null; targetPointId?: string | null; displayPointId?: string | null;
  motorState: string; playbackState: string; playbackRevision?: number; mediaSessionId?: string | null; mediaError?: string | null; carouselMode: boolean; carouselDirection: string; videoId: string | null; error: string | null;
};
type Labels = Record<string, string>;
type Presentation = { mode: 'demo' | 'compact' | 'visit'; demoRestPointId: string; demoContentPointId: string };
type DisplayConfig = {
  title: string; themeTitle: string; themeSubtitle: string; brandEnglish: string; coordinatePrimary: string; coordinateSecondary: string; pointPrefix: string; coordinateLabel: string; emblemPath: string;
  labels: Labels; showMascots: boolean; mascots: Record<string, string>; presentation: Presentation; points: Point[];
};

const fallbackPoints: Point[] = [
  { id: 'p01', order: 10, title: '高原启程', navLabel: '启程', subtitle: '从成都出发，走进青藏高原的科学现场', videoPath: '/content/videos/p01.mp4', posterPath: '/content/posters/p01.svg', backgroundPath: '/content/backgrounds/p01-plateau-base.png', mascotKey: 'main' },
  { id: 'p02', order: 20, title: '地质巡测', navLabel: '巡测', subtitle: '循着岩层与断裂带，解读高原的地质密码', videoPath: '/content/videos/p02.mp4', posterPath: '/content/posters/p02.svg', backgroundPath: '/content/backgrounds/p02-geology-route.png', mascotKey: 'moving' },
  { id: 'p03', order: 30, title: '冰川源区', navLabel: '冰川', subtitle: '追踪冰川变化，守护江河源头生态', videoPath: '/content/videos/p03.mp4', posterPath: '/content/posters/p03.svg', backgroundPath: '/content/backgrounds/p03-glacier-source.png', mascotKey: 'playing' },
  { id: 'p04', order: 40, title: '高原守望', navLabel: '守望', subtitle: '以科学之志，守望世界屋脊', videoPath: '/content/videos/p04.mp4', posterPath: '/content/posters/p04.svg', backgroundPath: '/content/backgrounds/p04-plateau-spirit.png', mascotKey: 'guide' }
];

const fallbackConfig: DisplayConfig = {
  title: '成都理工大学校史馆', themeTitle: '青藏高原科考', themeSubtitle: '青藏高原地质与生态科考专题展',
  brandEnglish: '', coordinatePrimary: '', coordinateSecondary: '', pointPrefix: '展项', coordinateLabel: '', emblemPath: '/content/branding/cdut-emblem.svg',
  points: fallbackPoints,
  presentation: { mode: 'visit', demoRestPointId: 'p04', demoContentPointId: 'p01' },
  showMascots: false,
  mascots: { main: '/content/mascots/mascot-main-original.png', moving: '/content/mascots/mascot-moving-original.png', playing: '/content/mascots/mascot-playing-original.png', guide: '/content/mascots/mascot-guide-original.png', error: '/content/mascots/mascot-guide-original.png' },
  labels: {
    play: '播放', pause: '暂停', stop: '停止', mute: '静音', unmute: '开启声音', volume: '音量',
    autoTour: '自动巡展', stopTour: '停止巡展', home: '回原点', playCurrent: '播放当前视频',
    emergencyStop: '紧急停机',
    swipeLocked: '滑轨移动中，请稍候', swipeBoundary: '已到达当前方向的最后展项', swipeSwitching: '正在切换到',
    adminEntry: '管理员入口', adminLoginTitle: '管理员验证', adminPassword: '请输入管理密码',
    adminLogin: '进入面板', adminCancel: '取消', adminPasswordError: '密码不正确，请重试',
    hardwarePing: '连接检测', hardwarePingSuccess: '控制器响应：', hardwarePingFailed: '控制器未响应：',
    mascotMainTitle: '地质科考伙伴', mascotGuideTitle: '科考导览伙伴', mascotMainText: '地质锤，敲开探索之门', mascotGuideText: '探索，从这里出发'
  }
};
const defaultStatus: Status = { currentScene: 'p01', targetScene: null, motorState: 'arrived', playbackState: 'idle', carouselMode: false, carouselDirection: 'forward', videoId: null, error: null };
const stateLabel: Record<string, string> = { idle: '待命', initializing: '控制器连接中', moving: '滑轨移动中', arrived: '已到位', loading: '内容装载中', showing: '图文展示中', ended: '视频已播完', playing: '正在播放', paused: '已暂停', stopped: '已停止', error: '需要关注' };
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
  const swipeStart = useRef<{ x: number; y: number } | null>(null);
  const volumeGesture = useRef<{ pointerId: number; startY: number; startVolume: number; dragged: boolean } | null>(null);
  const suppressVolumeClick = useRef(false);
  const volumeHintTimer = useRef<number | null>(null);
  const [requestError, setRequestError] = useState('');
  const [videoMuted, setVideoMuted] = useState(() => localStorage.getItem('rail-video-muted') !== 'false');
  const [volume, setVolume] = useState(() => {
    const saved = Number(localStorage.getItem('rail-video-volume') ?? '.6');
    return Number.isFinite(saved) && saved >= 0 && saved <= 1 ? saved : .6;
  });
  const [swipeMessage, setSwipeMessage] = useState('');
  const [presentationMessage, setPresentationMessage] = useState('');
  const [volumeHint, setVolumeHint] = useState<number | null>(null);
  const presentation = displayConfig.presentation ?? fallbackConfig.presentation;
  const displayPointId = [status.displayPointId]
    .find((id): id is string => Boolean(id && displayConfig.points.some((point) => point.id === id)));
  const reportedActiveId = [status.targetPointId, status.targetScene, status.currentPointId, status.currentScene]
    .find((id): id is string => Boolean(id && displayConfig.points.some((point) => point.id === id)));
  const activeId = presentation.mode === 'demo'
    ? displayPointId ?? presentation.demoContentPointId
    : displayPointId ?? reportedActiveId ?? displayConfig.points[0]?.id;
  const activePoint = useMemo(() => displayConfig.points.find((point) => point.id === activeId) ?? displayConfig.points[0], [activeId, displayConfig]);
  const canNavigatePoints = presentation.mode !== 'demo';
  const showStationNavigation = presentation.mode === 'visit';
  const showOverlayNavigation = presentation.mode === 'compact';
  const hasVideo = Boolean(activePoint?.videoPath) && activePoint?.contentType !== 'imageText' && activePoint?.videoAvailable !== false;
  const labels: Labels = { ...fallbackConfig.labels, avatarArea: '数字人展示区', mediaError: '此展项暂未配置可播放的视频', ...displayConfig.labels };
  const [mediaError, setMediaError] = useState(false);
  const [needsGesture, setNeedsGesture] = useState(false);
  const [videoShape, setVideoShape] = useState({ source: '', width: 0, height: 0 });
  const mediaEvents = useRef<Array<{ time: string; event: string; position: number }>>([]);
  const [mediaMetrics, setMediaMetrics] = useState<ReturnType<typeof readMediaMetrics> | null>(null);
  const [copyMessage, setCopyMessage] = useState('');
  const recordMediaEvent = useCallback((event: string) => {
    mediaEvents.current.push({ time: new Date().toISOString(), event, position: Number((videoRef.current?.currentTime ?? 0).toFixed(2)) });
    if (mediaEvents.current.length > 80) mediaEvents.current.shift();
  }, []);
  const playFailed = useCallback((error: unknown) => {
    if (error instanceof DOMException && error.name === 'AbortError') return;
    recordMediaEvent(`播放未成功：${error instanceof Error ? error.name : '未知错误'}`);
    setNeedsGesture(true);
  }, [recordMediaEvent]);

  const loadStatus = useCallback(async () => {
    try { setStatus(await (await fetch('/api/status')).json() as Status); } catch { /* 离线演示仍可查看界面 */ }
  }, []);
  const loadDisplayConfig = useCallback(async () => {
    try {
      const response = await fetch('/api/display-config');
      if (!response.ok) return;
      const config = await response.json() as DisplayConfig;
      setDisplayConfig({ ...fallbackConfig, ...config, presentation: { ...fallbackConfig.presentation, ...config.presentation }, points: config.points?.length ? config.points : fallbackPoints, labels: { ...fallbackConfig.labels, ...config.labels } });
    } catch { /* 离线演示仍保留本地默认界面 */ }
  }, []);
  const command = useCallback(async (path: string) => {
    setRequestError('');
    try {
      const response = await fetch(`/api/control/${path}`, { method: 'POST' });
      const result = await response.json() as { success?: boolean; detail?: string; message?: string; error?: string };
      if (!response.ok || result.success === false) setRequestError(result.detail ?? result.message ?? result.error ?? '操作未成功，请稍后重试');
      await loadStatus();
    } catch { setRequestError('服务暂时无法连接，请检查程序是否运行'); }
  }, [loadStatus]);
  const activate = useCallback((id: string) => command(`points/${encodeURIComponent(id)}/activate`), [command]);
  const reportPlayback = useCallback(async (body: { sessionId: string; revision: number; event: 'ended' | 'error' }) => {
    // Only retry identical feedback, never a motion/control action. The server
    // ignores duplicates and feedback belonging to an old media session.
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const response = await fetch('/api/media/events', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        if (response.ok) return;
        if (response.status < 500) break;
      } catch { /* 短暂断线后重发同一条播放反馈 */ }
      await new Promise((resolve) => window.setTimeout(resolve, 500));
    }
    recordMediaEvent('播放反馈未送达，巡展保留当前点位');
  }, [recordMediaEvent]);

  useEffect(() => {
    void loadStatus();
    void loadDisplayConfig();
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
    socket.onmessage = (event) => { const message = JSON.parse(event.data) as { type: string; data: Status }; if (message.type === 'status') setStatus(message.data); };
    return () => socket.close();
  }, [loadDisplayConfig, loadStatus]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if (event.ctrlKey && event.shiftKey && event.altKey && event.key.toLowerCase() === 'm') setAdmin((value) => !value); };
    addEventListener('keydown', handler);
    return () => removeEventListener('keydown', handler);
  }, []);

  useEffect(() => { setMediaError(false); setNeedsGesture(false); }, [activePoint?.videoPath, status.mediaSessionId]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !hasVideo) return;
    synchronizeMedia(video, { source: activePoint?.videoPath ?? '', state: status.playbackState, revision: status.playbackRevision ?? 0 }, recordMediaEvent, playFailed);
  }, [status.playbackState, status.playbackRevision, status.mediaSessionId, activePoint?.videoPath, hasVideo, recordMediaEvent, playFailed]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const events: Record<string, string> = { loadstart: '装载视频', loadedmetadata: '读取视频尺寸', playing: '开始输出画面', pause: '视频暂停', waiting: '等待视频数据', stalled: '读取暂时停滞', seeking: '跳转进度', seeked: '跳转完成', ended: '播放结束', error: '视频错误' };
    const record = (event: Event) => recordMediaEvent(events[event.type] ?? event.type);
    for (const name of Object.keys(events)) video.addEventListener(name, record);
    return () => { for (const name of Object.keys(events)) video.removeEventListener(name, record); };
  }, [recordMediaEvent, status.mediaSessionId]);

  useEffect(() => {
    if (!admin) return;
    const sample = () => { if (videoRef.current) setMediaMetrics(readMediaMetrics(videoRef.current)); };
    sample();
    const timer = window.setInterval(sample, 1500);
    return () => window.clearInterval(timer);
  }, [admin]);

  useEffect(() => {
    recordMediaEvent(`滑轨${stateLabel[status.motorState] ?? status.motorState}；已确认点位${status.currentPointId ?? status.currentScene ?? '无'}；目标${status.targetPointId ?? status.targetScene ?? '无'}`);
  }, [status.motorState, status.currentPointId, status.currentScene, status.targetPointId, status.targetScene, recordMediaEvent]);

  useEffect(() => {
    const video = videoRef.current;
    if (video) {
      video.muted = videoMuted;
      video.volume = volume;
    }
    localStorage.setItem('rail-video-muted', String(videoMuted));
    localStorage.setItem('rail-video-volume', String(volume));
  }, [videoMuted, volume, status.mediaSessionId]);

  if (!activePoint) return null;
  const videoVisible = hasVideo && ['playing', 'paused', 'ended'].includes(status.playbackState);
  const videoRatio = videoShape.source === activePoint.videoPath && videoShape.width > 0 ? videoShape.width / videoShape.height : 16 / 9;
  const stageStyle = { '--video-ratio': videoRatio, '--video-height': `${100 / videoRatio}cqw` } as CSSProperties;
  const pointNumber = String(displayConfig.points.findIndex((point) => point.id === activePoint.id) + 1).padStart(2, '0');
  const mascotKeys = ['main', 'moving', 'playing', 'guide'];
  const mascotKey = activePoint.mascotKey ?? mascotKeys[(Number(pointNumber) - 1) % mascotKeys.length];
  const loginAdmin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAdminLoginError('');
    const response = await fetch('/api/admin/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: adminPassword }) });
    if (!response.ok) { setAdminLoginError(labels.adminPasswordError); return; }
    await fetch('/api/admin/reload', { method: 'POST' });
    await loadDisplayConfig();
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
  const beginVolumeGesture = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!hasVideo) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    volumeGesture.current = { pointerId: event.pointerId, startY: event.clientY, startVolume: videoMuted ? 0 : volume, dragged: false };
    setVolumeHint(Math.round((videoMuted ? 0 : volume) * 100));
  };
  const moveVolumeGesture = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const gesture = volumeGesture.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const delta = gesture.startY - event.clientY;
    if (Math.abs(delta) > 3) gesture.dragged = true;
    const nextVolume = Math.max(0, Math.min(1, gesture.startVolume + delta / 180));
    setVideoVolume(nextVolume);
    setVolumeHint(Math.round(nextVolume * 100));
  };
  const finishVolumeGesture = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const gesture = volumeGesture.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (gesture.dragged) {
      suppressVolumeClick.current = true;
      window.setTimeout(() => { suppressVolumeClick.current = false; }, 80);
    }
    volumeGesture.current = null;
    if (volumeHintTimer.current !== null) window.clearTimeout(volumeHintTimer.current);
    volumeHintTimer.current = window.setTimeout(() => setVolumeHint(null), 700);
  };
  const clickVolumeIcon = () => {
    if (suppressVolumeClick.current) return;
    toggleMute();
  };
  const playVideo = () => {
    if (!hasVideo) return;
    // A touch gesture can unblock browser autoplay without waiting for a fetch.
    if (videoRef.current) void videoRef.current.play().catch(playFailed);
    void command('play');
  };
  const emergencyStop = () => {
    if (!window.confirm('将立即发送 STOP 软停命令，并停止自动巡展。该命令不会切断伺服使能；请确认现场安全后继续。')) return;
    void command('emergency-stop');
  };
  const savePresentation = async (mode: Presentation['mode'], moveToRestPoint = false) => {
    if (moveToRestPoint && !window.confirm('将停止自动巡展并移动到演示位置 p4。请确认滑轨路径安全。')) return;
    setPresentationMessage('');
    try {
      const response = await fetch('/api/admin/presentation', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, moveToRestPoint })
      });
      const result = await response.json() as { success?: boolean; message?: string; error?: string; moved?: boolean; restPointId?: string };
      if (!response.ok || result.success === false) {
        setPresentationMessage(result.message ?? result.error ?? '展示配置保存失败');
        return;
      }
      await Promise.all([loadDisplayConfig(), loadStatus()]);
      setPresentationMessage(result.moved ? `已切换为静态演示，并已前往 ${result.restPointId ?? 'p4'}` : '展示方式已保存');
    } catch {
      setPresentationMessage('展示配置保存失败，请检查服务连接');
    }
  };
  const copyDiagnostics = async () => {
    const report = { collectedAt: new Date().toISOString(), pageMode: embedMode ? '嵌入' : '独立', userAgent: navigator.userAgent, point: activePoint.id, video: activePoint.videoPath, status, media: videoRef.current ? readMediaMetrics(videoRef.current) : null, events: mediaEvents.current };
    try { await navigator.clipboard.writeText(JSON.stringify(report, null, 2)); setCopyMessage('播放诊断已复制'); }
    catch { setCopyMessage('复制未成功，请拍下本面板的诊断数据'); }
  };
  const goAdjacent = (offset: -1 | 1) => {
    if (!canNavigatePoints) return;
    if (status.motorState === 'moving' || status.targetPointId || status.targetScene) {
      setSwipeMessage(labels.swipeLocked);
      return;
    }
    const currentIndex = displayConfig.points.findIndex((point) => point.id === activePoint.id);
    const nextPoint = displayConfig.points[currentIndex + offset];
    if (!nextPoint) {
      setSwipeMessage(labels.swipeBoundary);
      return;
    }
    setSwipeMessage(`${labels.swipeSwitching} ${nextPoint.navLabel}`);
    void activate(nextPoint.id);
  };
  const beginSwipe = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (!canNavigatePoints) return;
    if ((event.target as HTMLElement).closest('button, input')) return;
    const touch = event.touches[0];
    if (touch) swipeStart.current = { x: touch.clientX, y: touch.clientY };
  };
  const finishSwipe = (event: ReactTouchEvent<HTMLDivElement>) => {
    if (!canNavigatePoints) return;
    const start = swipeStart.current;
    swipeStart.current = null;
    const touch = event.changedTouches[0];
    if (!start || !touch) return;
    const distanceX = touch.clientX - start.x;
    const distanceY = touch.clientY - start.y;
    const threshold = Math.max(56, window.innerWidth * .05);
    if (Math.abs(distanceX) < threshold || Math.abs(distanceX) < Math.abs(distanceY) * 1.3) return;
    goAdjacent(distanceX < 0 ? 1 : -1);
  };
  const activePointIndex = displayConfig.points.findIndex((point) => point.id === activePoint.id);
  const previousPoint = displayConfig.points[activePointIndex - 1];
  const nextPoint = displayConfig.points[activePointIndex + 1];

  return <main className={`exhibit-shell avatar-anchor-${avatarAnchor} ${embedMode ? 'embed-mode' : ''}`} style={{ backgroundImage: `url("${activePoint.backgroundPath}")` }}>
    <div className="terrain-lines" />
    <header className="masthead">
      <div className="brand"><img className="brand-emblem" src={displayConfig.emblemPath} alt="成都理工大学校徽" /><div><p>{displayConfig.title}</p><h1>{displayConfig.themeTitle}</h1></div></div>
      <div className="header-actions">{!embedMode && <button className="admin-entry" type="button" onClick={() => { setAdminLoginError(''); setAdminLoginOpen(true); }}>{labels.adminEntry}</button>}</div>
    </header>
    <section className="presentation">
      <aside className="scene-intro"><h2>{presentation.mode === 'visit' && <span className="point-number">{pointNumber}</span>}{activePoint.title}</h2><p>{activePoint.subtitle}</p></aside>
      <div className="media-stack">
      <div className="media-frame">
        <div className="frame-corner top-left" /><div className="frame-corner top-right" /><div className="frame-corner bottom-left" /><div className="frame-corner bottom-right" />
        <div className="video-stage" style={stageStyle} onTouchStart={beginSwipe} onTouchEnd={finishSwipe} onTouchCancel={() => { swipeStart.current = null; }}>
          {(!videoVisible || mediaError) && <img className="poster" src={activePoint.imagePath || activePoint.backgroundPath} alt="" />}
          {!hasVideo && activePoint.contentText && <p className="content-text">{activePoint.contentText}</p>}
          <video key={status.mediaSessionId ?? 'initial'} ref={videoRef} className={videoVisible && !mediaError ? 'visible' : ''} src={hasVideo ? activePoint.videoPath : undefined} muted={videoMuted} preload="auto" playsInline controls={false} disablePictureInPicture onLoadedMetadata={(event) => { const video = event.currentTarget; setVideoShape({ source: activePoint.videoPath, width: video.videoWidth, height: video.videoHeight }); }} onPlaying={() => setNeedsGesture(false)} onEnded={(event) => {
            setNeedsGesture(true);
            if (videoRef.current !== event.currentTarget || status.displayPointId !== activePoint.id) return;
            const feedback = makeEndedFeedback(event.currentTarget, { source: new URL(activePoint.videoPath, location.href).href, sessionId: status.mediaSessionId ?? '', revision: status.playbackRevision ?? 0, state: status.playbackState });
            if (feedback) void reportPlayback(feedback);
          }} onLoadedData={() => setMediaError(false)} onError={(event) => {
            if (!hasVideo) return;
            setMediaError(true);
            if (videoRef.current === event.currentTarget && event.currentTarget.error && status.displayPointId === activePoint.id && status.mediaSessionId && status.playbackState === 'playing') {
              void reportPlayback({ sessionId: status.mediaSessionId, revision: status.playbackRevision ?? 0, event: 'error' });
            }
          }} />
          {hasVideo && (!videoVisible || needsGesture) && !mediaError && <button className="poster-play" type="button" onClick={playVideo} aria-label={labels.playCurrent}><span>▶</span>{labels.playCurrent}</button>}
          {showOverlayNavigation && <div className="overlay-navigation" aria-label="切换展项"><button type="button" disabled={!previousPoint || Boolean(status.targetPointId ?? status.targetScene)} onClick={() => goAdjacent(-1)} aria-label={previousPoint ? `切换到${previousPoint.navLabel}` : '没有上一展项'}>›</button><button type="button" disabled={!nextPoint || Boolean(status.targetPointId ?? status.targetScene)} onClick={() => goAdjacent(1)} aria-label={nextPoint ? `切换到${nextPoint.navLabel}` : '没有下一展项'}>‹</button></div>}
        </div>
      </div>
      <div className="control-dock" aria-label="展项控制"><div className="playback-controls" role="group" aria-label="视频播放控制"><button disabled={!hasVideo} onClick={playVideo}>{labels.play}</button><button disabled={!hasVideo} onClick={() => void command('pause')}>{labels.pause}</button><button disabled={!hasVideo} onClick={() => void command('stop')}>{labels.stop}</button><button className={`volume-icon ${videoMuted || volume === 0 ? 'muted' : ''}`} disabled={!hasVideo} onPointerDown={beginVolumeGesture} onPointerMove={moveVolumeGesture} onPointerUp={finishVolumeGesture} onPointerCancel={finishVolumeGesture} onClick={clickVolumeIcon} aria-label={`${videoMuted ? labels.unmute : labels.mute}；按住上下滑动调节音量`}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4Z" />{!(videoMuted || volume === 0) && <><path className="sound-wave" d="M16 8.5a5 5 0 0 1 0 7" /><path className="sound-wave" d="M18.5 6a8.5 8.5 0 0 1 0 12" /></>}</svg>{volumeHint !== null && <span className="volume-hint">{volumeHint}%</span>}</button></div><div className="rail-controls" role="group" aria-label="滑轨控制"><button className={status.carouselMode ? 'selected' : ''} onClick={() => void command(`carousel/${status.carouselMode ? 'stop' : 'start'}`)}>{status.carouselMode ? labels.stopTour : labels.autoTour}</button><button onClick={() => void command('home')}>{labels.home}</button><button className="emergency-stop" onClick={emergencyStop}>{labels.emergencyStop}</button></div></div>
      </div>
    </section>
    <aside className="avatar-lane" aria-label={labels.avatarArea} data-avatar-anchor={avatarAnchor} />
    {!embedMode && displayConfig.showMascots === true && <div className="mascot-wrap" data-mode={mascotKey}><div className="mascot-callout"><span>{mascotKey === 'main' ? labels.mascotMainTitle : labels.mascotGuideTitle}</span><b>{mascotKey === 'main' ? labels.mascotMainText : labels.mascotGuideText}</b></div><img src={displayConfig.mascots[mascotKey] ?? displayConfig.mascots.main} alt="科考主题玩偶" /></div>}
    {showStationNavigation && <nav className="station-nav" aria-label="可配置点位">{displayConfig.points.map((point, index) => <button disabled={Boolean(status.targetPointId ?? status.targetScene) && point.id !== activeId} aria-current={point.id === activeId ? 'true' : undefined} className={point.id === activeId ? 'active' : ''} key={point.id} onClick={() => void activate(point.id)}><em>{String(index + 1).padStart(2, '0')}</em><span>{point.navLabel}</span></button>)}</nav>}
    {!embedMode && adminLoginOpen && <div className="admin-login-backdrop"><form className="admin-login" onSubmit={loginAdmin}><h2>{labels.adminLoginTitle}</h2><label>{labels.adminPassword}<input autoFocus type="password" value={adminPassword} onChange={(event) => setAdminPassword(event.target.value)} required /></label>{adminLoginError && <p role="alert">{adminLoginError}</p>}<div><button type="button" onClick={() => setAdminLoginOpen(false)}>{labels.adminCancel}</button><button type="submit">{labels.adminLogin}</button></div></form></div>}
    {!embedMode && admin && <section className="admin-panel"><button className="close" onClick={() => setAdmin(false)}>×</button><span>管理员调试面板</span><div className="admin-status">滑轨：{stateLabel[status.motorState] ?? status.motorState}　影片：{stateLabel[status.playbackState] ?? status.playbackState}　巡展：{status.carouselMode ? '自动巡展中' : '手动控制'}</div><div className="presentation-admin"><strong>展示方式</strong><button className={presentation.mode === 'demo' ? 'selected' : ''} onClick={() => void savePresentation('demo')}>明日静态演示</button><button className={presentation.mode === 'compact' ? 'selected' : ''} onClick={() => void savePresentation('compact')}>隐藏点位栏</button><button className={presentation.mode === 'visit' ? 'selected' : ''} onClick={() => void savePresentation('visit')}>正常参观</button>{presentation.mode === 'demo' && <button onClick={() => void savePresentation('demo', true)}>前往 p4 演示位置</button>}</div>{presentationMessage && <small className="presentation-message">{presentationMessage}</small>}<div>{displayConfig.points.map((point, index) => <button key={point.id} onClick={() => void activate(point.id)}>{index + 1} · {point.title}</button>)}</div><div><button disabled={!hasVideo} onClick={playVideo}>{labels.play}</button><button disabled={!hasVideo} onClick={() => void command('pause')}>{labels.pause}</button><button disabled={!hasVideo} onClick={() => void command('stop')}>{labels.stop}</button><button onClick={() => void command('home')}>{labels.home}</button><button className="emergency-stop" onClick={emergencyStop}>{labels.emergencyStop}</button></div><div><button onClick={() => void command('carousel/start')}>启动巡展</button><button onClick={() => void command('carousel/stop')}>停止巡展</button><button onClick={() => void hardwarePing()}>{labels.hardwarePing}</button></div>{hardwareMessage && <small className="hardware-message">{hardwareMessage}</small>}
      <div className="admin-diagnostics"><h3>播放诊断</h3>{mediaMetrics && <p>视频尺寸：{mediaMetrics.resolution}<br />进度：{mediaMetrics.currentTime} / {mediaMetrics.duration ?? '未知'} 秒　缓冲余量：{mediaMetrics.bufferedSeconds} 秒<br />丢帧：{mediaMetrics.droppedFrames ?? '不支持'} / {mediaMetrics.totalFrames ?? '不支持'}<br />实际暂停：{mediaMetrics.paused ? '是' : '否'}　播放结束：{mediaMetrics.ended ? '是' : '否'}</p>}<button onClick={() => void copyDiagnostics()}>复制播放诊断</button>{copyMessage && <p>{copyMessage}</p>}{status.error && <p>硬件：{status.error}</p>}{requestError && <p>操作：{requestError}</p>}{mediaError && <p>{labels.mediaError}</p>}{swipeMessage && <p>{swipeMessage}</p>}</div>
    </section>}
  </main>;
}

createRoot(document.getElementById('root')!).render(<App />);
