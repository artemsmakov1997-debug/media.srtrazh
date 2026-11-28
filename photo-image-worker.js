/* Local files only. No external models, remote image URLs or upload requests. */
'use strict';
importScripts('photo-context-core.js?v=20261128');
const images = new Map();
const versions = {publication: 0, reference: 0};
async function inspect(file) {
  if (!(file instanceof Blob)) throw Error('Выберите файл фотографии.');
  if (file.size > PhotoContext.MAX_BYTES) throw Error('Выберите фото размером до 12 МБ.');
  const bytes = await file.arrayBuffer(), header = PhotoContext.headerInfo(bytes);
  let bitmap;
  try { bitmap = await createImageBitmap(file); } catch { throw Error('Файл не удалось открыть как фото. Попробуйте JPEG, PNG или WebP.'); }
  try {
    if (bitmap.width * bitmap.height > PhotoContext.MAX_PIXELS) throw Error('Уменьшите фото до 24 мегапикселей.');
    const scale = Math.min(1, 1000 / Math.max(bitmap.width, bitmap.height));
    const canvas = new OffscreenCanvas(Math.max(1, Math.round(bitmap.width * scale)), Math.max(1, Math.round(bitmap.height * scale)));
    const context = canvas.getContext('2d', {willReadFrequently: true});
    context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const preview = await canvas.convertToBlob({type: 'image/jpeg', quality: .9});
    const smallScale = Math.min(1, 160 / Math.max(bitmap.width, bitmap.height));
    const small = new OffscreenCanvas(Math.max(1, Math.round(bitmap.width * smallScale)), Math.max(1, Math.round(bitmap.height * smallScale)));
    const ctx = small.getContext('2d', {willReadFrequently: true});
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, small.width, small.height);
    ctx.drawImage(bitmap, 0, 0, small.width, small.height);
    let sha256 = null;
    if (self.crypto?.subtle) sha256 = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(value => value.toString(16).padStart(2, '0')).join('');
    const summary = {...header, width: bitmap.width, height: bitmap.height, bytes: file.size, file_name: file.name || 'Фото', sha256};
    return {summary, preview, pixels: ctx.getImageData(0, 0, small.width, small.height)};
  } finally { bitmap.close(); }
}
addEventListener('message', async event => {
  const {id, action, role, file} = event.data || {};
  let version;
  try {
    if (action === 'inspect') {
      if (!['publication', 'reference'].includes(role)) throw Error('Неизвестный файл.');
      version = ++versions[role];
      const image = await inspect(file);
      if (version === versions[role]) images.set(role, image);
      postMessage({id, type: 'result', result: {summary: image.summary, preview: image.preview}});
    } else if (action === 'compare') {
      const publication = images.get('publication'), reference = images.get('reference');
      if (!publication) throw Error('Добавьте фото из публикации.');
      const result = reference ? PhotoContext.compareImages(publication.pixels, reference.pixels,
        Boolean(publication.summary.sha256 && publication.summary.sha256 === reference.summary.sha256)) : {kind: 'no_reference', status: 'insufficient_data'};
      postMessage({id, type: 'result', result});
    } else if (action === 'clear') {
      if (role) { images.delete(role); versions[role]++; }
      else { images.clear(); versions.publication++; versions.reference++; }
      postMessage({id, type: 'result', result: null});
    }
  } catch (error) {
    if (action === 'inspect' && version === versions[role]) images.delete(role);
    postMessage({id, type: 'error', message: error.message || 'Не удалось проверить фото. Попробуйте другой файл.'});
  }
});
