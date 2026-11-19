"""Four PRO tabs, real-data rendering contracts and retired public routes."""
from pathlib import Path
import json

def pro_ui(browser,base,site):
    for width in (375,720,1280):
        context=browser.new_context(viewport={'width':width,'height':900},has_touch=width<721,is_mobile=width<721)
        page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base+'/analysis/')
        tabs=page.locator('.analysis-tabs [data-mode]')
        assert tabs.all_text_contents()==['Один сюжет — по-разному','История правок','Автоматический анализ','Самостоятельная проверка']
        boxes=[tabs.nth(i).bounding_box() for i in range(4)]
        assert (abs(boxes[0]['y']-boxes[3]['y'])<2)==(width>720)
        for mode in ('stories','history','automatic','manual'):
            page.locator('[data-mode='+mode+']').click()
            assert page.locator('#'+mode+'Panel').is_visible()
            assert sum(page.locator('#'+name+'Panel').is_visible() for name in ('stories','history','automatic','manual'))==1
            assert page.locator('[data-mode='+mode+']').get_attribute('aria-selected')=='true'
        page.locator('[data-mode=stories]').click();page.locator('#storiesContent .pro-empty, #storiesContent .pro-story').first.wait_for()
        page.locator('[data-mode=stories]').press('ArrowRight');assert page.locator('#historyPanel').is_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        # Deterministic real-schema fixture, never part of public production data.
        fixture={'schema_version':'pro-evidence-1.0','stories':[{'title':'Закрытие полос моста','items':[{'source':'Редакция','url':'https://tass.ru/test','published_at':'2026-11-19T10:00:00Z','title':'Закроют две полосы','phrases':[{'text':'Закроют','changed':True},{'text':' две полосы','changed':False}]}]}], 'history':[{'source':'Редакция','url':'https://tass.ru/test','versions':[{'before':[{'text':'все полосы','changed':True}],'after':[{'text':'две полосы','changed':True}],'before_at':'2026-11-19T10:00:00Z','after_at':'2026-11-19T11:00:00Z','kind':'title','title':'Закроют две полосы'}]}]}
        page.route('**/data/pro.json',lambda route:route.fulfill(json=fixture))
        page.goto(base+'/analysis/#stories');page.locator('.pro-headline mark').click();assert 'не доказывает манипуляцию' in page.locator('.pro-explanation').inner_text()
        page.locator('[data-mode=history]').click();assert page.locator('.pro-version del').inner_text()=='все полосы';assert page.locator('.pro-version ins').inner_text()=='две полосы';assert 'МСК' in page.locator('.pro-revision').inner_text()
        page.select_option('#historyKind','text');assert page.locator('#historyContent .pro-empty').is_visible()
        for url in ('/','/help/','/about/'):
            page.goto(base+url);assert page.locator('a[href*="business"]').count()==0;assert 'Бизнес' not in page.locator('body').inner_text()
            page.locator('a.pro-nav-link').click()
            assert page.locator('.pro-gateway-option').count()==1
            assert page.locator('.pro-gateway-option--research').get_attribute('href')=='/analysis/'
            page.locator('.pro-gateway-close').click()
        assert not errors,errors
        context.close()
    assert not (site/'business.html').exists() and not (site/'business/index.html').exists()
    print('Four PRO tabs, responsive layout, data, diffs, filters, navigation and removed routes passed')
