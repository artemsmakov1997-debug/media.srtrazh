import sqlite3
import unittest
from media_strazh.pro import pro_snapshot,fragments
class ProTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
  self.db.executescript('CREATE TABLE articles(id INTEGER,source_id TEXT); CREATE TABLE revisions(id INTEGER,article_id INTEGER,title TEXT,text TEXT,canonical_url TEXT,published_at TEXT,retrieved_at TEXT,extractor_version TEXT);')
 def add(self,id,source,title,time='2026-11-19T10:00:00+00:00',article=None,extractor='v1'):
  article=article or id
  if not self.db.execute('SELECT 1 FROM articles WHERE id=?',(article,)).fetchone():self.db.execute('INSERT INTO articles VALUES (?,?)',(article,source))
  self.db.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?)',(id,article,title,'Основной текст', 'https://tass.ru/test',time,time,extractor))
 def test_empty(self):self.assertEqual(pro_snapshot(self)['history'],[])
 def test_related_headlines_distinct_publishers(self):
  self.add(1,'tass','На Северном мосту закроют две полосы движения')
  self.add(2,'ria','На Северном мосту закроют две полосы движения из-за ремонта')
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
