// Read-only media verification. Writes only the requested JSON report.
// Usage: node verify-remux.cjs [original.mp4] [remuxed.mp4] [report.json]
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const workspace = path.resolve(__dirname, '../..');
const savedOriginal = path.join(workspace, 'release/视频无损优化-20261102/原始视频备份.mp4');
const original = path.resolve(process.argv[2] || (fs.existsSync(savedOriginal) ? savedOriginal : path.join(workspace, 'content/videos/P04.mp4')));
const optimized = path.resolve(process.argv[3] || path.join(workspace, 'release/视频无损优化-20261102/p04-web.mp4'));
const destination = path.resolve(process.argv[4] || path.join(workspace, 'tmp/remux-integrity-report.json'));
const toleranceSeconds = 0.000002;
const report = {
  schema: 'rail.remux-integrity/v1', checkedAt: new Date().toISOString(),
  original, optimized, passed: false, timestampToleranceSeconds: toleranceSeconds,
  streams: [], sampleDistances: [], containers: [], errors: [],
};

function probe(file) {
  const fields = [
    'packet=stream_index,pts_time,dts_time,pos,size,data_hash',
    'stream=index,codec_type,codec_name,profile,codec_tag_string,width,height,pix_fmt,level,r_frame_rate,avg_frame_rate,sample_aspect_ratio,display_aspect_ratio,color_range,color_space,color_transfer,color_primaries,sample_rate,channels,channel_layout,time_base,extradata_hash',
    'format=duration,size',
  ].join(':');
  return JSON.parse(execFileSync('ffprobe', [
    '-v', 'error', '-show_packets', '-show_streams', '-show_format',
    '-show_data_hash', 'sha256', '-show_entries', fields, '-of', 'json', file,
  ], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, windowsHide: true }));
}

function boxes(file) {
  const descriptor = fs.openSync(file, 'r');
  try {
    const length = fs.fstatSync(descriptor).size;
    const entries = [];
    let offset = 0;
    while (offset < length) {
      if (offset + 8 > length) throw new Error('Incomplete MP4 box header: ' + file);
      const header = Buffer.alloc(16);
      fs.readSync(descriptor, header, 0, Math.min(16, length - offset), offset);
      let size = header.readUInt32BE(0);
      const headerLength = size === 1 ? 16 : 8;
      if (size === 1) {
        if (offset + 16 > length) throw new Error('Incomplete extended box header: ' + file);
        size = Number(header.readBigUInt64BE(8));
      } else if (size === 0) size = length - offset;
      if (!Number.isSafeInteger(size) || size < headerLength || offset + size > length)
        throw new Error('Invalid MP4 box length: ' + file);
      entries.push({ type: header.toString('ascii', 4, 8), offset, bytes: size });
      offset += size;
    }
    return entries;
  } finally { fs.closeSync(descriptor); }
}

function compareTime(a, b) {
  if (a === undefined || b === undefined) return { equal: false, difference: null };
  const difference = Math.abs(Number(a) - Number(b));
  return { equal: Number.isFinite(difference) && difference <= toleranceSeconds, difference };
}

