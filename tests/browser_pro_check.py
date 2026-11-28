"""Five PRO tabs, real-data rendering contracts and retired public routes."""
from pathlib import Path
import json

def pro_ui(browser,base,site):
    for width in (320,390,720,1280):
        context=browser.new_context(viewport={'width':width,'height':900},has_touch=width<721,is_mobile=width<721,reduced_motion='reduce')
        page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        assert page.request.get(base+'/business/').status==404
        assert page.request.get(base+'/business.html').status==404
        page.goto(base+'/analysis/')
        assert page.locator('#storiesPanel .section-head').count()==0
        tabs=page.locator('.analysis-tabs [data-mode]')
        assert tabs.all_text_contents()==['Сравнение публикаций','История правок','Автоматический анализ','Самостоятельная проверка','Фото и контекст']
        page.evaluate('document.fonts.ready')
        boxes=tabs.evaluate_all('els=>els.map(el=>({y:el.getBoundingClientRect().y}))')
        assert (abs(boxes[0]['y']-boxes[3]['y'])<2)==(width>720)
        for mode in ('stories','history','automatic','manual','photo'):
            page.locator('[data-mode='+mode+']').click()
            assert page.locator('#'+mode+'Panel').is_visible()
            assert sum(page.locator('#'+name+'Panel').is_visible() for name in ('stories','history','automatic','manual','photo'))==1
            assert page.locator('[data-mode='+mode+']').get_attribute('aria-selected')=='true'
        page.locator('[data-mode=stories]').click();page.locator('#storiesContent .pro-empty, #storiesContent .pro-story').first.wait_for()
        page.locator('[data-mode=stories]').press('ArrowRight');assert page.locator('#historyPanel').is_visible()
        page.locator('[data-mode=history]').press('End');assert page.locator('#photoPanel').is_visible()
        page.locator('[data-mode=photo]').press('ArrowRight');assert page.locator('#storiesPanel').is_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        # Deterministic real-schema fixture, never part of public production data.
        items=[]
        for number in range(4):
            title=f'Редакция {number}: закроют две полосы'
            body=f'Полный текст {number}.\nЗакроют две полосы. '+('Длинный абзац. '*150)+'Конец сохранённой публикации. <script>не HTML</script>'
            items.append({'source':f'Редакция {number}','url':f'https://tass.ru/test/{number}',
                          'published_at':'2026-11-19T10:00:00Z','title':title,
                          'phrases':[{'text':f'Редакция {number}: ','changed':False},{'text':'закроют','changed':True},{'text':' две полосы','changed':False}],
                          'text':body,'text_phrases':[{'text':f'Полный текст {number}.\n','changed':False},{'text':'Закроют','changed':True},{'text':body.split('Закроют',1)[1],'changed':False}]})
        # Simulate an older snapshot that has no body yet for one publication.
        items[-1].pop('text');items[-1].pop('text_phrases')
        fixture={'schema_version':'pro-evidence-1.0','stories':[
            {'topic':'Права и свободы','title':'Общий заголовок сюжета','items':items},
            {'topic':'Международные переговоры','title':'Другой сюжет','items':items[:2]}],
            'history':[{'source':'Редакция','url':'https://tass.ru/test','versions':[{'before':[{'text':'все полосы','changed':True}],'after':[{'text':'две полосы','changed':True}],'before_at':'2026-11-19T10:00:00Z','after_at':'2026-11-19T11:00:00Z','kind':'title','title':'Закроют две полосы'}]}]}
        page.route('**/data/pro.json',lambda route:route.fulfill(json=fixture))
        page.goto(base+'/analysis/#stories');page.reload()
        page.locator('.pro-story').first.wait_for()
        trigger=lambda locator:locator.tap() if width<=720 else locator.click()
        first=page.locator('.pro-story').first
        assert first.locator('.pro-headline').count()==3
        assert first.locator('.pro-show-all').count()==1
        assert page.locator('.pro-story').nth(1).locator('.pro-headline').count()==2
        assert page.locator('.pro-story').nth(1).locator('.pro-show-all').count()==0
        assert first.locator('.pro-story-count').inner_text()=='4 публикации'
        heading=first.locator('.pro-story-heading')
        assert heading.evaluate('el=>{const size=parseFloat(getComputedStyle(el.querySelector("h3")).fontSize);return size>=16&&size<=21}')
        assert first.evaluate('el=>parseFloat(getComputedStyle(el).marginBottom)>=20')
        cards=first.locator('.pro-headline').evaluate_all('els=>els.map(el=>el.getBoundingClientRect().y)')
        assert (max(cards)-min(cards)<2)==(width>720)
        output=Path('/tmp/pro-layout-checks');output.mkdir(exist_ok=True)
        if width in (390,1280):page.screenshot(path=str(output/f'comparisons-{width}.png'),full_page=True)
        trigger(first.locator('.pro-publication-more').first)
        detail=page.locator('#proPublicationModal')
        detail.wait_for(state='visible')
        assert detail.locator('.pro-publication-text').inner_text()==items[0]['text']
        assert detail.locator('script').count()==0
        assert detail.locator('.pro-publication-text mark').inner_text()=='Закроют'
        trigger(detail.locator('.pro-publication-text mark'))
        assert 'не доказывает манипуляцию' in detail.locator('.pro-explanation').inner_text()
        assert detail.locator('a').get_attribute('href')==items[0]['url']
        assert detail.evaluate('el=>el.scrollWidth<=el.clientWidth+1')
        assert page.evaluate('document.body.style.overflow')=='hidden'
        if width in (390,1280):page.screenshot(path=str(output/f'publication-{width}.png'))
        page.keyboard.press('Escape');detail.wait_for(state='hidden')
        trigger(first.locator('.pro-show-all'))
        all_dialog=page.locator('#proStoryModal');all_dialog.wait_for(state='visible')
        assert all_dialog.locator('.pro-headline').count()==4
        assert all_dialog.evaluate('el=>el.scrollWidth<=el.clientWidth+1')
        if width in (390,1280):page.screenshot(path=str(output/f'all-publications-{width}.png'))
        trigger(all_dialog.locator('.pro-publication-more').nth(3))
        detail.wait_for(state='visible')
        assert 'пока не сохранён' in detail.locator('.pro-empty').inner_text()
        # Native focus trapping includes both Tab directions and nested Escape.
        detail.locator('.pro-dialog-close').focus();page.keyboard.press('Shift+Tab')
        assert detail.locator('a').evaluate('el=>el===document.activeElement'),page.evaluate('document.activeElement.outerHTML')
        page.keyboard.press('Tab');assert detail.locator('.pro-dialog-close').evaluate('el=>el===document.activeElement')
        trigger(detail.locator('.pro-dialog-close'));detail.wait_for(state='hidden')
        assert all_dialog.is_visible()
        assert page.evaluate('document.body.style.overflow')=='hidden'
        page.keyboard.press('Escape');all_dialog.wait_for(state='hidden')
        assert page.evaluate('document.body.style.overflow')==''
        assert first.locator('.pro-show-all').evaluate('el=>el===document.activeElement')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert page.locator('#historyPanel .section-head').count()==0
        page.locator('[data-mode=history]').click();assert page.locator('.pro-version del').inner_text()=='все полосы';assert page.locator('.pro-version ins').inner_text()=='две полосы';assert 'МСК' in page.locator('.pro-revision').inner_text()
        actions=page.locator('.pro-revision .pro-source-actions')
        assert actions.evaluate("el=>{const s=getComputedStyle(el),a=el.querySelector('a').getBoundingClientRect(),r=el.getBoundingClientRect();return s.justifyContent==='flex-end'&&parseFloat(s.paddingTop)>=20&&Math.abs(a.right-r.right)<2}")
        if width in (390,1280):page.screenshot(path=str(output/f'history-{width}.png'),full_page=True)
        page.select_option('#historyKind','text');assert page.locator('#historyContent .pro-empty').is_visible()
        for url in ('/','/help/','/about/'):
            page.goto(base+url);assert page.locator('a[href*="business"]').count()==0;assert 'Бизнес' not in page.locator('body').inner_text()
            if not page.locator('a.pro-nav-link').is_visible():page.locator('#burgerBtn').click()
            page.locator('a.pro-nav-link').click()
            page.wait_for_url('**/analysis/')
            assert page.locator('.pro-gateway-dialog').count()==0
            assert page.locator('.analysis-tabs').is_visible()
        assert not errors,errors
        context.close()
    assert not (site/'business.html').exists() and not (site/'business/index.html').exists()
    print('Five PRO tabs, responsive layout, data, diffs, filters, navigation and removed routes passed')
