"""Retained public-page regressions independent of the removed product."""
def public_ui(browser, base, site):
    context = browser.new_context(viewport={"width":1280,"height":900})
    try:
        page=context.new_page()
        # About: the Russia map runs in an isolated HTML iframe.
        page.goto(base + "/about.html")
        screen = page.locator("#aboutMonitorScreen")
        intro = page.locator("#aboutStageIntro")
        film = page.locator("#aboutFilm")
        movie = page.frame_locator("#aboutFilmFrame")
        assert intro.is_visible()
        assert film.get_attribute("data-film-status") in ("playing", "complete")
        assert movie.locator("#stage .map svg").count() == 1
        assert movie.locator("#dots").count() == 1
        # No 16:9 black side bars: stage must fill the iframe's viewport.
        assert movie.locator("#stage").evaluate(
            "el => Math.abs(el.getBoundingClientRect().width - innerWidth) <= 2")
        assert movie.locator("#stage").evaluate(
            "el => Math.abs(el.getBoundingClientRect().height - innerHeight) <= 2")
        assert movie.locator(".end .logo").inner_text() == "МЕДИА.СТРАЖ"
        assert movie.locator(".ring").count() >= 10
        assert page.locator(".about-stage").count() == 4
        assert page.locator('[data-about-channel]').count() == 3
        assert page.locator(".about-monitor-choices .about-choose").all_inner_texts() == [
            "Принципы", "Возможности", "Создатель"]
        assert page.locator(".about-channel-nav,.about-stage-heading,.about-side").count() == 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
        speed = page.locator("#aboutFilmSpeed")
        replay = page.locator("#aboutFilmReplay")
        assert speed.inner_text() == "Скорость ×1"
        speed.click()
        assert speed.inner_text() == "Скорость ×2"
        speed.click()
        assert speed.inner_text() == "Скорость ×3"
        replay.click()
        assert film.get_attribute("data-film-status") == "playing"
        page.wait_for_function(
            'document.querySelector("#aboutFilm").dataset.filmStatus === "complete"', timeout=11000)
        # Replaying resets all CSS animations, rather than only the label.
        replay.click()
        assert film.get_attribute("data-film-status") == "playing"
        # Restart is deferred over frames, avoiding a synchronous layout flush.
        movie.locator("#stage.go").wait_for()
        assert "void st.offsetWidth" not in (site / "about-map-film.html").read_text(encoding="utf-8")
        assert movie.locator(".ring").count() >= 10
        principles = page.locator('[data-about-channel="principles"]')
        principles.click()
        assert page.locator("#aboutStagePrinciples").is_visible()
        assert principles.inner_text() == "Назад"
        principles_movie = page.frame_locator("#aboutPrinciplesFilmFrame")
        assert principles_movie.locator("#stage").is_visible()
        assert principles_movie.locator(".sc").count() == 5
        assert page.locator("#aboutPrinciplesReplay").is_visible()
        page.wait_for_timeout(550)
        assert page.locator(".about-stage:visible").count() == 1
        opportunities = page.locator('[data-about-channel="opportunities"]')
        opportunities.click()
        assert opportunities.inner_text() == "Назад"
        assert page.locator("#aboutStageOpportunities").is_visible()
        assert page.locator("#aboutStageOpportunities .about-audience, #aboutStageOpportunities .about-stage-shell").count() == 0
        assert page.frame_locator("#aboutFeaturesFilmFrame").locator("#stage").is_visible()
        assert page.locator("#aboutFeaturesReplay").is_visible()
        creator = page.locator('[data-about-channel="creator"]')
        creator.click()
        assert page.locator("#aboutStageCreator").is_visible()
        assert creator.inner_text() == "Назад"
        creator_movie = page.frame_locator("#aboutCreatorFilmFrame")
        assert creator_movie.locator("#authorMeshCanvas").count() == 1
        assert creator_movie.locator("#authorMeshCanvas").get_attribute("data-model-kind") == "3d-mesh"
        assert creator_movie.locator(".ch a").evaluate_all(
            'links => links.map(a => a.getAttribute("href"))') == [
                "https://t.me/iznankamedia", "mailto:artem_shmakow@vk.com"]
        assert page.locator("#aboutCreatorReplay").is_visible()
        creator.click()
        assert intro.is_visible()
        page.wait_for_timeout(550)
        assert page.locator(".about-stage:visible").count() == 1
        assert creator.inner_text() == "Создатель"
        assert screen.evaluate('el => el.clientWidth > 0')
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
        # Desktop rating CTA now visibly glows only on hover.
        page.goto(base + "/index.html")
        full_list = page.locator(".show-full-list-trigger.full-list-button-desktop")
        normal_style = full_list.evaluate(
            'el => ({background:getComputedStyle(el).backgroundImage, shadow:getComputedStyle(el).boxShadow})')
        full_list.hover()
        page.wait_for_timeout(260)
        hovered_style = full_list.evaluate(
            'el => ({background:getComputedStyle(el).backgroundImage, shadow:getComputedStyle(el).boxShadow})')
        assert normal_style != hovered_style
        # Archive starts directly with search/filter controls on desktop.
        page.goto(base + "/archive.html")
        page.wait_for_selector('#archiveList .archive-item')
        assert page.locator(".archive-top-row, .section-subtitle, #manipCounter").count() == 0
        assert page.locator("#archiveList .archive-item").count() > 0
        page.goto(base + "/about.html")
        assert page.frame_locator("#aboutFilmFrame").locator(".logo").count() == 1
        # The iframe and controls stay within the TV monitor.
        page.goto(base + "/about.html")
        page.frame_locator("#aboutFilmFrame").locator("#stage").wait_for()
        geometry = page.evaluate("""() => {
            const monitor = document.querySelector('#aboutMonitorScreen').getBoundingClientRect();
            const film = document.querySelector('#aboutFilm').getBoundingClientRect();
            const iframe = document.querySelector('#aboutFilmFrame').getBoundingClientRect();
            const controls = document.querySelector('.about-film-controls').getBoundingClientRect();
            return {monitor,film,iframe,controls};
        }""")
        assert abs(geometry["monitor"]["width"] - geometry["film"]["width"]) <= 2, geometry
        assert abs(geometry["iframe"]["width"] - geometry["film"]["width"]) <= 2, geometry
        assert geometry["controls"]["bottom"] <= geometry["film"]["bottom"] + 2, geometry
        # Desktop methodology: all three numbers end on the same baseline.
        page.goto(base + "/method.html")
        numbers = page.locator("#pipelineGrid .pipe-num")
        assert numbers.count() == 3
        tops = numbers.evaluate_all("els => els.map(el => el.getBoundingClientRect().top)")
        assert max(tops) - min(tops) <= 1.5, tops
        assert numbers.all_inner_texts() == ["/01", "/02", "/03"]


        page.goto(base+"/index.html")
        # The favicon is shared by all public pages and rendered at every
        # standard browser / PWA size, including the vector version.
        assert page.locator('link[rel="icon"][type="image/svg+xml"]').get_attribute("href").endswith(
            "favicon.svg?v=focus1")
        svg_icon = (site / "favicon.svg").read_text(encoding="utf-8")
        assert '#13cde0' in svg_icon and '#f7f8fa' in svg_icon and '#000' in svg_icon
        for icon_name, size in (
            ("favicon-16x16.png", 16), ("favicon-32x32.png", 32),
            ("apple-touch-icon.png", 180), ("android-chrome-192x192.png", 192),
            ("android-chrome-512x512.png", 512),
        ):
            data = (site / icon_name).read_bytes()
            assert data[:8] == bytes.fromhex("89504e470d0a1a0a"), icon_name
            assert int.from_bytes(data[16:20], "big") == size, icon_name
            assert int.from_bytes(data[20:24], "big") == size, icon_name
        assert (site / "favicon.ico").read_bytes().startswith(bytes.fromhex("00000100"))
        # The public page background, navigation and footer are unchanged.
        # Only individual content blocks have brighter layered surfaces.
        assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg-body').trim()") == "#05070b"
        assert page.locator(".current-rating-section").evaluate(
            "el => getComputedStyle(el).backgroundImage") == "none"
        # The rating header is an open editorial layout; cards retain dark surfaces.
        for surface in (".hero-text", ".hero-counter"):
            assert page.locator(surface).first.evaluate(
                "el => getComputedStyle(el).backgroundImage") == "none"
        for surface in (".media-card", ".rating-appeal-strip"):
            assert "gradient" in page.locator(surface).first.evaluate(
                "el => getComputedStyle(el).backgroundImage"), surface
        # The approved editorial card has a logo/title/status heading,
        # a soft accent percentage line and an archive link.
        rating_cards = page.locator("#mediaGrid .media-card")
        rating_cards.first.wait_for(state="visible")
        # The front page displays one row of up to three cards on desktop.
        assert 1 <= rating_cards.count() <= 3
        assert not page.locator("#ratingStatus").inner_text().startswith("Обновлено:")
        assert rating_cards.first.locator(".media-name, .rating-headline, .media-footer .link-button").count() == 3
        assert rating_cards.first.locator(".rating-headline-label").inner_text() in ("спорных сообщений", "нет данных за 24 часа")
        assert rating_cards.first.locator(".media-level-badge, .rating-caption-row").count() == 0
        assert rating_cards.first.locator('.small-graph').count() == 0
        assert rating_cards.first.locator(".media-meta, .media-details, .rating-health, .rating-graph-caption, .rating-caption, .media-footer .badge").count() == 0
        first_card_rect = rating_cards.first.bounding_box()
        first_button_rect = rating_cards.first.locator(".media-footer .link-button").bounding_box()
        assert first_button_rect["width"] >= first_card_rect["width"] - 50
        if page.locator('.media-card[data-publisher="meduza"]').count():
            legal_tags = page.locator('.media-card[data-publisher="meduza"] .media-status-tag').all_inner_texts()
            assert "иноагент" in legal_tags
            assert "нежелательная организация" in legal_tags
        # Desktop defaults to compact interface size without horizontal overflow.
        assert page.evaluate("getComputedStyle(document.body).zoom") == "0.8"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
    finally:
        context.close()

    from browser_about_features_check import features_ui
    features_ui(browser, base)

    from browser_about_section_films_check import section_films_ui
    section_films_ui(browser, base)
