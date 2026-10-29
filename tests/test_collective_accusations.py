"""User-supplied missed text, transferable constructions and literal controls."""
import json
from pathlib import Path
import unittest

from media_strazh.analysis import MAX_FINDINGS, VERSION, analyze


USER_TEXT = Path(__file__).with_name('collective_publication.txt').read_text().rstrip('\n')
DOCUMENTS = {
    'collective_question': {'text': 'Почему русские стесняются признать, что национальной идеей является убийство?'},
    'collective_essence': {'text': 'Национальной идеей этой страны является уничтожение людей.'},
    'collective_immutable': {'text': 'Россия, даже если захочет измениться, сделать этого никогда не сможет.'},
    'collective_inferiority': {'text': 'Это отсталая страна с вторичной культурой.'},
    'collective_pathology': {'text': 'Украине приписали манию величия.'},
    'collective_hook': {'text': 'Президент оказался на китайском крючке.'},
    'collective_threat': {'text': 'Этой стране приписали жажду разрушения цивилизации.'},
    'collective_full': {'text': USER_TEXT},
}
TARGETS = {
    'collective_question': 'simplification.presupposed_confession',
    'collective_essence': 'generalization.violent_national_essence',
    'collective_immutable': 'generalization.immutable_collective',
    'collective_inferiority': 'enemy.civilizational_inferiority',
    'collective_pathology': 'enemy.collective_pathology',
    'collective_hook': 'enemy.foreign_hook',
    'collective_threat': 'enemy.civilizational_threat',
}
NEW_IDS = set(TARGETS.values())
EXPANDED_IDS = {'generalization.universal_claim', 'generalization.group_mental_state',
                'enemy.political_madness', 'enemy.derisive_communication'}


