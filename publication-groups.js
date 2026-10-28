/* Original platform variants stay intact; a filtered view shows one copy. */
'use strict';
window.PublicationGroups = Object.freeze({
  candidates(articles) {
    return articles.flatMap(item => {
      if (item.variants === undefined) return [item];
      if (!Array.isArray(item.variants) || item.variants.length > 1 ||
          typeof item.publication_id !== 'string') throw Error('publication variants');
      for (const variant of item.variants) {
        if (!variant || variant.variants !== undefined || variant.id === item.id ||
            variant.publication_id !== item.publication_id ||
            variant.publisher_id !== item.publisher_id || variant.platform === item.platform) {
          throw Error('publication variant');
        }
      }
      return [item, ...item.variants];
    });
  },
  unique(items, raw = item => item) {
    const seen = new Set();
    return items.filter(item => {
      const value = raw(item);
      const key = value.publication_id || 'article-' + value.id;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }
});
