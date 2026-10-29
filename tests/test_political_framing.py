"""Political vocabulary: distinctions, literal controls, voices and exact spans."""
import json
import unittest

from media_strazh.analysis import MAX_FINDINGS, VERSION, analyze
from media_strazh.rules import RULES


DOCUMENTS = {
    'denazification': {'text': 'В заявлении говорится о денацификации страны.'},
    'demilitarization': {'text': 'Стороны обсуждают демилитаризацию территории.'},
    'anti_russian': {'text': 'Министр назвал меры антироссийскими.'},
    'liberal_actor': {'text': 'Либералы представили программу реформ.'},
    'political_persecution': {'text': 'В докладе описаны политические преследования.'},
    'repression': {'text': 'Историк изучает репрессии против граждан.'},
    'oppression': {'text': 'В публикации говорится об угнетении женщин.'},
    'ideological_slur': {'text': 'Эти грантоеды поддержали решение.'},
    'bought_voice': {'text': 'Это продажный журналист.'},
    'double_standards': {'text': 'Политик обвинил оппонентов в двойных стандартах.'},
    'betrayal_label': {'text': 'Этот депутат — предатель.'},
}
TARGETS = {key: ('dysphemism.' if key in {'ideological_slur', 'bought_voice'} else
                 'context.' if key == 'double_standards' else
                 'enemy.' if key == 'betrayal_label' else 'terminology.') + key
           for key in DOCUMENTS}
NEW_IDS = set(TARGETS.values())
RHETORIC = {'dysphemism.ideological_slur', 'dysphemism.bought_voice', 'enemy.betrayal_label'}


