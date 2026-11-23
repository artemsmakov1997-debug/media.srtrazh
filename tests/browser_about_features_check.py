"""Author-supplied capabilities film: playback, copy, responsive scenes and lifecycle."""
from pathlib import Path


def features_ui(browser, base):
    output=Path('/tmp/about-features-checks');output.mkdir(exist_ok=True)
    for width in (320,390,768,1280):
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
            assert not page.locator('#aboutStageOpportunities .about-audience').count()
            assert movie.locator('.flt').inner_text()=='Все издания\nСайты и Telegram\nВсе маркеры'
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
                else:
                    assert movie.locator('.frame').evaluate('el=>getComputedStyle(el).visibility')=='hidden'
                    assert movie.locator('.end .pro').evaluate('el=>getComputedStyle(el).opacity')=='1'
                if width in (390,1280):
                    page.screenshot(path=str(output/f'features-{name}-{width}.png'),full_page=True,animations='disabled')
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
    finally:context.close()
    print('Capabilities film: four scenes, final logo/PRO, controls, mobile layout, paused hidden channel and reduced motion passed',flush=True)
