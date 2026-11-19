"""Bounded, evidence-only public comparisons and recorded revisions."""
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
import re
from .sources import SOURCES

STOP = {'после','перед','через','будет','будут','который','также','этого','россии','сообщили','заявил'}
def words(title):
    return {w for w in re.findall(r'[а-яёa-z0-9]+',title.lower()) if len(w)>3 and w not in STOP}

def fragments(before, after):
    # Limit both computation and public reproduction. Include the first change.
    prefix=0
    while prefix<min(len(before),len(after)) and before[prefix]==after[prefix]:prefix+=1
    offset=max(0,prefix-400)
    a=re.findall(r'\s+|[^\s]+',before[offset:offset+12000])
    b=re.findall(r'\s+|[^\s]+',after[offset:offset+12000])
    matcher=SequenceMatcher(None,a,b,autojunk=True)
    changes=[op for op in matcher.get_opcodes() if op[0]!='equal']
    if not changes:return [],[]
    _,i,j,k,l=changes[0]
    a0,b0=max(0,i-12),max(0,k-12)
    a1,b1=min(len(a),max(j,i+24),a0+100),min(len(b),max(l,k+24),b0+100)
    def segments(side):
        result=[];remaining=600
        for tag,x,y,u,v in matcher.get_opcodes():
            start,end,lo,hi=(x,y,a0,a1) if side==0 else (u,v,b0,b1)
            start,end=max(start,lo),min(end,hi)
            if end>start and remaining:
                text=''.join((a if side==0 else b)[start:end])[:remaining]
                result.append({'text':text,'changed':tag!='equal'});remaining-=len(text)
        return result
    return segments(0),segments(1)

def pro_snapshot(store):
    rows=store.db.execute('''SELECT a.id,a.source_id,r.id AS revision_id,r.title,r.text,r.canonical_url,
        r.published_at,r.retrieved_at,r.extractor_version FROM articles a JOIN revisions r ON r.article_id=a.id
        ORDER BY r.retrieved_at DESC,r.id DESC LIMIT 1000''').fetchall()
    by_article=defaultdict(list)
    for r in rows:by_article[r['id']].append(r)
    history=[]; latest=[]
    for versions in by_article.values():
        versions.sort(key=lambda r:(r['retrieved_at'],r['revision_id']))
        current=versions[-1];source=SOURCES.get(current['source_id'])
        if not source:continue
        latest.append((current,source))
        pairs=[]
        for old,new in zip(versions,versions[1:]):
            if old['extractor_version']!=new['extractor_version']:continue
            title_changed=old['title']!=new['title'];text_changed=old['text']!=new['text']
            if not(title_changed or text_changed):continue
            for kind,field,changed in (('title','title',title_changed),('text','text',text_changed)):
                if not changed:continue
                before,after=fragments(old[field],new[field])
                if not before and not after:continue
                pairs.append({'before':before,'after':after,'before_at':old['retrieved_at'],'after_at':new['retrieved_at'],
                              'kind':kind,'title':new['title'][:250]})
        if pairs:history.append({'source':source.name,'source_id':source.id,'url':current['canonical_url'],
                                  'versions':pairs[-5:]})
    stories=[];used=set()
    for i,(anchor,source) in enumerate(latest):
        if i in used or len(words(anchor['title']))<3:continue
        group=[(anchor,source)];publishers={source.publisher};indices=[i]
        for j,(other,other_source) in enumerate(latest[i+1:],i+1):
            if j in used or other_source.publisher in publishers:continue
            try:
                delta=abs((datetime.fromisoformat(anchor['published_at'])-datetime.fromisoformat(other['published_at'])).total_seconds())
            except (ValueError,TypeError):continue
            if delta>86400:continue
            a,b=words(anchor['title']),words(other['title']);shared=a&b
            if len(shared)<3 or len(shared)/len(a|b)<.55:continue
            # Different numbers can indicate different events or outcomes.
            if re.findall(r'\d+',anchor['title'])!=re.findall(r'\d+',other['title']):continue
            group.append((other,other_source));publishers.add(other_source.publisher);indices.append(j)
            if len(group)==6:break
        if len(group)<2:continue
        used.update(indices)
        common=set.intersection(*(words(r['title']) for r,s in group))
        stories.append({'title':anchor['title'][:250],'items':[{'source':s.name,'url':r['canonical_url'],
            'published_at':r['published_at'],'title':r['title'][:250],
            'phrases':[{'text':m.group(),'changed':m.group().lower() not in common and len(m.group())>3}
                       for m in re.finditer(r'\w+|\W+',r['title'][:250])]} for r,s in group]})
        if len(stories)==8:break
    history.sort(key=lambda h:h['versions'][-1]['after_at'],reverse=True)
    return {'schema_version':'pro-evidence-1.0','stories':stories,'history':history[:20]}
