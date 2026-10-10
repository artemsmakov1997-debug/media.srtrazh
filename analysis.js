/* Public snapshot viewer. Publisher text is always inserted as text, never HTML. */
'use strict';
const element = id => document.getElementById(id);
const statuses = {
  needs_review: 'Требует проверки',
  quoted_candidate: 'Цитата или переданная речь — проверьте автора высказывания',
  context_only: 'Отрицание или обсуждение формулировки'
};
const publishers = {rt: 'russian.rt.com', tass: 'tass.ru', ria: 'ria.ru'};
let report = null;

function node(tag, text, className) {
  const result = document.createElement(tag);
  result.textContent = text;
  if (className) result.className = className;
  return result;
}

function date(value) {
  if (!value || !Number.isFinite(Date.parse(value))) return 'не указана';
  return new Date(value).toLocaleString('ru-RU', {timeZone: 'Europe/Moscow'}) + ' МСК';
}

function original(item) {
  try {
    const url = new URL(item.url);
    if (url.protocol !== 'https:' || url.hostname !== publishers[item.source_id] ||
        url.username || url.password || (url.port && url.port !== '443')) return null;
    const link = node('a', 'Открыть оригинал публикации →');
    link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
    return link;
  } catch { return null; }
}

function excerpt(evidence) {
  const result = node('div', '', 'context');
  const sentence = evidence.sentence;
  const text = Array.from(sentence.text);
  const start = evidence.start - sentence.start;
  const end = evidence.end - sentence.start;
  if (start < 0 || end > text.length || text.slice(start, end).join('') !== evidence.quote) {
    result.textContent = sentence.text;
    return result;
  }
  result.append(document.createTextNode(text.slice(0, start).join('')));
  result.append(node('mark', text.slice(start, end).join('')));
  result.append(document.createTextNode(text.slice(end).join('')));
  return result;
}

function render() {
  element('articles').replaceChildren();
  const selected = report.articles.filter(item =>
    (!element('source').value || item.source_id === element('source').value) &&
    (!element('candidates').checked || (item.summary && item.summary.review_fragments > 0)));
  element('selection').textContent = 'Показано публикаций: ' + selected.length + '.';
  if (!selected.length) element('articles').append(node('p', 'В этой подборке нет публикаций, соответствующих фильтру.', 'muted'));
  for (const item of selected) {
    const article = node('article', '', 'publication');
    article.append(node('p', item.source + ' · ' + date(item.published_at), 'muted'));
    article.append(node('h2', item.title));
    const link = original(item);
    if (link) article.append(link);
    article.append(node('p', 'Получена: ' + date(item.retrieved_at), 'muted'));
    if (!item.summary) {
      article.append(node('p', 'Анализ текущей версией ещё не сохранён.', 'muted'));
    } else {
      const counts = item.summary;
      article.append(node('p', 'Фрагментов для проверки: ' + counts.review_fragments +
        '. Меток приёмов: ' + counts.review_candidates +
        '. В цитатах или переданной речи: ' + counts.quoted_candidates + '.', 'badge'));
      if (!item.findings.length) {
        article.append(node('p', 'Совпадений текущих правил не найдено. Это не доказывает нейтральность текста.', 'muted'));
      } else {
        const details = document.createElement('details');
        details.append(node('summary', 'Посмотреть найденные фрагменты и объяснения'));
        for (const finding of item.findings) {
          const card = node('section', '', 'finding');
          card.append(node('p', statuses[finding.status] || finding.status, 'badge'));
          card.append(node('h3', finding.label), node('p', finding.explanation));
          for (const evidence of finding.evidence) {
            card.append(node('p', evidence.field === 'title' ? 'Фрагмент заголовка' : 'Фрагмент текста', 'muted'));
            card.append(excerpt(evidence));
            if (evidence.sentence.truncated) card.append(node('p', 'Показан ограниченный фрагмент контекста.', 'muted'));
          }
          card.append(node('p', finding.review_question));
          details.append(card);
        }
        if (item.findings_omitted) details.append(node('p', 'Других меток в результате: ' + item.findings_omitted + '. Подборка ограничена.', 'muted'));
        article.append(details);
      }
      if (counts.findings_truncated) article.append(node('p', 'Полный результат ограничен первыми 500 совпадениями; сводка неполная.', 'muted'));
    }
    element('articles').append(article);
  }
}

async function load() {
  try {
    const response = await fetch('data/analysis.json', {cache: 'no-store', signal: AbortSignal.timeout(20000)});
    if (!response.ok) throw new Error('snapshot unavailable');
    report = await response.json();
    if (report.schema_version !== 'public-snapshot-1.0' || !Array.isArray(report.articles)) throw new Error('invalid snapshot');
    element('updated').textContent = 'Подборка обновлена: ' + date(report.generated_at) +
      '. Версия анализа: ' + report.algorithm_version + '.';
    const age = Date.now() - Date.parse(report.generated_at);
    if (Number.isFinite(age) && age > 90 * 60 * 1000) {
      element('updated').classList.add('error');
      element('updated').append(document.createTextNode(' Подборка давно не обновлялась.'));
    }
    element('totals').textContent = 'В подборке: ' + report.totals.displayed +
      '. Проанализировано: ' + report.totals.analyzed +
      '. С фрагментами для проверки: ' + report.totals.with_review_candidates + '.';
    for (const source of report.sources) {
      const card = node('section', '', 'source');
      card.append(node('h2', source.name), node('p', 'Публикаций в подборке: ' + source.displayed));
      card.append(node('p', source.status ? 'Последняя проверка: ' + date(source.status.last_attempt_at) : 'Источник ещё не проверялся.', 'muted'));
      if (source.status && source.status.last_error) card.append(node('p', source.status.last_error, 'error'));
      element('sources').append(card);
    }
    element('coverage').textContent = report.coverage.map(item => item.label + ': ' +
      (item.coverage === 'candidate_rules' ? 'поиск отдельных признаков' : 'не проверяется')).join('; ') + '.';
    element('coverageBlock').hidden = false;
    element('controls').hidden = false;
    render();
  } catch {
    element('updated').textContent = 'Подборка пока недоступна.';
    element('error').textContent = 'Публикации появятся после успешного сбора. Попробуйте обновить страницу позже.';
    element('error').hidden = false;
  }
}
element('source').addEventListener('change', render);
element('candidates').addEventListener('change', render);
load();