class PoliticalFramingTests(unittest.TestCase):
    def find(self, text, rule):
        return [f for f in analyze({'text': text})['findings'] if f['rule_id'] == rule]

    def test_all_eleven_rules_have_nonempty_examples_and_questions(self):
        self.assertEqual(len(NEW_IDS), 11)
        self.assertTrue(NEW_IDS <= {r.id for r in RULES})
        for key, doc in DOCUMENTS.items():
            hits = self.find(doc['text'], TARGETS[key])
            self.assertEqual(len(hits), 1, key)
            self.assertTrue(hits[0]['explanation'] and hits[0]['review_question'])

    def test_title_and_body_preserve_unicode_spans_json_and_unit_weight(self):
        for key, doc in DOCUMENTS.items():
            for field in ('title', 'text'):
                document = {'text': 'Опубликован документ.', field: '📰 ' + doc['text']}
                result = analyze(document)
                hits = [f for f in result['findings'] if f['rule_id'] == TARGETS[key]]
                self.assertEqual(len(hits), 1, (key, field))
                self.assertEqual(result['algorithm_version'], VERSION)
                self.assertEqual(hits[0]['rating_weight'], 1)
                for e in hits[0]['evidence']:
                    self.assertEqual(document[e['field']][e['start']:e['end']], e['quote'])
                    s = e['sentence']
                    self.assertEqual(document[e['field']][s['start']:s['end']], s['text'])
                json.loads(json.dumps(result, ensure_ascii=False))

    def test_terms_are_informational_and_slurs_are_candidates(self):
        for key, doc in DOCUMENTS.items():
            f = self.find(doc['text'], TARGETS[key])[0]
            self.assertEqual(f['status'], 'needs_review' if f['rule_id'] in RHETORIC else 'context_only')
            self.assertEqual(bool(f['evidence'][0]['context'].get('informational_notice')), f['rule_id'] not in RHETORIC)

    def test_quoted_or_discussed_words_do_not_imply_editorial_endorsement(self):
        for key, doc in DOCUMENTS.items():
            rule = TARGETS[key]
            quoted = self.find('Редактор заявил: «' + doc['text'] + '»', rule)[0]
            self.assertTrue(quoted['evidence'][0]['context']['in_quotes'])
            self.assertEqual(quoted['status'], 'quoted_candidate' if rule in RHETORIC else 'context_only')
            discussed = self.find('Фраза «' + doc['text'] + '»', rule)[0]
            self.assertEqual(discussed['status'], 'context_only')

    def test_unquoted_reported_accusations_keep_attribution(self):
        for text, key in [('Депутата назвали предателем.', 'betrayal_label'),
                          ('Оппонентов назвали грантоедами.', 'ideological_slur')]:
            f = self.find(text, TARGETS[key])[0]
            self.assertEqual(f['status'], 'quoted_candidate')
            self.assertTrue(f['evidence'][0]['context']['reported_speech'])

    def test_mission_names_cases_and_related_verbs(self):
        cases = {
            'denazification': ['денацификация', 'денацификации', 'денацификацию', 'денацификацией', 'денацификациях', 'денацифицировать', 'денацифицированный'],
            'demilitarization': ['демилитаризация', 'демилитаризации', 'демилитаризацию', 'демилитаризацией', 'демилитаризациях', 'демилитаризовать', 'демилитаризованная'],
        }
        for key, forms in cases.items():
            for term in forms:
                self.assertTrue(self.find('Обсуждается ' + term + ' территории.', TARGETS[key]), (key, term))

    def test_anti_russian_forms_and_hyphenated_spelling(self):
        for term in ('антироссийский', 'антироссийская', 'антироссийские', 'антироссийскими',
                     'АНТИРОССИЙСКУЮ', 'антироссийского', 'антироссийски', 'анти-российские', 'анти‑российской'):
            self.assertTrue(self.find('В тексте есть характеристика: ' + term + '.', TARGETS['anti_russian']), term)

    def test_liberal_is_not_automatically_a_slur(self):
        for term in ('либерал', 'либерала', 'либералы', 'либералам', 'либералами', 'либералка',
                     'либералок', 'неолиберал', 'неолибералов'):
            result = analyze({'text': term + ' участвует в выборах.'})
            hits = [f for f in result['findings'] if f['rule_id'] == TARGETS['liberal_actor']]
            self.assertEqual(len(hits), 1, term)
            self.assertEqual(hits[0]['category'], 'actor_terminology')
            self.assertEqual(hits[0]['status'], 'context_only')
            self.assertEqual(result['summary']['candidate_fragments'], 0)

    def test_traitor_forms_and_explicit_negation(self):
        for term in ('предатель', 'предателя', 'предателю', 'предателем', 'предателях',
                     'предатели', 'предательница', 'предательницами', 'предательниц'):
            self.assertTrue(self.find('Его назвали: ' + term + '.', TARGETS['betrayal_label']), term)
        f = self.find('Он не предатель.', TARGETS['betrayal_label'])[0]
        self.assertEqual(f['status'], 'context_only')
        self.assertTrue(f['evidence'][0]['context']['nearby_negation'])

    def test_existing_complex_accusation_takes_priority_over_general_traitor_noun(self):
        result = analyze({'text': 'Он дружит с противником, значит он тоже предатель.'})
        ids = {f['rule_id'] for f in result['findings']}
        self.assertIn('enemy.guilt_by_association', ids)
        self.assertNotIn(TARGETS['betrayal_label'], ids)
        result = analyze({'text': 'Политических оппонентов назвали национал-предателями.'})
        self.assertIn('enemy.traitor_label', {f['rule_id'] for f in result['findings']})
        self.assertNotIn(TARGETS['betrayal_label'], {f['rule_id'] for f in result['findings']})

    def test_rights_phrases_cover_cases_and_related_formulations(self):
        for phrase in ('политические преследования', 'политическим преследованиям', 'политической расправой',
                       'преследование по политическим мотивам', 'гонения по политическим причинам',
                       'преследования за убеждения', 'расправа за политические взгляды', 'подавление инакомыслия'):
            self.assertTrue(self.find('В заявлении говорится: ' + phrase + '.', TARGETS['political_persecution']), phrase)
        for phrase in ('репрессии', 'репрессий', 'репрессиями', 'репрессивные законы', 'репрессивном режиме'):
            self.assertTrue(self.find('Историк обсуждает ' + phrase + '.', TARGETS['repression']), phrase)
        for phrase in ('угнетение', 'угнетения', 'угнетению', 'угнетением', 'угнетений'):
            self.assertTrue(self.find('В публикации обсуждается ' + phrase + ' граждан.', TARGETS['oppression']), phrase)

    def test_documented_history_and_treaty_terms_remain_notices_not_lies(self):
        for text, key in [('Архив подтверждает репрессии 1937 года.', 'repression'),
                          ('Денацификация Германии после 1945 года описана в учебнике.', 'denazification'),
                          ('Договор установил демилитаризованную зону между странами.', 'demilitarization'),
                          ('Суд признал политические преследования заявителя.', 'political_persecution')]:
            f = self.find(text, TARGETS[key])[0]
            self.assertEqual(f['status'], 'context_only')
            self.assertTrue(f['evidence'][0]['context']['informational_notice'])

    def test_genetic_repression_is_excluded_even_with_political_title(self):
        for text in ('Репрессия генов снижает синтез белка.', 'Репрессия экспрессии генов изучается в лаборатории.',
                     'Обнаружена транскрипционная репрессия.', 'Репрессия транскрипции зависит от белка.',
                     'Репрессия белков изучена в лаборатории.'):
            result = analyze({'title': 'Президент посетил лабораторию', 'text': text})
            self.assertNotIn(TARGETS['repression'], {f['rule_id'] for f in result['findings']}, text)

    def test_medical_and_plant_oppression_is_excluded_with_public_actors(self):
        for text in ('У политика наблюдали угнетение дыхания.', 'Препарат вызывает угнетение сознания.',
                     'Врач сообщил об угнетении ЦНС.', 'Врач описал состояние угнетения.',
                     'Угнетение центральной нервной системы опасно.', 'Угнетение иммунитета связано с лекарством.',
                     'Угнетение роста растений вызвано холодом.', 'Угнетение растений связано с засухой.'):
            result = analyze({'title': 'Заявление министра', 'text': text})
            self.assertNotIn(TARGETS['oppression'], {f['rule_id'] for f in result['findings']}, text)
        self.assertTrue(self.find('Врач рассказал об угнетении женщин.', TARGETS['oppression']))
        self.assertTrue(self.find('Репрессии против врачей подтверждены документами.', TARGETS['repression']))

    def test_computer_dmz_and_literal_standards_are_excluded(self):
        for text in ('Демилитаризованная зона DMZ защищает сервер.', 'Сервер находится в демилитаризованной зоне.',
                     'Проводится демилитаризация локальной сети.'):
            self.assertFalse(self.find(text, TARGETS['demilitarization']), text)
        for text in ('Демилитаризация Украины обсуждалась в документе, который разместили на сервере.',
                     'На сервере опубликован доклад о демилитаризации территории.'):
            self.assertTrue(self.find(text, TARGETS['demilitarization']), text)
        for text in ('Описаны двойные стандарты напряжения.', 'Используются двойные стандарты кодировки.'):
            self.assertFalse(self.find(text, TARGETS['double_standards']), text)

    def test_proper_work_titles_and_fictional_labels_are_excluded(self):
        for text in ('Газета «Либерал» вышла в печать.', 'Фильм «Предатель» показали на фестивале.',
                     'Программа «Кремлебот» получила обновление.',
                     'Книга «Репрессии» поступила в продажу.', 'Роман «Грантоеды» переведён.',
                     'Герой романа о президенте оказался предателем.', 'Персонаж фильма назвал журналиста грантоедом.',
                     'По сюжету министра назвали предателем.', 'Игрок настольной игры оказался предателем.',
                     'Актёр в фильме сыграл предателя.'):
            self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & NEW_IDS, text)
        self.assertTrue(self.find('Актёр назвал депутата предателем.', TARGETS['betrayal_label']))
        self.assertTrue(self.find('Актёр, сыгравший героя фильма, назвал депутата предателем.', TARGETS['betrayal_label']))

    def test_added_ideological_slurs_and_paid_voice_phrases(self):
        for term in ('грантоед', 'грантоедами', 'грантоедка', 'грантоедок', 'либераст', 'либерастов',
                     'либерастками', 'кремлебот', 'кремлеботов', 'кремлеботами', 'кремлеботка',
                     'соросята', 'соросят', 'соросятами', 'соросёнок', 'соросенком'):
            self.assertTrue(self.find('В споре прозвучало слово ' + term + '.', TARGETS['ideological_slur']), term)
        for phrase in ('продажный журналист', 'продажные СМИ', 'продажной прессой', 'проплаченный эксперт',
                       'проплаченные блогеры', 'продажные российские издания'):
            self.assertTrue(self.find('В споре использовали фразу ' + phrase + '.', TARGETS['bought_voice']), phrase)

    def test_ordinary_funding_and_unrelated_substrings_do_not_create_new_slurs(self):
        for text in ('Журналист получил грант на исследование.', 'Услуги эксперта оплачены по договору.',
                     'Обсуждается либерализация экономики.', 'Принято либеральное решение.',
                     'Дверь предательски скрипнула.', 'Началось уголовное преследование по делу о краже.'):
            self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & NEW_IDS, text)

    def test_rule_decisions_do_not_use_publisher_url_or_date(self):
        for doc in DOCUMENTS.values():
            expected = analyze(doc)['findings']
            for source in ('RT', 'Медиазона', 'ИноСМИ', 'Неизвестное издание'):
                self.assertEqual(analyze({**doc, 'source': source, 'url': 'https://example.org/news',
                                          'published_at': '2026-10-29T12:00:00+03:00'})['findings'], expected)

    def test_existing_budget_limits_repeated_terms(self):
        result = analyze({'text': (DOCUMENTS['repression']['text'] + '\n') * 600})
        self.assertEqual(len(result['findings']), MAX_FINDINGS)
        self.assertTrue(result['summary']['findings_truncated'])


if __name__ == '__main__':
    unittest.main()