class CollectiveAccusationTests(unittest.TestCase):
    def find(self, text, rule):
        return [f for f in analyze({'text': text})['findings'] if f['rule_id'] == rule]

    def test_complete_original_missed_publication_has_specific_explanations(self):
        result = analyze({'text': USER_TEXT})
        self.assertEqual(result['algorithm_version'], VERSION)
        self.assertEqual(len(result['findings']), 13)
        self.assertEqual({f['rule_id'] for f in result['findings']}, NEW_IDS | EXPANDED_IDS)
        self.assertEqual(result['summary']['marker_fragments'], 13)
        self.assertFalse(result['summary']['findings_truncated'])
        for f in result['findings']:
            self.assertEqual(f['status'], 'needs_review')
            self.assertTrue(f['explanation'] and f['review_question'])
            self.assertEqual(f['rating_weight'], 1)

    def test_title_body_unicode_spans_and_serialization(self):
        for doc in DOCUMENTS.values():
            for field in ('title', 'text'):
                document = {'text': 'Опубликован документ.', field: '📰 ' + doc['text']}
                result = analyze(document)
                self.assertTrue(result['findings'])
                for f in result['findings']:
                    for evidence in f['evidence']:
                        self.assertEqual(document[evidence['field']][evidence['start']:evidence['end']], evidence['quote'])
                        sentence = evidence['sentence']
                        self.assertEqual(document[evidence['field']][sentence['start']:sentence['end']], sentence['text'])
                self.assertEqual(json.loads(json.dumps(result, ensure_ascii=False)), result)

    def test_accusatory_question_is_not_limited_to_one_country_or_verb(self):
        for subject in ('русские', 'украинцы', 'американцы', 'политики'):
            for verb in ('стесняются', 'боятся', 'отказываются', 'не хотят'):
                text = f'Почему {subject} до сих пор {verb} признать, что их целью является геноцид?'
                self.assertTrue(self.find(text, TARGETS['collective_question']), text)

    def test_ordinary_or_unfinished_questions_are_not_confession_accusations(self):
        for text in ('Почему русские учат иностранные языки?', 'Почему политики не хотят признать, что бюджет вырос?',
                     'Почему страна не хочет расследовать геноцид?',
                     'Почему политики стесняются признать, что они не знают ответа?',
                     'Русские стесняются признать, что национальной идеей является убийство.'):
            self.assertFalse(self.find(text, TARGETS['collective_question']), text)

    def test_claimed_knowledge_inflections_and_reversed_word_order(self):
        for phrase in ('Причины понятны и всем известны.', 'Всем известна причина решения.',
                       'Этот факт всем хорошо известен.', 'Последствий не понимает никто.',
                       'Никто не сомневается в решении.'):
            self.assertTrue(self.find(phrase, 'generalization.universal_claim'), phrase)
        self.assertFalse(self.find('Это всем известные препараты.', 'generalization.universal_claim'))

    def test_population_desires_work_without_other_political_keywords(self):
        for subject in ('Русские', 'Россияне', 'Украинцы', 'Американцы', 'Немцы', 'Французы',
                        'Поляки', 'Китайцы', 'Израильтяне', 'Палестинцы', 'Белорусы', 'Мигранты'):
            for claim in ('очень хотят войны', '— да, они очень хотят войны', 'жаждут крови', 'ненавидят соседей'):
                text = subject + ' ' + claim + '.'
                self.assertTrue(self.find(text, 'generalization.group_mental_state'), text)

    def test_quantified_subsets_and_explicit_negation_are_not_whole_group_desire(self):
        for phrase in ('Некоторые русские хотят войны.', 'Не все русские хотят войны.',
                       'Многие украинцы хотят войны.', 'Отдельные немцы жаждут крови.',
                       'Опрошенные американцы хотят войны.', '30% россиян хотят войны.',
                       'Русские не хотят войны.', 'Украинцы не жаждут крови.'):
            self.assertFalse(self.find(phrase, 'generalization.group_mental_state'), phrase)

    def test_national_essence_is_not_triggered_by_bare_legal_or_historical_terms(self):
        for text in ('Суд рассматривает обвинение в геноциде.', 'Архив содержит документы об оккупации.',
                     'Убийство расследуют следователи.', 'Национальная идея — развитие образования.'):
            self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & NEW_IDS, text)

    def test_immutability_and_collective_pathology_follow_only_nearest_collective(self):
        for country in ('Россия', 'Украина', 'Германия', 'Франция'):
            self.assertTrue(self.find(country + ' никогда не сможет измениться.', TARGETS['collective_immutable']))
            self.assertTrue(self.find(country + ' обсуждается в статье. Она якобы страдает манией величия.', TARGETS['collective_pathology']))
        for text in ('Губернатор выступил. Пациентка никогда не сможет измениться.',
                     'Российская пациентка никогда не сможет измениться.',
                     'Украинский пациент страдает манией величия.',
                     'Россия обсуждается в статье. Пациентка пришла на приём. Она страдает манией величия.',
                     'Россия обсуждается в статье. Анна плачет. Она никогда не сможет измениться.'):
            self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & {
                TARGETS['collective_immutable'], TARGETS['collective_pathology']}, text)

    def test_clinical_insult_needs_a_public_person_and_excludes_clinical_reporting(self):
        self.assertTrue(self.find('Президента назвали взбалмошным дементником.', 'enemy.political_madness'))
        for text in ('Врач рассказал о пациенте с манией величия.',
                     'Врач поставил президенту диагноз и описал манию величия.',
                     'У пациентки в больнице началась сильная истерика.',
                     'Сосед назвал пожилого человека дементником.'):
            self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & {
                'enemy.political_madness', TARGETS['collective_pathology']}, text)

    def test_literal_bleating_is_not_an_enemy_image_despite_nearby_official(self):
        self.assertTrue(self.find('Министр заторможенно блеет на саммите.', 'enemy.derisive_communication'))
        self.assertTrue(self.find('Министр блеет, как овца.', 'enemy.derisive_communication'))
        for text in ('Министр посетил ферму, где овцы блеют.', 'Президент слушал, как козы громко блеют.',
                     'Губернатор увидел блеющих ягнят.', 'Овцы рядом с министром блеют.'):
            self.assertFalse(self.find(text, 'enemy.derisive_communication'), text)

    def test_technical_secondary_cultures_and_literal_hooks_are_not_public_labels(self):
        for text in ('В институте изучают вторичную культуру клеток.',
                     'Министр посетил лабораторию, где растёт вторичная культура бактерий.',
                     'На русском крючке держалась рыба, которую поймал президент.',
                     'В гардеробе президента пальто висит на чужом крючке.'):
            self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & NEW_IDS, text)

    def test_fictional_characters_are_not_political_targets_from_article_title(self):
        for text in ('В романе отсталой страной правят волшебники.',
                     'Персонаж фильма никогда не сможет измениться.',
                     'В сериале президент оказался на китайском крючке.',
                     'Герою фильма приписана жажда разрушения цивилизации.'):
            result = analyze({'title': 'Заявление президента России', 'text': text})
            self.assertFalse({f['rule_id'] for f in result['findings']} & NEW_IDS, text)

    def test_attribution_and_metalinguistic_discussion_preserve_status(self):
        for key, rule in TARGETS.items():
            text = DOCUMENTS[key]['text']
            f = self.find('Редактор заявил: «' + text + '»', rule)[0]
            self.assertEqual(f['status'], 'quoted_candidate', key)
            f = self.find('Фраза «' + text + '»', rule)[0]
            self.assertEqual(f['status'], 'context_only', key)
            f = self.find('Неверно утверждать, что ' + text.lower(), rule)[0]
            self.assertEqual(f['status'], 'context_only', key)

    def test_denial_stops_at_contrast_or_separate_proposition(self):
        for prefix in ('Неверно утверждать, что бюджет уменьшился, но ',
                       'Неверно утверждать, что бюджет уменьшился; ',
                       'Неверно утверждать, что бюджет уменьшился. '):
            f = self.find(prefix + 'Россия никогда не сможет измениться.', TARGETS['collective_immutable'])[0]
            self.assertNotEqual(f['status'], 'context_only')
            self.assertFalse(f['evidence'][0]['context']['nearby_negation'])

    def test_publisher_name_url_and_date_do_not_determine_findings(self):
        for doc in DOCUMENTS.values():
            expected = analyze(doc)['findings']
            for source in ('RT', 'Радио Свобода', 'Медиазона', 'Неизвестный автор'):
                self.assertEqual(analyze({**doc, 'source': source, 'url': 'https://example.org/post',
                                          'published_at': '2026-10-30T00:00:00+03:00'})['findings'], expected)

    def test_large_input_and_findings_remain_bounded(self):
        result = analyze({'text': (DOCUMENTS['collective_immutable']['text'] + '\n') * 600})
        self.assertEqual(len(result['findings']), MAX_FINDINGS)
        self.assertTrue(result['summary']['findings_truncated'])
        self.assertFalse(self.find(('Почему ' + 'слово ' * 100) * 300, TARGETS['collective_question']))


if __name__ == '__main__':
    unittest.main()
