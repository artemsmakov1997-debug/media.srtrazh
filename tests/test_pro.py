import sqlite3
import unittest
from media_strazh.pro import pro_snapshot,fragments,headline_parts
class ProTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
  self.db.executescript('CREATE TABLE articles(id INTEGER,source_id TEXT,current_revision_id INTEGER); CREATE TABLE revisions(id INTEGER,article_id INTEGER,title TEXT,text TEXT,canonical_url TEXT,published_at TEXT,retrieved_at TEXT,extractor_version TEXT);')
 def add(self,id,source,title,time='2026-11-19T10:00:00+00:00',article=None,extractor='v1'):
  article=article or id
  if not self.db.execute('SELECT 1 FROM articles WHERE id=?',(article,)).fetchone():self.db.execute('INSERT INTO articles(id,source_id) VALUES (?,?)',(article,source))
  self.db.execute('UPDATE articles SET current_revision_id=? WHERE id=?',(id,article))
  self.db.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?)',(id,article,title,'Основной текст', 'https://tass.ru/test',time,time,extractor))
 def test_empty(self):self.assertEqual(pro_snapshot(self)['history'],[])
 def test_related_headlines_distinct_publishers(self):
  self.add(1,'tass','Германия поддержала новые санкции против России из-за войны')
  self.add(2,'ria','Германия назвала новые санкции против России ответом на войну')
  self.assertEqual(len(pro_snapshot(self)['stories']),1)
 def test_same_publisher_or_different_numbers_do_not_group(self):
  self.add(1,'tass','На Северном мосту закроют 2 полосы движения')
  self.add(2,'tass_telegram','На Северном мосту закроют 2 полосы движения')
  self.add(3,'ria','На Северном мосту закроют 3 полосы движения')
  self.assertEqual(pro_snapshot(self)['stories'],[])
 def test_real_versions_and_extractor_guard(self):
  self.add(1,'tass','Мост полностью закроют')
  self.add(2,'tass','На мосту закроют две полосы',time='2026-11-19T12:00:00+00:00',article=1)
  report=pro_snapshot(self);self.assertEqual(len(report['history']),1)
  version=report['history'][0]['versions'][0]
  self.assertEqual(''.join(x['text'] for x in version['after']),'На мосту закроют две полосы')
  self.assertEqual(version['before_at'],'2026-11-19T10:00:00+00:00')
  self.db.execute("UPDATE revisions SET extractor_version='v2' WHERE id=2")
  self.assertEqual(pro_snapshot(self)['history'],[])
 def test_diff_bounded_and_empty(self):
  self.assertEqual(fragments('same','same'),([],[]))
  a,b=fragments('x'*1000,'y'*1000)
  self.assertLessEqual(sum(len(s['text']) for s in b),600)

 def test_word_diff_keeps_long_unchanged_context_readable(self):
  before=('Сохраняется обычное движение. '*30)+' Работы завершатся до конца недели.'
  after=before.replace('до конца недели','до 4 декабря')
  old,new=fragments(before,after)
  self.assertTrue(any(x['changed'] and '4' in x['text'] for x in new))
  self.assertTrue(any(not x['changed'] for x in new))

 def test_late_edit_and_both_fields_remain_visible(self):
  before='Неизменная строка. '*1000+' Старый срок.'
  after=before.replace('Старый срок','Новый срок')
  a,b=fragments(before,after)
  self.assertTrue(any(x['changed'] and 'Новый' in x['text'] for x in b))
  self.add(1,'tass','Первый заголовок')
  self.add(2,'tass','Второй заголовок',time='2026-11-19T12:00:00+00:00',article=1)
  self.db.execute("UPDATE revisions SET text='Уточнённый текст' WHERE id=2")
  self.assertEqual({v['kind'] for v in pro_snapshot(self)['history'][0]['versions']},{'title','text'})

 def test_headline_explanations_use_the_existing_detector(self):
  title='Все знают: нас ждёт неминуемая катастрофа'
  parts=headline_parts(title,set(title.lower().split()))
  self.assertEqual(''.join(p['text'] for p in parts),title)
  self.assertTrue(any(p.get('explanation') and p['changed'] for p in parts))

 def test_apolitical_and_cosmetic_political_rewrites_are_excluded(self):
  for id,source,title in [(1,'tass','В городе открыли новый спортивный центр'),(2,'ria','В городе открыли новый спортивный центр для детей'),(3,'aif','Трамп назвал РФ, Китай и США самыми могущественными странами мира'),(4,'vedomosti','Трамп назвал США, Россию и Китай самыми могущественными странами в мире')]:
   self.add(id,source,title)
  self.assertEqual(pro_snapshot(self)['stories'],[])
 def test_old_edits_are_not_hidden_by_recent_single_version_articles(self):
  self.add(1,'tass','Первый заголовок',time='2026-10-01T10:00:00+00:00')
  self.add(2,'tass','Уточнённый заголовок',time='2026-10-01T11:00:00+00:00',article=1)
  for id in range(3,1105):self.add(id,'ria','Новая одиночная публикация')
  self.assertEqual(len(pro_snapshot(self)['history']),1)
