"""Read-only audit of retained publication versions; no private bodies exported."""
import json
from pathlib import Path
import sqlite3
import sys
p=Path(sys.argv[1])
if not p.exists():
    raise SystemExit('Retained corpus was not restored')
db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
counts={'articles':db.execute('SELECT count(*) FROM articles').fetchone()[0], 'revisions':db.execute('SELECT count(*) FROM revisions').fetchone()[0]}
rows=db.execute('''SELECT a.id,a.source_id,r.title,r.text,r.canonical_url,r.retrieved_at,r.extractor_version
 FROM articles a JOIN revisions r ON r.article_id=a.id WHERE a.id IN
 (SELECT article_id FROM revisions GROUP BY article_id HAVING count(*)>1)
 ORDER BY a.id,r.retrieved_at,r.id''')
previous={};examples=[];title_changes=body_changes=extractor_changes=0;multi=set()
for row in rows:
 multi.add(row['id']);old=previous.get(row['id']);previous[row['id']]=row
 if old is None:continue
 if old['extractor_version']!=row['extractor_version']:extractor_changes+=1;continue
 title=old['title']!=row['title'];body=old['text']!=row['text'];title_changes+=title;body_changes+=body
 if (title or body) and len(examples)<8:
  examples.append({'source':row['source_id'],'url':row['canonical_url'],'before':old['title'][:250],'after':row['title'][:250],'before_at':old['retrieved_at'],'after_at':row['retrieved_at'],'body_changed':body})
counts.update(articles_with_versions=len(multi),title_changes=title_changes,body_changes=body_changes,extractor_transitions=extractor_changes,examples=examples)
message=json.dumps(counts,ensure_ascii=False).replace('%','%25').replace('\r','%0D').replace('\n','%0A')
print('::notice title=PRO retained corpus audit::'+message)
