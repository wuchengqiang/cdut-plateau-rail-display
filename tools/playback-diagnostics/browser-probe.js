(() => {
  if (window.__railDiagnosticProbe) return;
  const ids = new WeakMap();
  const events = [];
  const removed = new WeakSet();
  const detached = [];
  const releaseDetached = window.__railDiagnosticOptions?.releaseDetached === true;
  let releasedCount = 0;
  let serial = 0;
  let truncatedEvents = 0;
  const round = value => Number.isFinite(value) ? Math.round(value * 1000) / 1000 : null;
  const identity = video => {
    if (!ids.has(video)) ids.set(video, ++serial);
    return ids.get(video);
  };
  function snapshot(video) {
    const quality = video.getVideoPlaybackQuality?.();
    let buffer = 0;
    for (let i = 0; i < video.buffered.length; i++) {
      if (video.buffered.start(i) <= video.currentTime && video.buffered.end(i) >= video.currentTime)
        buffer = video.buffered.end(i) - video.currentTime;
    }
    let sourcePath = '';
    try { sourcePath = new URL(video.currentSrc || video.src, location.href).pathname; } catch {}
    return {
      elementId: identity(video), sourcePath, connected: video.isConnected,
      currentTime: round(video.currentTime), duration: round(video.duration),
      paused: video.paused, ended: video.ended, seeking: video.seeking,
      readyState: video.readyState, networkState: video.networkState,
      bufferedSeconds: round(buffer), width: video.videoWidth, height: video.videoHeight,
      totalFrames: quality?.totalVideoFrames ?? null, droppedFrames: quality?.droppedVideoFrames ?? null,
      muted: video.muted, volume: round(video.volume), playbackRate: video.playbackRate,
      errorCode: video.error?.code ?? null,
    };
  }
  function record(event) {
    if (!(event.target instanceof HTMLVideoElement)) return;
    if (events.length >= 2000) { events.shift(); truncatedEvents++; }
    events.push({ at: new Date().toISOString(), pageMs: round(performance.now()), event: event.type, video: snapshot(event.target) });
  }
  for (const type of ['loadstart', 'loadedmetadata', 'loadeddata', 'playing', 'waiting', 'stalled', 'pause', 'emptied', 'seeking', 'seeked', 'ended', 'error'])
    document.addEventListener(type, record, true);

  function onRemoval(video) {
    // A node moved/reinserted in the same DOM transaction is NOT an old player.
    if (video.isConnected || removed.has(video)) return;
    let source;
    try { source = new URL(video.currentSrc || video.src, location.href); } catch { return; }
    if (source.origin !== location.origin || !source.pathname.startsWith('/content/videos/')) return;
    removed.add(video);
    const before = snapshot(video);
    if (typeof WeakRef === 'function' && detached.length < 200) detached.push({ id: before.elementId, ref: new WeakRef(video) });
    const entry = { at: new Date().toISOString(), pageMs: round(performance.now()), event: 'detached-video', video: before, action: 'observe-only' };
    if (releaseDetached && !video.isConnected) {
      try {
        video.pause();
        video.removeAttribute('src');
        for (const sourceNode of video.querySelectorAll('source')) sourceNode.removeAttribute('src');
        video.load();
        releasedCount++;
        entry.action = 'pause-remove-src-load';
        entry.after = snapshot(video);
      } catch (error) { entry.action = 'release-failed'; entry.error = error.name; }
    }
    if (events.length >= 2000) { events.shift(); truncatedEvents++; }
    events.push(entry);
  }
  const observer = new MutationObserver(records => {
    for (const record of records) for (const node of record.removedNodes) {
      if (node instanceof HTMLVideoElement) onRemoval(node);
      if (node instanceof Element) for (const video of node.querySelectorAll('video')) onRemoval(video);
    }
  });
  observer.observe(document, { childList: true, subtree: true });

  // A only observes; B releases only detached local file videos. Neither mode
  // sends HTTP commands, changes the active video, or holds strong old-node refs.
  Object.defineProperty(window, '__railDiagnosticProbe', { value: Object.freeze({
    read() {
      return {
        at: new Date().toISOString(), pageMs: round(performance.now()),
        visibility: document.visibilityState, focused: document.hasFocus(),
        viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
        screen: { width: screen.width, height: screen.height }, userAgent: navigator.userAgent,
        videos: [...document.querySelectorAll('video')].map(snapshot),
        variant: releaseDetached ? 'release' : 'original', releasedCount,
        detachedVideos: detached.map(item => {
          const video = item.ref.deref();
          return video ? snapshot(video) : { elementId: item.id, collected: true };
        }),
        events: events.splice(0), truncatedEvents,
      };
    },
  }) });
})();
