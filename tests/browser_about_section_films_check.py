"""Supplied principles/creator films: frame fitting, playback and real 3D fallback."""
from pathlib import Path


def section_films_ui(browser, base):
    output = Path('/tmp/about-section-films-checks')
    output.mkdir(exist_ok=True)
    for width in (320, 390, 768, 1280, 1920):
        context = browser.new_context(viewport={'width': width, 'height': 1000},
                                      is_mobile=width < 681, has_touch=width < 681)
        errors = []
        try:
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.clock.install()
            page.goto(base + '/about/')
            for name, capital, moments in (
                ('principles', 'Principles', (4.5, 8.9, 13.1, 17.4, 21.5, 24.5)),
                ('creator', 'Creator', (8, 13.5)),
            ):
                iframe_id = 'about' + capital + 'FilmFrame'
                movie = page.frame_locator('#' + iframe_id)
                stage = movie.locator('#stage')
                stage.wait_for(state='attached')
                state = lambda: stage.evaluate('()=>window.mediaFilm.state()')

                def wait_running(value):
                    page.wait_for_function(
                        'p=>document.getElementById(p.id).contentWindow.mediaFilm.state().running===p.value',
                        arg={'id': iframe_id, 'value': value})

                assert not state()['running']
                page.locator('[data-about-channel=' + name + ']').click()
                wait_running(True)
                assert movie.locator('#ctl').is_hidden()
                assert stage.evaluate('el=>{const r=el.getBoundingClientRect();return Math.abs(r.x)<1&&Math.abs(r.y)<1&&Math.abs(r.width-innerWidth)<1&&Math.abs(r.height-innerHeight)<1}')
                assert page.locator('#' + iframe_id).evaluate('el=>{const r=el.getBoundingClientRect(),p=el.parentElement.getBoundingClientRect();return Math.abs(r.width-p.width)<1&&Math.abs(r.height-p.height)<1}')
                page.locator('#about' + capital + 'Pause').click()
                wait_running(False)
                paused = state()['time']
                page.clock.run_for(500)
                assert state()['time'] == paused
                page.locator('#about' + capital + 'Pause').click()
                wait_running(True)
                page.locator('#about' + capital + 'Speed').click()
                page.wait_for_function('id=>document.getElementById(id).contentWindow.mediaFilm.state().speed===1.5', arg=iframe_id)
                page.locator('#about' + capital + 'Replay').click()
                page.wait_for_function('id=>document.getElementById(id).contentWindow.mediaFilm.state().time<.5', arg=iframe_id)
                for moment in moments:
                    page.clock.run_for(round(max(0, moment - state()['time']) * 1000 / 1.5))
                    # Freeze the sampled frame while inspecting/saving it. Clock
                    # install still lets real time pass between driver calls.
                    stage.evaluate('()=>window.mediaFilm.pause()')
                    sampled = state()
                    assert abs(sampled['time'] - moment) < .35, (width, name, sampled)
                    stage.evaluate('el=>el.getAnimations({subtree:true}).forEach(a=>{if(Number.isFinite(a.effect.getComputedTiming().endTime))a.finish()})')
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    assert stage.evaluate('()=>document.documentElement.scrollWidth<=innerWidth+1')
                    if moment == moments[-1]:
                        assert movie.locator('#frame').evaluate('el=>getComputedStyle(el).visibility') == 'hidden'
                        assert movie.locator('.end .logo').evaluate('el=>getComputedStyle(el).opacity') == '1'
                    else:
                        # Visible copy, illustration and biography fit above playback controls.
                        selectors = '.lbl,.ttl,.cap,.sc.on' if name == 'principles' else '.lbl,.creator-layout,.nm,.rl,.ch'
                        bounds = movie.locator(selectors).evaluate_all('els=>els.map(el=>{const r=el.getBoundingClientRect();return {top:r.top,bottom:innerHeight-58-r.bottom,left:r.left,right:innerWidth-r.right}})')
                        assert all(min(rect.values()) >= -1 for rect in bounds), (width, name, moment, bounds)
                        if name == 'principles':
                            assert movie.locator('.sc.on').count() == 1
                            art = movie.locator('.sc.on').evaluate('el=>{const p=el.getBoundingClientRect();return [...el.querySelectorAll(".mk b,.cd,.ap,.dial,.ind")].map(c=>{const r=c.getBoundingClientRect();return Math.min(r.top-p.top,p.bottom-r.bottom,r.left-p.left,p.right-r.right)})}')
                            assert all(value >= -1 for value in art), (width, moment, art)
                        else:
                            model = movie.locator('#authorMeshCanvas')
                            assert model.get_attribute('data-model-kind') == '3d-mesh'
                            assert int(model.get_attribute('data-vertices')) > 10000
                            assert model.get_attribute('data-renderer') in ('webgl', 'software-3d')
                            assert model.evaluate('el=>el.width>50&&el.height>50')
                            assert movie.locator('.ch a').evaluate_all('els=>els.map(el=>el.getAttribute("href"))') == ['https://t.me/iznankamedia', 'mailto:artem_shmakow@vk.com']
                    if width in (390, 1280):
                        page.screenshot(path=str(output / f'{name}-{moment}-{width}.png'), animations='disabled')
                    stage.evaluate('()=>window.mediaFilm.resume()')

                # User intent is preserved when switching browser visibility.
                page.locator('#about' + capital + 'Replay').click()
                wait_running(True)
                page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))")
                wait_running(False)
                page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'))")
                wait_running(True)
                page.locator('#about' + capital + 'Pause').click()
                wait_running(False)
                page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'))")
                page.clock.run_for(300)
                assert not state()['running']
                # An unrelated window cannot issue a control message.
                stage.evaluate("name=>dispatchEvent(new MessageEvent('message',{origin:location.origin,source:window,data:{type:'media-strazh-'+name+'-control',action:'resume'}}))", name)
                assert not state()['running']
                page.locator('[data-about-channel=' + name + ']').click()
                page.clock.run_for(300)
                assert not state()['running']
            assert not errors, errors
        finally:
            context.close()

    # Static posters still communicate useful content with reduced motion.
    context = browser.new_context(viewport={'width': 390, 'height': 900}, reduced_motion='reduce')
    try:
        page = context.new_page()
        page.goto(base + '/about/')
        for name, capital, poster in (('principles', 'Principles', 21.5), ('creator', 'Creator', 8)):
            page.locator('[data-about-channel=' + name + ']').click()
            iframe_id = 'about' + capital + 'FilmFrame'
            page.wait_for_function('p=>{const s=document.getElementById(p.id).contentWindow.mediaFilm?.state();return s&&!s.running&&s.time===p.poster}', arg={'id': iframe_id, 'poster': poster})
            frame = page.frame_locator('#' + iframe_id)
            assert frame.locator('#frame').evaluate('el=>!el.classList.contains("off")')
            page.locator('#about' + capital + 'Replay').click()
            page.wait_for_function('id=>document.getElementById(id).contentWindow.mediaFilm.state().running', arg=iframe_id)
            frame.locator('#stage').press('Escape')
            page.wait_for_function("document.querySelector('#aboutMonitorScreen').dataset.activeChannel==='intro'")
            assert page.locator('[data-about-channel=' + name + ']').evaluate('el=>el===document.activeElement')
    finally:
        context.close()

    # Hardware-independent rendering: both paths project and shade real geometry.
    for software in (False, True):
        context = browser.new_context(viewport={'width': 390, 'height': 600}, reduced_motion='reduce')
        try:
            if software:
                context.add_init_script("const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(kind,...args){return kind.includes('webgl')?null:original.call(this,kind,...args)}")
            page = context.new_page()
            page.goto(base + '/about-creator-film.html')
            model = page.locator('#authorMeshCanvas')
            if software:
                assert model.get_attribute('data-renderer') == 'software-3d'
            pictures = []
            for time in (0, 4):
                pixels = model.evaluate('''(el,time)=>{window.authorBust3D.render(time);
                    if(el.dataset.renderer==='webgl'){
                        const gl=el.getContext('webgl'),data=new Uint8Array(el.width*el.height*4);
                        gl.readPixels(0,0,el.width,el.height,gl.RGBA,gl.UNSIGNED_BYTE,data);
                        return Array.from(data);
                    }
                    return Array.from(el.getContext('2d').getImageData(0,0,el.width,el.height).data);
                }''', time)
                assert sum(value > 0 for value in pixels[3::4]) > 1000
                pictures.append(pixels)
            assert pictures[0] != pictures[1], 'The 3D mesh must turn, not repeat a static silhouette'
        finally:
            context.close()
    print('Principles/creator films: five scenes, biography, full-frame mobile/desktop layout, controls, lifecycle, reduced motion, WebGL and software 3D passed', flush=True)


if __name__ == '__main__':
    import argparse
    import functools
    import http.server
    import shutil
    import threading
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', required=True, type=Path)
    args = parser.parse_args()
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(args.site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium') or None, args=['--no-sandbox'])
            section_films_ui(browser, f'http://127.0.0.1:{server.server_port}')
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
