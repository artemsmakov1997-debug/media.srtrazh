"""Synthetic contracts for preparation/evaluation; never a human-labelled corpus."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from media_strazh.analysis import SUPPORTED, analyze
from media_strazh.benchmark import SCHEMA, prepare_benchmark, evaluate_benchmark


def record(index,text=None,source='ria'):
    document={'title':'Проверочный материал '+str(index),'text':text or ('Тема'+str(index)+' ')*30,'url':'https://ria.ru/news/'+str(index),'source':'Синтетический пример','published_at':'2026-10-10T09:00:00+00:00'}
    return {'id':source+':'+str(index)+':r'+str(index),'document':document,'schema_version':SCHEMA,'split':'development',
            'fully_annotated':False,'reviewer':'','labels':None,'spans':[], 'annotation_categories':sorted(SUPPORTED),
            'provenance':{'sha256':analyze(document)['document']['sha256']}}


class Records:
    def __init__(self,rows): self.rows=rows
    def export_corpus(self): return iter(copy.deepcopy(self.rows))


class BenchmarkTests(unittest.TestCase):
    def test_real_selection_contract_is_deterministic_disjoint_and_without_predictions(self):
        rows=[record(i,source='ria' if i%2 else 'ria_telegram') for i in range(1,20)]
        with tempfile.TemporaryDirectory() as directory:
            first,second=Path(directory)/'first',Path(directory)/'second'
            result=prepare_benchmark(Records(rows),first,size=12)
            prepare_benchmark(Records(rows),second,size=12)
            self.assertEqual(result['splits'],{'holdout':4,'development':8})
            for name in ('development.jsonl','holdout.jsonl','manifest.json'):
                self.assertEqual((first/name).read_bytes(),(second/name).read_bytes())
            data=[json.loads(line) for name in ('development','holdout') for line in (first/(name+'.jsonl')).read_text().splitlines()]
            self.assertEqual(len({r['provenance']['sha256'] for r in data}),12)
            self.assertTrue(all(r['labels'] is None and not r['fully_annotated'] and not r['spans'] for r in data))
            self.assertTrue((first/'annotation.html').exists())
            with self.assertRaises(ValueError): prepare_benchmark(Records(rows),first,size=12)

    def test_duplicates_known_development_examples_and_insufficient_pool(self):
        rows=[record(i) for i in range(1,8)]
        rows.append(copy.deepcopy(rows[0]));rows[-1]['id']='ria:100:r100';rows[-1]['document']['url']='https://ria.ru/duplicate'
        excluded=record(99);excluded['document']['url']='https://t.me/izvestia/253503';rows.append(excluded)
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'corpus';prepare_benchmark(Records(rows),output,size=6)
            manifest=json.loads((output/'manifest.json').read_text())
            self.assertEqual(manifest['duplicates_excluded'],1)
            self.assertEqual(manifest['excluded_known_development'],1)
            with self.assertRaises(ValueError): prepare_benchmark(Records(rows),Path(directory)/'too-many',size=12)
            self.assertFalse((Path(directory)/'too-many').exists())

    def test_unreviewed_texts_are_not_treated_as_negative_gold(self):
        result=evaluate_benchmark([record(1,'Возмутительное решение правительства.')])
        self.assertEqual(result['status'],'awaiting_human_review')
        self.assertIsNone(result['metrics'])
        self.assertEqual((result['reviewed'],result['pending']),(0,1))

    def reviewed(self,text):
        row=record(1,text);row.update(fully_annotated=True,reviewer='Synthetic test reviewer',spans=[],labels=[])
        return row

    def test_exact_unicode_spans_and_quoted_voice_are_scored_separately(self):
        text='📰 Министр сказал: «Возмутительное решение».'
        row=self.reviewed(text)
        f=analyze(row['document'])['findings'][0];e=f['evidence'][0]
        row['spans']=[{k:e[k] for k in ('field','start','end','quote')}|{'category':f['category'],'status':f['status']}]
        result=evaluate_benchmark([row]);metrics=result['metrics']
        self.assertEqual(metrics['exact_spans_with_status']['tp'],1)
        self.assertEqual(metrics['by_status']['quoted_candidate']['tp'],1)
        self.assertEqual(metrics['voice_accuracy_on_matched_spans'],1)
        row['spans'][0]['status']='needs_review';row['labels']=[f['category']]
        metrics=evaluate_benchmark([row])['metrics']
        self.assertEqual(metrics['voice_accuracy_on_matched_spans'],0)
        self.assertEqual(metrics['exact_spans_with_status']['fp'],1)
        self.assertEqual(metrics['exact_spans_with_status']['fn'],1)

    def test_human_confirmed_negative_can_reveal_a_false_positive(self):
        result=evaluate_benchmark([self.reviewed('Возмутительное решение правительства.')])
        self.assertEqual(result['metrics']['exact_spans_with_status']['fp'],1)
        self.assertEqual(result['metrics']['document_category_author']['emotional_evaluation']['fp'],1)
        self.assertTrue(result['errors'][0]['predicted'][0]['rule_id'])

    def test_unresolved_invalid_and_incomplete_annotations_cannot_claim_accuracy(self):
        row=self.reviewed('Возмутительное решение.')
        with self.assertRaises(ValueError): evaluate_benchmark([dict(row,reviewer='')])
        changed=copy.deepcopy(row);changed['document']['text']='Изменённый оригинал.'
        with self.assertRaises(ValueError): evaluate_benchmark([changed])
        f=analyze(row['document'])['findings'][0];e=f['evidence'][0]
        row['spans']=[{k:e[k] for k in ('field','start','end','quote')}|{'category':f['category'],'status':'uncertain'}]
        result=evaluate_benchmark([row]);self.assertEqual(result['unresolved'],1);self.assertIsNone(result['metrics'])
        row['spans'][0]['end']+=1
        with self.assertRaises(ValueError): evaluate_benchmark([row])

    def test_manifest_prevents_changing_split_or_reference_and_counts_missing_rows(self):
        row=self.reviewed('Открылась городская библиотека.')
        manifest={'documents':[{'id':row['id'],'sha256':row['provenance']['sha256'],'split':'development'},
                               {'id':'missing','sha256':'0'*64,'split':'development'}]}
        result=evaluate_benchmark([row],manifest=manifest)
        self.assertEqual(result['pending'],1);self.assertEqual(result['status'],'partial')
        changed=copy.deepcopy(row);changed['split']='holdout'
        with self.assertRaises(ValueError): evaluate_benchmark([changed],split='holdout',manifest=manifest)