try {
  if ([original, optimized].some(file => file.toLowerCase() === destination.toLowerCase()))
    throw new Error('Report destination must not overwrite either media input.');
  const inputs = [probe(original), probe(optimized)];
  if (!inputs[0].streams?.length || inputs[0].streams.length !== inputs[1].streams?.length)
    throw new Error('Stream counts differ or input has no streams.');
  const codecFields = ['codec_type', 'codec_name', 'profile', 'codec_tag_string', 'width', 'height',
    'pix_fmt', 'level', 'r_frame_rate', 'avg_frame_rate', 'sample_aspect_ratio', 'display_aspect_ratio',
    'color_range', 'color_space', 'color_transfer', 'color_primaries', 'sample_rate', 'channels',
    'channel_layout', 'extradata_hash'];
  for (const source of inputs[0].streams) {
    const target = inputs[1].streams.find(stream => stream.index === source.index);
    if (!target) throw new Error('Missing output stream: ' + source.index);
    const packets = inputs.map(input => input.packets.filter(packet => packet.stream_index === source.index));
    const result = {
      index: source.index, type: source.codec_type, packetCounts: packets.map(list => list.length),
      payloadHashMismatches: 0, packetSizeMismatches: 0,
      ptsMismatches: 0, dtsMismatches: 0, maxPtsDifferenceSeconds: 0, maxDtsDifferenceSeconds: 0,
      codecParameterDifferences: codecFields.filter(field => source[field] !== target[field]),
      timeBases: [source.time_base, target.time_base],
      codecParameters: Object.fromEntries(codecFields.filter(field => source[field] !== undefined).map(field => [field, source[field]])),
    };
    for (let index = 0; index < Math.max(packets[0].length, packets[1].length); index++) {
      const a = packets[0][index], b = packets[1][index];
      if (!a || !b) { result.payloadHashMismatches++; continue; }
      if (!a.data_hash || !b.data_hash || a.data_hash !== b.data_hash) result.payloadHashMismatches++;
      if (a.size !== b.size) result.packetSizeMismatches++;
      for (const type of ['pts', 'dts']) {
        const comparison = compareTime(a[type + '_time'], b[type + '_time']);
        if (!comparison.equal) result[type + 'Mismatches']++;
        if (comparison.difference !== null && Number.isFinite(comparison.difference)) {
          const key = 'max' + type[0].toUpperCase() + type.slice(1) + 'DifferenceSeconds';
          result[key] = Math.max(result[key], comparison.difference);
        }
      }
    }
    result.passed = packets[0].length > 0 && packets[0].length === packets[1].length
      && result.payloadHashMismatches === 0 && result.packetSizeMismatches === 0
      && result.ptsMismatches === 0 && result.dtsMismatches === 0
      && result.codecParameterDifferences.length === 0;
    report.streams.push(result);
  }
  for (let i = 0; i < inputs.length; i++) {
    const file = [original, optimized][i], input = inputs[i];
    const entries = boxes(file);
    const moov = entries.find(box => box.type === 'moov');
    const mdat = entries.find(box => box.type === 'mdat');
    report.containers.push({ file, bytes: Number(input.format.size), durationSeconds: Number(input.format.duration),
      boxes: entries, indexBeforeMedia: Boolean(moov && mdat && moov.offset < mdat.offset) });
    const streamIds = ['video', 'audio'].map(type => input.streams.find(stream => stream.codec_type === type)?.index);
    for (const seconds of [60, 120]) {
      const packets = streamIds.map(id => input.packets.find(packet => packet.stream_index === id && Number(packet.pts_time) >= seconds));
      const valid = packets.every(packet => packet && Number.isFinite(Number(packet.pos)));
      report.sampleDistances.push({ file, requestedSeconds: seconds, available: valid,
        positions: packets.map(packet => packet ? { stream: packet.stream_index, ptsSeconds: Number(packet.pts_time), offset: Number(packet.pos) } : null),
        distanceBytes: valid ? Math.abs(Number(packets[0].pos) - Number(packets[1].pos)) : null });
    }
  }
  report.passed = report.streams.every(stream => stream.passed) && report.containers[1].indexBeforeMedia;
  if (!report.passed) report.errors.push('Payload/timing/codec verification or fast-start index validation failed.');
} catch (error) {
  report.errors.push(error.message);
} finally {
  // Never use either media input as the report output, including on failure.
  if (![original, optimized].some(file => file.toLowerCase() === destination.toLowerCase())) {
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.writeFileSync(destination, JSON.stringify(report, null, 2) + '\n', 'utf8');
  }
  console.log(JSON.stringify({ passed: report.passed, report: destination, streams: report.streams.map(stream => ({
    index: stream.index, packetCounts: stream.packetCounts, payloadHashMismatches: stream.payloadHashMismatches,
    ptsMismatches: stream.ptsMismatches, dtsMismatches: stream.dtsMismatches, passed: stream.passed,
  })), errors: report.errors }, null, 2));
  if (!report.passed) process.exitCode = 1;
}
