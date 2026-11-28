/* Evidence-only photo helpers, shared by the local worker and regression checks. */
((root) => {
  'use strict';
  const MAX_BYTES = 12 * 1024 * 1024, MAX_PIXELS = 24000000;
  const ascii = (bytes, start, length) => String.fromCharCode(...bytes.subarray(start, start + length));
  function headerInfo(buffer) {
    const bytes = new Uint8Array(buffer), view = new DataView(buffer);
    const info = {format: '', width: 0, height: 0, orientation: 1, captured_at: null, software: null};
    if (!bytes.length || bytes.length > MAX_BYTES) throw Error('Выберите фото размером до 12 МБ.');
    function exif(start, end) {
      try {
        const little = ascii(bytes, start, 2) === 'II';
        if (!little && ascii(bytes, start, 2) !== 'MM') return;
        const u16 = pos => { if (pos < start || pos + 2 > end) throw Error(); return view.getUint16(pos, little); };
        const u32 = pos => { if (pos < start || pos + 4 > end) throw Error(); return view.getUint32(pos, little); };
        if (u16(start + 2) !== 42) return;
        function ifd(offset, nested = false) {
          const position = start + offset, count = Math.min(u16(position), 200);
          for (let index = 0; index < count; index++) {
            const entry = position + 2 + index * 12, tag = u16(entry), type = u16(entry + 2), length = u32(entry + 4);
            if (!nested && tag === 0x8769 && type === 4 && length === 1) ifd(u32(entry + 8), true);
            if (tag === 0x0112 && type === 3 && length === 1) {
              const value = u16(entry + 8); if (value >= 1 && value <= 8) info.orientation = value;
            }
            if (type !== 2 || length < 2 || length > 256) continue;
            const valueAt = length <= 4 ? entry + 8 : start + u32(entry + 8);
            if (valueAt < start || valueAt + length > end) continue;
            const value = ascii(bytes, valueAt, length).replace(/\0.*$/s, '').replace(/[\x00-\x1f]/g, '').slice(0, 128);
            if (tag === 0x9003 && /^\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}$/.test(value)) info.captured_at = value;
            if (tag === 0x0131) info.software = value;
          }
        }
        ifd(u32(start + 4));
      } catch { /* Invalid optional metadata must not become a claim about the image. */ }
    }
    if (bytes.length >= 33 && ascii(bytes, 1, 3) === 'PNG' && bytes[0] === 137 &&
        bytes[4] === 13 && bytes[5] === 10 && bytes[6] === 26 && bytes[7] === 10 && ascii(bytes, 12, 4) === 'IHDR') {
      info.format = 'PNG'; info.width = view.getUint32(16); info.height = view.getUint32(20);
      for (let offset = 8; offset + 12 <= bytes.length;) {
        const length = view.getUint32(offset), tag = ascii(bytes, offset + 4, 4);
        if (tag === 'acTL') throw Error('Выберите статичное фото: анимированные изображения пока не поддерживаются.');
        if (length > bytes.length - offset - 12) break;
        if (tag === 'eXIf') exif(offset + 8, offset + 8 + length);
        offset += length + 12;
      }
    } else if (bytes.length > 4 && bytes[0] === 255 && bytes[1] === 216) {
      info.format = 'JPEG';
      for (let offset = 2; offset + 4 <= bytes.length;) {
        if (bytes[offset] !== 255) break;
        while (bytes[offset] === 255) offset++;
        const tag = bytes[offset++];
        if (tag === 0xda || tag === 0xd9) break;
        if (tag === 1 || tag >= 0xd0 && tag <= 0xd7) continue;
        if (offset + 2 > bytes.length) break;
        const length = view.getUint16(offset);
        if (length < 2 || offset + length > bytes.length) break;
        if ([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf].includes(tag) && length >= 8) {
          info.height = view.getUint16(offset + 3); info.width = view.getUint16(offset + 5);
        }
        if (tag === 0xe1 && ascii(bytes, offset + 2, 6) === 'Exif\0\0') exif(offset + 8, offset + length);
        offset += length;
      }
    } else if (bytes.length >= 30 && ascii(bytes, 0, 4) === 'RIFF' && ascii(bytes, 8, 4) === 'WEBP') {
      info.format = 'WebP';
      const tag = ascii(bytes, 12, 4);
      if (tag === 'VP8X') {
        if (bytes[20] & 2) throw Error('Выберите статичное фото: анимированные изображения пока не поддерживаются.');
        const uint24 = offset => bytes[offset] + (bytes[offset + 1] << 8) + (bytes[offset + 2] << 16);
        info.width = uint24(24) + 1; info.height = uint24(27) + 1;
      } else if (tag === 'VP8 ' && ascii(bytes, 23, 3) === '\x9d\x01\x2a') {
        info.width = view.getUint16(26, true) & 0x3fff; info.height = view.getUint16(28, true) & 0x3fff;
      } else if (tag === 'VP8L' && bytes[20] === 0x2f) {
        const bits = view.getUint32(21, true); info.width = (bits & 0x3fff) + 1; info.height = ((bits >>> 14) & 0x3fff) + 1;
      }
    }
    if (!info.format || !info.width || !info.height) throw Error('Не удалось прочитать фото. Поддерживаются JPEG, PNG и WebP.');
    if (info.width > 12000 || info.height > 12000 || info.width * info.height > MAX_PIXELS) {
      throw Error('Слишком большое разрешение. Уменьшите фото до 24 мегапикселей и 12 000 пикселей по стороне.');
    }
    return info;
  }

  const cueRules = [
    ['photo.caption_publication_claim', 'Утверждение о выборе фотографий',
      /(?:никогда|ни\s+за\s+что)[^.!?\n]{0,90}(?:не\s+(?:опубликуют|покажут|разместят)|не\s+увидите)[^.!?\n]{0,70}(?:канал[а-яё]*|сми|официальн[а-яё]*|телевидени[а-яё]*)/giu,
      'Подпись утверждает, какие снимки другие редакции показывают или скрывают. Нужна проверка их публикаций; одно фото не подтверждает это утверждение.'],
    ['photo.caption_authenticity_claim', 'Заявление о подлинности или обработке',
      /(?:фото|фотография|снимок)[^.!?\n]{0,35}(?:реальн[а-яё]*|настоящ[а-яё]*|без\s+(?:фильтров|ретуши|обработки))|без\s+(?:фильтров|ретуши|фотошопа)|(?:оно|она)\s+(?:реальн[а-яё]*|настоящ[а-яё]*)\s*,?\s*а\s+не/giu,
      'Это заявление о происхождении или обработке изображения. Для проверки нужны исходный файл и источник; подпись сама по себе не подтверждает подлинность.'],
    ['photo.caption_filter_quantity', 'Утверждение о масштабе обработки',
      /(?:\d{2,5}|сотн[а-яё]*|десятк[а-яё]*)\s+(?:разных\s+)?(?:фильтр[а-яё]*|сло[йяе][а-яё]*\s+фотошопа)/giu,
      'Количество фильтров может быть преувеличением. Без истории обработки это число нельзя проверить по внешнему виду фотографии.'],
    ['photo.caption_true_face', 'Перенос оценки внешности на человека',
      /(?:вот\s+(?:оно\s+)?|это\s+)(?:настоящее|истинное)\s+лицо[^.!?\n]{0,60}/giu,
      'Фраза предлагает судить о человеке по выбранному изображению. Проверьте, что именно доказывает кадр и доступны ли другие снимки события.']
  ];
  function captionCues(text) {
    const findings = [];
    for (const [rule_id, label, pattern, explanation] of cueRules) {
      pattern.lastIndex = 0;
      for (const match of text.matchAll(pattern)) {
        const start = Array.from(text.slice(0, match.index)).length;
        findings.push({rule_id, label, status: 'needs_review', explanation,
          evidence: [{field: 'text', start, end: start + Array.from(match[0]).length, quote: match[0]}]});
      }
    }
    return findings;
  }

  const sample = (image, x, y, channel) => {
    x = Math.max(0, Math.min(image.width - 1, x)); y = Math.max(0, Math.min(image.height - 1, y));
    const left = Math.floor(x), top = Math.floor(y), dx = x - left, dy = y - top;
    const at = (px, py) => image.data[(py * image.width + px) * 4 + channel];
    return at(left, top) * (1 - dx) * (1 - dy) + at(Math.min(left + 1, image.width - 1), top) * dx * (1 - dy) +
      at(left, Math.min(top + 1, image.height - 1)) * (1 - dx) * dy +
      at(Math.min(left + 1, image.width - 1), Math.min(top + 1, image.height - 1)) * dx * dy;
  };
  function descriptor(image, region = {x: 0, y: 0, width: image.width, height: image.height}, size = 16) {
    const rgb = [], grey = [];
    for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
      const px = region.x + (x + .5) * region.width / size - .5, py = region.y + (y + .5) * region.height / size - .5;
      const r = sample(image, px, py, 0), g = sample(image, px, py, 1), b = sample(image, px, py, 2);
      rgb.push(r, g, b); grey.push(.2126 * r + .7152 * g + .0722 * b);
    }
    const mean = grey.reduce((sum, value) => sum + value, 0) / grey.length;
    const deviation = Math.sqrt(grey.reduce((sum, value) => sum + (value - mean) ** 2, 0) / grey.length);
    return {rgb, grey, mean, deviation};
  }
  function distance(a, b) {
    let cross = 0, error = 0;
    for (let i = 0; i < a.grey.length; i++) cross += (a.grey[i] - a.mean) * (b.grey[i] - b.mean);
    for (let i = 0; i < a.rgb.length; i++) error += Math.abs(a.rgb[i] - b.rgb[i]);
    return {correlation: a.deviation * b.deviation > 1 ? cross / (a.grey.length * a.deviation * b.deviation) : 0,
      error: error / (a.rgb.length * 255)};
  }
  function compareImages(publication, reference, sameFile = false) {
    if (sameFile) return {kind: 'same_file', status: 'observation'};
    const a = descriptor(publication, undefined, 24), b = descriptor(reference, undefined, 24);
    const aspectDifference = Math.abs((publication.width / publication.height) / (reference.width / reference.height) - 1);
    const whole = distance(a, b);
    if (aspectDifference < .015 && whole.error < .018 && (whole.correlation > .985 || whole.error < .001)) {
      return {kind: 'visual_copy', status: 'needs_review', metrics: whole};
    }
    if (a.deviation < 12 || b.deviation < 12) return {kind: 'inconclusive', status: 'insufficient_data', reason: 'low_detail'};
    const aspect = publication.width / publication.height;
    const maxWidth = Math.min(reference.width, reference.height * aspect);
    const small = descriptor(publication, undefined, 10), candidates = [];
    function consider(region, size, target) {
      const metrics = distance(target, descriptor(reference, region, size));
      const score = metrics.correlation - metrics.error * .7;
      if (metrics.correlation > .75) candidates.push({region, metrics, score});
    }
    // Bounded search; it does not claim to match rotations, mirrors or arbitrary edits.
    for (let scale = 1; scale >= .24; scale -= .04) {
      const width = maxWidth * scale, height = width / aspect, step = Math.max(3, Math.round(width / 12));
      const xs = [], ys = [];
      for (let x = 0; x <= reference.width - width; x += step) xs.push(x);
      for (let y = 0; y <= reference.height - height; y += step) ys.push(y);
      xs.push(reference.width - width); ys.push(reference.height - height);
      for (const x of xs) for (const y of ys) consider({x, y, width, height}, 10, small);
    }
    candidates.sort((x, y) => y.score - x.score);
    const seeds = candidates.slice(0, 8), refined = [];
    for (const seed of seeds) {
      const r = seed.region;
      for (let dw = -3; dw <= 3; dw++) for (let dy = -3; dy <= 3; dy++) for (let dx = -3; dx <= 3; dx++) {
        const width = r.width + dw, height = width / aspect, x = r.x + dx, y = r.y + dy;
        if (width < 12 || height < 12 || x < 0 || y < 0 || x + width > reference.width + .01 || y + height > reference.height + .01) continue;
        const region = {x, y, width, height}, metrics = distance(a, descriptor(reference, region, 24));
        refined.push({region, metrics, score: metrics.correlation - metrics.error * .7});
      }
    }
    refined.sort((x, y) => y.score - x.score);
    const best = refined[0];
    if (best && best.metrics.correlation > .985 && best.metrics.error < .045) {
      const {region: r} = best;
      // Repeated/periodic patterns cannot identify a unique crop reliably.
      const rival = refined.find(item => Math.hypot(item.region.x - r.x, item.region.y - r.y) > Math.min(r.width, r.height) * .4);
      if (rival && best.score - rival.score < .012) return {kind: 'inconclusive', status: 'insufficient_data', reason: 'ambiguous_match'};
      const region = {x: r.x / reference.width, y: r.y / reference.height, width: r.width / reference.width, height: r.height / reference.height};
      const retained_area = region.width * region.height;
      if (retained_area < .95) return {kind: 'crop_candidate', status: 'needs_review', region, retained_area, metrics: best.metrics};
    }
    return {kind: 'not_matched', status: 'insufficient_data'};
  }
  function captureDateNote(captured, published) {
    if (!captured || !/^\d{4}-\d{2}-\d{2}$/.test(published || '')) return null;
    const date = captured.slice(0, 10).replaceAll(':', '-');
    for (const value of [date, published]) {
      const parsed = Date.parse(value);
      if (!Number.isFinite(parsed) || new Date(parsed).toISOString().slice(0, 10) !== value) return null;
    }
    const difference = Math.round((Date.parse(published) - Date.parse(date)) / 86400000);
    return Number.isFinite(difference) ? {captured_date: date, publication_date: published, difference_days: difference} : null;
  }
  const api = {MAX_BYTES, MAX_PIXELS, headerInfo, captionCues, compareImages, captureDateNote};
  root.PhotoContext = Object.freeze(api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
