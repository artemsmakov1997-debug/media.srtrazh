'use strict';
const assert = require('node:assert/strict');
const core = require('../photo-context-core.js');

function image(width, height, changed = false) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const p = (y * width + x) * 4;
    data[p] = 110 + 65 * Math.sin(x * .13) + 45 * Math.cos(y * .19);
    data[p + 1] = 120 + 75 * Math.cos(x * .09 + y * .12);
    data[p + 2] = 115 + 80 * Math.sin(y * .14 - x * .1);
    if (x > 48 && x < 105 && y > 30 && y < 79) { data[p] = 210; data[p + 1] = 65 + y; data[p + 2] = 35 + x; }
    if (changed) { data[p] = 255 - data[p]; data[p + 1] = 255 - data[p + 1]; data[p + 2] = 255 - data[p + 2]; }
    data[p + 3] = 255;
  }
  return {width, height, data};
}
function crop(source, x, y, width, height) {
  const target = {width, height, data: new Uint8ClampedArray(width * height * 4)};
  for (let row = 0; row < height; row++) target.data.set(source.data.subarray(((y + row) * source.width + x) * 4, ((y + row) * source.width + x + width) * 4), row * width * 4);
  return target;
}
const full = image(160, 120), clipped = crop(full, 32, 24, 96, 72);
assert.equal(core.compareImages(full, full, true).kind, 'same_file');
assert.equal(core.compareImages(full, image(160, 120)).kind, 'visual_copy');
const match = core.compareImages(clipped, full);
assert.equal(match.kind, 'crop_candidate', JSON.stringify(match));
assert.equal(match.status, 'needs_review');
assert.ok(Math.abs(match.region.x - .2) < .025, JSON.stringify(match));
assert.ok(Math.abs(match.region.y - .2) < .025, JSON.stringify(match));
assert.ok(Math.abs(match.retained_area - .36) < .03, JSON.stringify(match));
for (const box of [[17, 11, 89, 67], [41, 23, 80, 64], [3, 5, 151, 109], [70, 50, 60, 45]]) {
  const found = core.compareImages(crop(full, ...box), full);
  assert.equal(found.kind, 'crop_candidate', JSON.stringify({box, found}));
  assert.ok(Math.abs(found.region.x * full.width - box[0]) < 3);
  assert.ok(Math.abs(found.region.y * full.height - box[1]) < 3);
}
assert.equal(core.compareImages(full, image(160, 120, true)).kind, 'not_matched');
const flat = value => ({width: 32, height: 24, data: Uint8ClampedArray.from({length: 32 * 24 * 4}, (_, i) => i % 4 === 3 ? 255 : value)});
assert.equal(core.compareImages(flat(80), flat(180)).kind, 'inconclusive');

const text = '⚡ Фото, которое никогда не опубликуют официальные российские каналы. Потому что оно реальное, а не пропущенное через 200 фильтров.';
const cues = core.captionCues(text);
assert.equal(cues.length, 3, JSON.stringify(cues));
for (const finding of cues) for (const part of finding.evidence) assert.equal(Array.from(text).slice(part.start, part.end).join(''), part.quote);
assert.ok(cues.every(item => item.status === 'needs_review' && !('rating_weight' in item)));
assert.deepEqual(core.captionCues('Фото участников конференции. На снимке человек с наушником. Снимок предоставлен организаторами.'), []);
assert.deepEqual(core.captionCues('Никогда не опубликуют снимок без согласия героя.'), []);
assert.equal(core.captionCues('Это истинное лицо политика.')[0].rule_id, 'photo.caption_true_face');
assert.equal(core.captionCues('Снимок сделан без фильтров.')[0].status, 'needs_review');
assert.deepEqual(core.captureDateNote('2026:11:20 18:00:00', '2026-11-28'), {captured_date: '2026-11-20', publication_date: '2026-11-28', difference_days: 8});
assert.equal(core.captureDateNote('2026:02:31 12:00:00', '2026-11-28'), null);
assert.equal(core.captureDateNote(null, '2026-11-28'), null);

function png(width, height) {
  const bytes = new Uint8Array(33), view = new DataView(bytes.buffer);
  bytes.set([137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82]);
  view.setUint32(16, width); view.setUint32(20, height); return bytes;
}
assert.equal(core.headerInfo(png(516, 519).buffer).width, 516);
assert.throws(() => core.headerInfo(png(12000, 12000).buffer), /24 мегапиксел/);
assert.throws(() => core.headerInfo(new TextEncoder().encode('<svg onload="alert(1)"></svg>').buffer), /JPEG, PNG и WebP/);
assert.throws(() => core.headerInfo(new ArrayBuffer(core.MAX_BYTES + 1)), /12 МБ/);
const animated = new Uint8Array(45); animated.set(png(10, 10)); animated.set([0,0,0,0,97,99,84,76], 33);
assert.throws(() => core.headerInfo(animated.buffer), /анимированные/);
const webp = new Uint8Array(30);
webp.set(new TextEncoder().encode('RIFF'), 0); webp.set(new TextEncoder().encode('WEBPVP8X'), 8);
webp[24] = 159; webp[27] = 119;
assert.equal(core.headerInfo(webp.buffer).format, 'WebP');
assert.equal(core.headerInfo(webp.buffer).width, 160);
assert.equal(core.headerInfo(webp.buffer).height, 120);
webp[20] = 2; assert.throws(() => core.headerInfo(webp.buffer), /анимированные/);

// EXIF date/rotation are read as untrusted metadata; no GPS data is extracted.
const jpeg = new Uint8Array(100), j = new DataView(jpeg.buffer);
jpeg.set([255,216,255,225,0,76,69,120,105,102,0,0,73,73,42,0,8,0,0,0]);
j.setUint16(20, 2, true); // IFD entries
j.setUint16(22, 0x0112, true); j.setUint16(24, 3, true); j.setUint32(26, 1, true); j.setUint16(30, 6, true);
j.setUint16(34, 0x8769, true); j.setUint16(36, 4, true); j.setUint32(38, 1, true); j.setUint32(42, 34, true);
j.setUint16(46, 1, true); j.setUint16(48, 0x9003, true); j.setUint16(50, 2, true); j.setUint32(52, 20, true); j.setUint32(56, 48, true);
jpeg.set(new TextEncoder().encode('2026:11:20 18:00:00\0'), 60);
jpeg.set([255,192,0,11,8,0,120,0,160,1,1,17,0,255,217], 80);
const meta = core.headerInfo(jpeg.buffer);
assert.equal(meta.orientation, 6); assert.equal(meta.captured_at, '2026:11:20 18:00:00');
assert.equal(meta.width, 160); assert.equal(meta.height, 120); assert.ok(!('gps' in meta));
j.setUint32(56, 0xffffff, true); assert.equal(core.headerInfo(jpeg.buffer).captured_at, null);
console.log('Photo core: real crops, visual copies, unrelated/flat images, exact Unicode evidence, cautious caption cues, dates and bounded JPEG/PNG/WebP metadata passed');
