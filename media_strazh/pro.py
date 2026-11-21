"""Bounded, evidence-only public comparisons and recorded revisions."""
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
import re
from .sources import SOURCES
from .analysis import analyze

STOP = {'после','перед','через','будет','будут','который','также','этого','сообщили','заявил','назвал','самыми','самые','странами','страны','мире','мира'}
TOPICS = (
    ('Война и безопасность',r'\b(?:войн|военн|всу|удар|ракет|дрон|мобилиз|плен|перемири|обстрел|оккупац|аннекси)[а-яё]*\b'),
    ('Санкции и международные решения',r'\b(?:санкци|нато|дипломат|ультиматум|переговор|мирн[а-яё]*\s+соглашени|оборонн[а-яё]*\s+союз)[а-яё]*\b'),
    ('Права и свободы',r'\b(?:политзаключ|репресси|цензур|иноагент|политическ[а-яё]*\s+преследован|запрет[а-яё]*\s+(?:партии|сми|митинг)|приговор|протест)[а-яё]*\b'),
    ('Выборы и власть',r'\b(?:выбор(?:ы|ов|ам|ами|ах)|референдум[а-яё]*|отставк[а-яё]*|импичмент[а-яё]*|парламент[а-яё]*|госпереворот[а-яё]*)\b'),
)
def political_topic(title):
    for name,pattern in TOPICS:
        if not re.search(pattern,title,re.I):continue
        if name=='Война и безопасность':
            literal=re.search(r'\b(?:футбол|матч|бокс|теннис|пенальти|шайб|мороз|погод|космодром|орбит|космическ)[а-яё]*\b',title,re.I)
            military=re.search(r'\b(?:войн|военн|всу|обстрел|мобилиз|плен|оккупац|аннекси|перемири)[а-яё]*\b',title,re.I)
            if literal and not military:continue
        return name
    return None

def token_key(word):
    word=word.lower().replace('ё','е')
    if word in {'рф','россия','россии','россию','россией'}:return 'россия'
    if word in {'сша','соединенные'}:return 'сша'
    root=re.sub(r'(?:иями|ами|ого|ему|ому|ыми|ими|иях|ах|ях|ов|ев|ом|ем|ый|ий|ой|ая|яя|ое|ее|ую|юю|ые|ие|ы|и|а|я|у|ю|е|о)$','',word)
    return root if len(root)>=4 else word

def words(title):
    return {token_key(w) for w in re.findall(r'[а-яёa-z0-9]+',title.lower()) if len(w)>3 and w not in STOP}

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

def headline_parts(title, common):
    findings=analyze({'title':title,'text':'Опубликован материал.'})['findings']
    evidence=[(e,f) for f in findings for e in f['evidence'] if e['field']=='title']
    result=[]
    for m in re.finditer(r'\w+|\W+',title):
        matches=[f for e,f in evidence if e['start']<m.end() and m.start()<e['end']]
        part={'text':m.group(),'changed':bool(matches) or (token_key(m.group()) not in common and len(m.group())>3 and m.group().lower() not in STOP and bool(re.fullmatch(r'\w+',m.group())))}
        if matches:
            part['explanation']=' '.join(dict.fromkeys(
                ('Цитата или переданная речь. ' if f['status']=='quoted_candidate' else '')+
                f['label']+': '+f['explanation'] for f in matches))
        result.append(part)
    return result

def pro_snapshot(store):
    # Select revision-bearing articles first: a global recent-row cap hid
    # older real changes behind new single-version publications.
    rows=store.db.execute('''SELECT a.id,a.source_id,r.id AS revision_id,r.title,r.text,r.canonical_url,
        r.published_at,r.retrieved_at,r.extractor_version FROM articles a JOIN revisions r ON r.article_id=a.id
        WHERE a.id IN (SELECT article_id FROM revisions GROUP BY article_id HAVING count(*)>1)
        ORDER BY r.retrieved_at DESC,r.id DESC LIMIT 20000''').fetchall()
    by_article=defaultdict(list)
    for r in rows:by_article[r['id']].append(r)
    history=[]; latest=[]
    for versions in by_article.values():
        versions.sort(key=lambda r:(r['retrieved_at'],r['revision_id']))
        current=versions[-1];source=SOURCES.get(current['source_id'])
        if not source:continue
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
    latest_rows=store.db.execute('''SELECT a.source_id,r.title,r.canonical_url,r.published_at
        FROM articles a JOIN revisions r ON r.id=a.current_revision_id
        WHERE r.title<>'' ORDER BY r.retrieved_at DESC,r.id DESC LIMIT 4000''').fetchall()
    latest=[(r,SOURCES[r['source_id']]) for r in latest_rows
            if r['source_id'] in SOURCES and political_topic(r['title'])]
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
            if political_topic(other['title'])!=political_topic(anchor['title']):continue
            if len(shared)<3 or len(shared)/len(a|b)<.4:continue
            if len(a^b)<2:continue
            # Different numbers can indicate different events or outcomes.
            if re.findall(r'\d+',anchor['title'])!=re.findall(r'\d+',other['title']):continue
            group.append((other,other_source));publishers.add(other_source.publisher);indices.append(j)
            if len(group)==6:break
        if len(group)<2:continue
        used.update(indices)
        common=set.intersection(*(words(r['title']) for r,s in group))
        stories.append({'topic':political_topic(anchor['title']),'contrast':len(set.union(*(words(r['title']) for r,s in group))-common),'title':anchor['title'][:250],'items':[{'source':s.name,'url':r['canonical_url'],
            'published_at':r['published_at'],'title':r['title'][:250],
            'phrases':headline_parts(r['title'][:250],common)} for r,s in group]})
        if len(stories)==40:break
    history.sort(key=lambda h:h['versions'][-1]['after_at'],reverse=True)
    stories.sort(key=lambda item:(item['contrast'],len(item['items'])),reverse=True)
    return {'schema_version':'pro-evidence-1.0','stories':stories[:8],'history':history[:20]}
