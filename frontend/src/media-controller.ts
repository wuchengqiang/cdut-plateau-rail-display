export type MediaCommand = { source: string; state: string; revision: number };
export type MediaTarget = Pick<HTMLVideoElement, 'paused' | 'ended' | 'currentTime' | 'play' | 'pause'>;

export function makeEndedFeedback(video: Pick<HTMLVideoElement, 'ended' | 'duration' | 'currentTime' | 'currentSrc'>, context: { source: string; sessionId: string; revision: number; state: string }) {
  if (!context.sessionId || context.state !== 'playing' || video.currentSrc !== context.source || !video.ended
    || !Number.isFinite(video.duration) || video.duration <= 0 || video.currentTime < video.duration - .25) return null;
  return { sessionId: context.sessionId, revision: context.revision, event: 'ended' as const };
}

// Only explicit media commands or a source change control the element. Rail updates
// never seek, pause, reload, or replay it. Retrying play also works after native end.
export function synchronizeMedia(video: MediaTarget, command: MediaCommand, record: (event: string) => void, failed: (error: unknown) => void): void {
  if (command.state === 'playing' && (video.paused || video.ended)) {
    record('请求播放');
    void video.play().catch(failed);
  } else if (command.state === 'paused' || command.state === 'loading') {
    if (!video.paused) { record('请求暂停'); video.pause(); }
  } else if (command.state === 'stopped') {
    if (!video.paused) video.pause();
    if (video.currentTime !== 0) { record('停止归零'); video.currentTime = 0; }
  }
}

export function readMediaMetrics(video: HTMLVideoElement) {
  const quality = video.getVideoPlaybackQuality?.();
  let bufferedSeconds = 0;
  for (let i = 0; i < video.buffered.length; i++) {
    if (video.buffered.start(i) <= video.currentTime && video.buffered.end(i) >= video.currentTime) {
      bufferedSeconds = video.buffered.end(i) - video.currentTime;
      break;
    }
  }
  return {
    resolution: `${video.videoWidth} × ${video.videoHeight}`,
    currentTime: Number(video.currentTime.toFixed(2)),
    duration: Number.isFinite(video.duration) ? Number(video.duration.toFixed(2)) : null,
    paused: video.paused, ended: video.ended, readyState: video.readyState,
    bufferedSeconds: Number(bufferedSeconds.toFixed(2)),
    totalFrames: quality?.totalVideoFrames ?? null, droppedFrames: quality?.droppedVideoFrames ?? null,
    errorCode: video.error?.code ?? null,
  };
}
