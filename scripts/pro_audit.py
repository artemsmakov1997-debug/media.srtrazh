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
 if title and len(examples)<3:
  examples.append({'source':row['source_id'],'url':row['canonical_url'],'before':old['title'][:250],'after':row['title'][:250],'before_at':old['retrieved_at'],'after_at':row['retrieved_at'],'body_changed':body})
counts.update(articles_with_versions=len(multi),title_changes=title_changes,body_changes=body_changes,extractor_transitions=extractor_changes,examples=examples)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from media_strazh.pro import pro_snapshot
from types import SimpleNamespace
pro=pro_snapshot(SimpleNamespace(db=db))
counts['pro_history_publications']=len(pro['history'])
counts['latest_change_at']=max((v['after_at'] for h in pro['history'] for v in h['versions']),default=None)
from datetime import datetime,timedelta,timezone
cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
counts['changed_publications_last_week']=sum(any(v['after_at']>=cutoff for v in h['versions']) for h in pro['history'])
counts['pro_stories']=len(pro['stories'])
counts['story_examples']=[{'topic':s.get('topic'),'titles':[i['title'][:150] for i in s['items'][:2]]} for s in pro['stories'][:2]]
message=json.dumps(counts,ensure_ascii=False).replace('%','%25').replace('\r','%0D').replace('\n','%0A')
print('::notice title=PRO retained corpus audit::'+message)
