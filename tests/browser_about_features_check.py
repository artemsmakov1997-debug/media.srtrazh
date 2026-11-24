"""Author-supplied capabilities film: playback, copy, responsive scenes and lifecycle."""
from pathlib import Path


def features_ui(browser, base):
    output=Path('/tmp/about-features-checks');output.mkdir(exist_ok=True)
    for width in (320,390,768,1280,1920):
        context=browser.new_context(viewport={'width':width,'height':1000},is_mobile=width<681,has_touch=width<681)
        errors=[]
        try:
            page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            page.clock.install()
            page.goto(base+'/about/')
            movie=page.frame_locator('#aboutFeaturesFilmFrame')
            movie.locator('#stage').wait_for(state='attached')
            stage=movie.locator('#stage')
            state=lambda:stage.evaluate('()=>window.mediaFilm.state()')
            def wait_playing(value):
                page.wait_for_function("expected=>document.querySelector('#aboutFeaturesFilmFrame').contentWindow.mediaFilm.state().running===expected",arg=value)
            assert not state()['running']  # Hidden channel does not animate.
            page.locator('[data-about-channel=opportunities]').click()
            wait_playing(True);page.clock.run_for(700)
            assert state()['running']
            stage.evaluate('()=>document.fonts.ready')
            assert not page.locator('#aboutStageOpportunities .about-audience').count()
            assert movie.locator('.flt').count()==0
            for removed in ('Все издания','Сайты и Telegram','Все маркеры'):
                assert removed not in movie.locator('body').inner_text()
            assert stage.evaluate('el=>{const r=el.getBoundingClientRect();return Math.abs(r.left)<1&&Math.abs(r.top)<1&&Math.abs(r.width-innerWidth)<1&&Math.abs(r.height-innerHeight)<1}')
            assert page.locator('#aboutFeaturesFilmFrame').evaluate('el=>{const r=el.getBoundingClientRect(),p=el.parentElement.getBoundingClientRect();return Math.abs(r.width-p.width)<1&&Math.abs(r.height-p.height)<1&&Math.abs(r.left-p.left)<1&&Math.abs(r.top-p.top)<1}')
            assert movie.locator('.end .pro').evaluate('el=>parseFloat(getComputedStyle(el).fontSize)<=42')
            assert movie.locator('#ctl').is_hidden()
            assert movie.locator('.end').inner_text()=='МЕДИА.СТРАЖ\nPRO'
            page.locator('#aboutFeaturesPause').click();wait_playing(False);page.clock.run_for(100)
            paused=state()['time'];page.clock.run_for(1000)
            assert not state()['running'] and abs(state()['time']-paused)<.01
            page.locator('#aboutFeaturesPause').click();wait_playing(True);page.clock.run_for(200)
            assert state()['running'] and state()['time']>paused,(width,paused,state())
            page.locator('#aboutFeaturesSpeed').click();page.clock.run_for(100)
            assert state()['speed']==1.5
            page.locator('#aboutFeaturesSpeed').click();page.clock.run_for(100)
            assert state()['speed']==2
            page.locator('#aboutFeaturesReplay').click();page.clock.run_for(100)
            assert state()['time']<.4
            for moment,name in ((4.6,'automatic'),(9.3,'comparison'),(14.5,'revisions'),(19.1,'manual'),(23.8,'final')):
                delta=max(0,moment-state()['time'])
                page.clock.run_for(round(delta*1000/2))
                assert abs(state()['time']-moment)<.15,state()
                stage.evaluate('el=>el.getAnimations({subtree:true}).forEach(a=>{if(Number.isFinite(a.effect.getComputedTiming().endTime))a.finish()})')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                assert stage.evaluate('()=>document.documentElement.scrollWidth<=innerWidth+1')
                if name!='final':
                    metrics=movie.locator('.sc.on').evaluate('el=>({height:el.clientHeight,scroll:el.scrollHeight})')
                    assert metrics['scroll']<=metrics['height']+2,(width,name,metrics)
                    bounds=movie.locator('.sc.on').evaluate('el=>{const p=el.parentElement.getBoundingClientRect();return [...el.children].map(c=>{const r=c.getBoundingClientRect();return {top:r.top-p.top,bottom:p.bottom-r.bottom,left:r.left-p.left,right:p.right-r.right}})}')
                    assert all(min(b.values())>=-1 for b in bounds),(width,name,bounds)
                else:
                    assert movie.locator('.frame').evaluate('el=>getComputedStyle(el).visibility')=='hidden'
                    assert movie.locator('.end .pro').evaluate('el=>getComputedStyle(el).opacity')=='1'
                if width in (390,1280,1920):
                    page.screenshot(path=str(output/f'features-{name}-{width}.png'),full_page=True,animations='disabled')
            # Actual clicks/taps must reach the iframe, and restart the chosen scene.
            assert page.locator('#aboutFeaturesFilmFrame').evaluate('el=>getComputedStyle(el).pointerEvents')=='auto'
            page.locator('#aboutFeaturesReplay').click();page.clock.run_for(1000)
            demos=movie.locator('#tabs button')
            assert demos.all_text_contents()==['Сравнение публикаций','История правок','Автоматический анализ','Самостоятельная проверка']
            def wait_demo(mode,start):
                page.wait_for_function("""expected=>{
                    const s=document.querySelector('#aboutFeaturesFilmFrame').contentWindow.mediaFilm.state();
                    return s.selected===expected.mode&&s.running&&s.time>=expected.start&&s.time<expected.start+.75;
                }""",arg={'mode':mode,'start':start})
            def activate_demo(target):
                assert target.is_visible() and target.is_enabled()
                if width<681:
                    target.tap()
                    return
                # FrameLocator's click coordinates ignore the about page's 80%
                # CSS zoom in Chromium. Send a real mouse click at the visual
                # centre, scaling child viewport coordinates into the iframe.
                outer=page.locator('#aboutFeaturesFilmFrame').bounding_box()
                rect=target.evaluate('el=>({r:el.getBoundingClientRect().toJSON(),w:innerWidth,h:innerHeight})')
                x=outer['x']+(rect['r']['x']+rect['r']['width']/2)*outer['width']/rect['w']
                y=outer['y']+(rect['r']['y']+rect['r']['height']/2)*outer['height']/rect['h']
                assert page.evaluate('p=>document.elementFromPoint(p.x,p.y)?.id',{'x':x,'y':y})=='aboutFeaturesFilmFrame'
                page.mouse.click(x,y)
            for mode,start in [('comparison',5.8),('history',10.4),('automatic',1.2),('manual',15)]:
                target=movie.locator(f'button[data-demo={mode}]')
                activate_demo(target)
                wait_demo(mode,start)
                assert target.get_attribute('aria-pressed')=='true'
                assert movie.locator('.sc.on').get_attribute('id')==target.get_attribute('aria-controls')
                assert movie.locator('.sc.on').get_attribute('data-demo')==mode
                page.wait_for_function("document.querySelector('#aboutFeaturesPause').textContent==='Пауза'")
                page.clock.run_for(2400)
                assert state()['finished'] and not state()['running']
                assert abs(state()['time']-(start+4.5-.001))<.01
                assert movie.locator('#frame').get_attribute('class')=='frame'
                page.wait_for_function("document.querySelector('#aboutFeaturesPause').textContent==='Продолжить'")
                end_time=state()['time'];page.clock.run_for(600)
                assert state()['time']==end_time and movie.locator('.sc.on').get_attribute('data-demo')==mode
            # Continue repeats a completed selected scene; a repeated click restarts it.
            page.locator('#aboutFeaturesPause').click();wait_demo('manual',15)
            page.clock.run_for(900)
            activate_demo(movie.locator('button[data-demo=manual]'));wait_demo('manual',15)
            # A system pause must preserve user intent for visibility restoration.
            page.wait_for_function("document.querySelector('#aboutFeaturesPause').textContent==='Пауза'")
            page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))")
            wait_playing(False)
            paused_time=state()['time'];page.clock.run_for(600)
            assert state()['time']==paused_time
            page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'))")
            wait_playing(True)
            assert state()['selected']=='manual'
            # Keyboard activation and directional controls stay inside the player.
            movie.locator('button[data-demo=history]').focus()
            movie.locator('button[data-demo=history]').press('Enter');wait_demo('history',10.4)
            movie.locator('button[data-demo=history]').press('ArrowLeft');wait_demo('comparison',5.8)
            movie.locator('button[data-demo=comparison]').press('End');wait_demo('manual',15)
            movie.locator('button[data-demo=manual]').press('Home');wait_demo('comparison',5.8)
            movie.locator('button[data-demo=automatic]').focus()
            movie.locator('button[data-demo=automatic]').press('Space');wait_demo('automatic',1.2)
            # Escape inside the now-interactive iframe returns to the intro channel.
            movie.locator('button[data-demo=automatic]').press('Escape')
            page.wait_for_function("document.querySelector('#aboutMonitorScreen').dataset.activeChannel==='intro'")
            assert page.locator('[data-about-channel=opportunities]').evaluate('el=>el===document.activeElement')
            page.locator('[data-about-channel=opportunities]').click();wait_playing(True);page.clock.run_for(700)
            assert state()['selected'] is None
            page.locator('[data-about-channel=creator]').click();page.clock.run_for(800)
            paused=state()['time'];page.clock.run_for(800)
            assert not state()['running'] and abs(state()['time']-paused)<.01
            page.locator('[data-about-channel=opportunities]').click();page.clock.run_for(700)
            assert state()['running'] and state()['time']<2
            # A same-origin message from an unrelated frame must not control playback.
            stage.evaluate("()=>dispatchEvent(new MessageEvent('message',{origin:location.origin,source:window,data:{type:'media-strazh-features-control',action:'speed',value:.5}}))")
            assert state()['speed']==2
            assert not errors,errors
        finally:context.close()
    context=browser.new_context(viewport={'width':390,'height':900},reduced_motion='reduce')
    try:
        page=context.new_page();page.goto(base+'/about/')
        page.locator('[data-about-channel=opportunities]').click()
        frame=page.frame_locator('#aboutFeaturesFilmFrame');frame.locator('#stage').wait_for()
        page.wait_for_function("document.querySelector('#aboutFeaturesPause').textContent==='Продолжить'")
        assert not frame.locator('#stage').evaluate('()=>window.mediaFilm.state().running')
        assert frame.locator('.end .pro').evaluate('el=>getComputedStyle(el).opacity')=='1'
        page.locator('#aboutFeaturesReplay').click()
        page.wait_for_function("()=>document.querySelector('#aboutFeaturesFilmFrame').contentWindow.mediaFilm.state().running")
        assert frame.locator('#stage').evaluate('()=>window.mediaFilm.state().running')
        frame.locator('button[data-demo=history]').click()
        page.wait_for_function("()=>document.querySelector('#aboutFeaturesFilmFrame').contentWindow.mediaFilm.state().selected==='history'")
    finally:context.close()
    print('Capabilities film: full-frame geometry, removed filters, smaller PRO, four scenes, clickable selectors, keyboard, scene replay, mobile layout and reduced motion passed',flush=True)


if __name__=='__main__':
    import argparse
    import functools
    import http.server
    import shutil
    import threading
    from playwright.sync_api import sync_playwright
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site',required=True,type=Path)
    args=parser.parse_args()
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(args.site)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
            features_ui(browser,f'http://127.0.0.1:{server.server_port}')
            browser.close()
    finally:server.shutdown();server.server_close()
