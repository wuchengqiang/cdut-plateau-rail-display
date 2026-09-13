import assert from 'node:assert/strict';
import { makeEndedFeedback, synchronizeMedia, readMediaMetrics } from './src/media-controller.ts';

const events = [];
const failure = (error) => { throw error; };
let playCalls = 0;
let pauseCalls = 0;
const video = {
  paused: true, ended: false, currentTime: 24.5,
  play() { playCalls++; this.paused = false; this.ended = false; return Promise.resolve(); },
  pause() { pauseCalls++; this.paused = true; },
};
let command = { source: '/content/videos/p01.mp4', state: 'playing', revision: 3 };
synchronizeMedia(video, command, (event) => events.push(event), failure);
assert.equal(playCalls, 1);
// Repeated status, rail position and arrival carry the same media command.
synchronizeMedia(video, command, (event) => events.push(event), failure);
assert.equal(playCalls, 1);
assert.equal(pauseCalls, 0);
assert.equal(video.currentTime, 24.5);
command = { ...command, state: 'paused', revision: 4 };
synchronizeMedia(video, command, () => {}, failure);
synchronizeMedia(video, command, () => {}, failure);
assert.equal(pauseCalls, 1);
assert.equal(video.currentTime, 24.5);
command = { ...command, state: 'playing', revision: 5 };
synchronizeMedia(video, command, () => {}, failure);
assert.equal(playCalls, 2);
// A new explicit Play after native ended must work even if backend said playing.
video.ended = true; video.paused = true;
synchronizeMedia(video, { ...command, revision: 6 }, () => {}, failure);
assert.equal(playCalls, 3);
synchronizeMedia(video, { ...command, state: 'stopped', revision: 7 }, () => {}, failure);
assert.equal(video.currentTime, 0);
assert.equal(video.paused, true);
// A confirmed end must retain the last frame while waiting for physical arrival.
const beforeEnd = { playCalls, pauseCalls, position: video.currentTime };
synchronizeMedia(video, { ...command, state: 'ended', revision: 8 }, () => {}, failure);
assert.deepEqual({ playCalls, pauseCalls, position: video.currentTime }, beforeEnd);

const feedbackContext = { source: 'http://127.0.0.1/content/videos/p01.mp4', sessionId: 'a'.repeat(32), revision: 10, state: 'playing' };
const endedVideo = { currentSrc: feedbackContext.source, ended: true, duration: 141.31, currentTime: 141.31 };
assert.deepEqual(makeEndedFeedback(endedVideo, feedbackContext), { sessionId: feedbackContext.sessionId, revision: 10, event: 'ended' });
for (const override of [{ ended: false }, { duration: NaN }, { currentTime: 10 }, { currentSrc: 'old-video' }]) {
  assert.equal(makeEndedFeedback({ ...endedVideo, ...override }, feedbackContext), null);
}
for (const override of [{ sessionId: '' }, { state: 'paused' }, { state: 'stopped' }, { state: 'ended' }]) {
  assert.equal(makeEndedFeedback(endedVideo, { ...feedbackContext, ...override }), null);
}

const metrics = readMediaMetrics({ ...video, videoWidth: 2126, videoHeight: 3840, duration: 141.31,
  currentTime: 20, readyState: 4, error: null,
  buffered: { length: 1, start: () => 0, end: () => 35 },
  getVideoPlaybackQuality: () => ({ totalVideoFrames: 600, droppedVideoFrames: 8 }),
});
assert.equal(metrics.bufferedSeconds, 15);
assert.equal(metrics.droppedFrames, 8);
assert.equal(metrics.resolution, '2126 × 3840');
console.log('Passed: media continuity at arrival, pause without seek, explicit replay, frame/buffer metrics');
