// Passive, bounded telemetry. Never controls media, retries playback or moves rail.
export const MEDIA_DIAGNOSTICS_BUILD = 'recovery-diagnostics-20261102';
type EventName = 'media_error' | 'play_rejected' | 'stalled' | 'recovered' | 'retry_requested';
export type DiagnosticContext = { sessionId: string | null; revision: number; pointId: string; pageMode: 'embedded' | 'standalone'; playing: boolean };
type ExceptionName = 'NotAllowedError' | 'NotSupportedError' | 'NetworkError' | 'InvalidStateError' | 'UnknownError';
export type DiagnosticPayload = Record<string, unknown>;

const pageId = typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, char => {
  const n = crypto.getRandomValues(new Uint8Array(1))[0] & 15;
  return (char === 'x' ? n : (n & 3) | 8).toString(16);
});
const match = navigator.userAgent.match(/(Edg|Chrome|Firefox|Version)\/(\d+(?:\.\d+){0,3})/g);
const browser = match?.find(value => value.startsWith('Edg/')) ?? match?.find(value => !value.startsWith('Version/')) ?? match?.[0];
const [family, version] = browser?.split('/') ?? [];
const browserFamily = ({Edg:'Edge',Chrome:'Chrome'} as Record<string,string>)[family] ?? 'Other';
let inFlight = 0;
const sent = new Map<string, number>();
const round = (value: number) => Number.isFinite(value) && value >= 0 ? Math.round(value * 1000) / 1000 : null;

export function mediaDiagnosticSnapshot(video: HTMLVideoElement, context: DiagnosticContext, event: EventName, exceptionName?: ExceptionName): DiagnosticPayload {
  const quality = video.getVideoPlaybackQuality?.();
  let buffer = 0;
  for (let i = 0; i < video.buffered.length; i++) if (video.buffered.start(i) <= video.currentTime && video.buffered.end(i) >= video.currentTime)
    buffer = video.buffered.end(i) - video.currentTime;
  return {
    event, pageId, sessionId: context.sessionId, revision: context.revision, pointId: context.pointId,
    pageMode: context.pageMode, frontendBuild: MEDIA_DIAGNOSTICS_BUILD, browserFamily, browserVersion: version ?? null,
    currentTime: round(video.currentTime), duration: round(video.duration), bufferedSeconds: round(buffer),
    totalFrames: quality?.totalVideoFrames ?? null, droppedFrames: quality?.droppedVideoFrames ?? null,
    readyState: video.readyState, networkState: video.networkState, errorCode: video.error?.code ?? null,
    paused: video.paused, ended: video.ended, seeking: video.seeking, muted: video.muted, volume: round(video.volume),
    visibility: document.visibilityState === 'visible' ? 'visible' : 'hidden', ...(exceptionName ? {exceptionName} : {}),
  };
}

export function sendMediaDiagnostic(video: HTMLVideoElement, context: DiagnosticContext, event: EventName, exception?: unknown): void {
  try {
    const key = `${context.sessionId}:${context.pointId}:${event}`;
    const now = performance.now();
    if (inFlight >= 2 || now - (sent.get(key) ?? -Infinity) < 10000) return;
    if (sent.size >= 128) sent.delete(sent.keys().next().value!);
    sent.set(key, now);
    const name = exception instanceof Error ? exception.name : '';
    const safeName = ['NotAllowedError','NotSupportedError','NetworkError','InvalidStateError'].includes(name) ? name as ExceptionName : 'UnknownError';
    const body = JSON.stringify(mediaDiagnosticSnapshot(video, context, event, exception === undefined ? undefined : safeName));
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 3000);
    inFlight++;
    void fetch('/api/media/diagnostics', {method:'POST', headers:{'Content-Type':'application/json'},body,signal:controller.signal})
      .catch(() => { /* Telemetry failure must never block playback. */ })
      .finally(() => {inFlight--;clearTimeout(timeout);});
  } catch { /* Do not expose native messages, URLs, tokens, or errors to the UI. */ }
}

export function observeMediaDiagnostics(video: HTMLVideoElement, context: () => DiagnosticContext | null): () => void {
  let position = video.currentTime, lastProgress = performance.now(), stalled = false;
  const report = (event: EventName) => { const current = context(); if (current) sendMediaDiagnostic(video, current, event); };
  const error = () => { if (video.error) report('media_error'); };
  video.addEventListener('error', error);
  const timer = window.setInterval(() => {
    const current = context(), now = performance.now();
    if (!current || !current.playing || video.paused || video.ended || video.seeking || document.visibilityState !== 'visible') {
      position = video.currentTime; lastProgress = now; stalled = false; return;
    }
    if (Math.abs(video.currentTime - position) > .05) {
      if (stalled) report('recovered');
      position = video.currentTime; lastProgress = now; stalled = false;
    } else if (!stalled && !video.error && now - lastProgress >= 10000) {
      report('stalled'); stalled = true;
    }
  }, 2000);
  // An element may have already failed before its React effect attached.
  if (video.error) error();
  return () => { clearInterval(timer); video.removeEventListener('error', error); };
}
