(() => {
  'use strict';
  const options = window.__railReadOptions;
  const video = document.getElementById('video');
  const message = document.getElementById('message');
  const start = document.getElementById('start');
  if (!options || !['file', 'http'].includes(options.kind)) {
    message.textContent = '请使用随包的启动脚本打开测试。';
    return;
  }
  const source = new URL(options.source);
  if ((options.kind === 'file' && source.protocol !== 'file:') ||
      (options.kind === 'http' && (source.protocol !== 'http:' || source.hostname !== '127.0.0.1')) ||
      source.username || source.password || source.search || source.hash) {
    message.textContent = '视频地址校验未通过。';
    return;
  }
  document.getElementById('title').textContent = options.kind === 'file' ? '直接读取同一个视频文件' : '通过本机 Web 服务读取同一个视频';
  document.getElementById('name').textContent = options.name;
  const events = [];
  let truncatedEvents = 0;
  const round = v => Number.isFinite(v) ? Math.round(v * 1000) / 1000 : null;
  const ranges = value => Array.from({ length: value.length }, (_, i) => [round(value.start(i)), round(value.end(i))]);
  function snapshot() {
    const quality = video.getVideoPlaybackQuality?.();
    const box = video.getBoundingClientRect();
    let ahead = 0;
    for (let i = 0; i < video.buffered.length; i++) {
      if (video.buffered.start(i) <= video.currentTime && video.buffered.end(i) >= video.currentTime)
        ahead = video.buffered.end(i) - video.currentTime;
    }
    return {
      currentTime: round(video.currentTime), duration: round(video.duration),
      bufferedSeconds: round(ahead), bufferedRanges: ranges(video.buffered),
      paused: video.paused, ended: video.ended, seeking: video.seeking,
      readyState: video.readyState, networkState: video.networkState,
      width: video.videoWidth, height: video.videoHeight,
      renderedWidth: round(box.width), renderedHeight: round(box.height),
      totalFrames: quality?.totalVideoFrames ?? null, droppedFrames: quality?.droppedVideoFrames ?? null,
      muted: video.muted, volume: video.volume, playbackRate: video.playbackRate,
      loop: video.loop, errorCode: video.error?.code ?? null,
      actualSourceKind: video.currentSrc ? new URL(video.currentSrc).protocol.replace(':', '') : null,
    };
  }
  for (const type of ['loadstart', 'loadedmetadata', 'loadeddata', 'playing', 'waiting', 'stalled', 'pause', 'emptied', 'seeking', 'seeked', 'ended', 'error', 'volumechange']) {
    video.addEventListener(type, () => {
      if (events.length >= 2000) { events.shift(); truncatedEvents++; }
      events.push({ at: new Date().toISOString(), pageMs: round(performance.now()), event: type, video: snapshot() });
      if (type === 'playing') { start.hidden = true; message.textContent = ''; }
      if (type === 'ended') message.textContent = '视频已播完，请切回黑色窗口按 Enter 保存本轮。';
      if (type === 'error') message.textContent = '视频读取失败，仍请切回黑色窗口保存报告。';
    });
  }
  Object.defineProperty(window, '__railReadProbe', { value: Object.freeze({
    read() {
      return {
        kind: options.kind, mediaName: options.name, at: new Date().toISOString(), pageMs: round(performance.now()),
        visibility: document.visibilityState, focused: document.hasFocus(),
        viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
        userAgent: navigator.userAgent, video: snapshot(), events: events.splice(0), truncatedEvents,
      };
    },
  }) });
  async function play() {
    try { await video.play(); }
    catch (error) { start.hidden = false; message.textContent = error.name === 'NotAllowedError' ? '浏览器要求点击一次开始播放。' : '无法自动播放，请点击重试并保留报告。'; }
  }
  start.addEventListener('click', play);
  video.loop = false;
  video.muted = false;
  video.volume = 0.5;
  video.src = source.href;
  void play();
})();
