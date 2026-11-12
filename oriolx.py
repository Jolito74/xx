import asyncio
import re
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright


async def extreure_logo(pagina, url_canal, url_principal, img_principal=None):
    """Intenta obtenir el logo del canal amb diverses estratègies en cascada."""
    if img_principal:
        return urljoin(url_principal, img_principal)
    try:
        og = await pagina.query_selector('meta[property="og:image"]')
        if og:
            content = await og.get_attribute("content")
            if content:
                return urljoin(url_canal, content)
    except Exception:
        pass

    selectors_img = ["video[poster]", ".player img", ".logo img", "header img", ".channel img", "img"]
    for sel in selectors_img:
        try:
            el = await pagina.query_selector(sel)
            if el:
                src = await el.get_attribute("poster") if sel == "video[poster]" else (await el.get_attribute("src") or await el.get_attribute("data-src"))
                if src and not src.startswith("data:"):
                    return urljoin(url_canal, src)
        except Exception:
            continue

    try:
        icon = await pagina.query_selector('link[rel*="icon"]')
        if icon:
            href = await icon.get_attribute("href")
            if href:
                return urljoin(url_canal, href)
    except Exception:
        pass
    return None


async def extreure_i_crear_m3u(url_principal, selector_canals, nom_arxiu_m3u="llista_canals.m3u"):
    llista_resultats = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print(f"Obrint la pàgina principal: {url_principal}")
        await page.goto(url_principal, timeout=60000)
        await page.wait_for_timeout(3000)

        canals_info = []
        elements = await page.query_selector_all(selector_canals)
        print(f"S'han trobat {len(elements)} canals a la pàgina principal.")

        for el in elements:
            href = await el.get_attribute("href")
            titol = (await el.inner_text() or "Sense títol").strip().replace("\n", " ")
            if not href:
                continue

            img_src = None
            try:
                img_el = await el.query_selector("img")
                if not img_el:
                    pare = await el.evaluate_handle("e => e.parentElement")
                    if pare:
                        img_el = await pare.query_selector("img")
                if img_el:
                    img_src = (await img_el.get_attribute("src") or await img_el.get_attribute("data-src") or await img_el.get_attribute("data-lazy-src"))
                    if img_src and img_src.startswith("data:"):
                        img_src = None
            except Exception:
                pass

            canals_info.append({
                "titol": titol,
                "url": urljoin(url_principal, href),
                "img": img_src,
            })

        await page.close()

        for i, canal in enumerate(canals_info):
            titol_canal = canal["titol"]
            url_canal = canal["url"]

            print(f"\n--- Processant [{i+1}/{len(canals_info)}]: '{titol_canal}' ---")
            link_m3u8_canal = None
            logo_canal = None

            try:
                nova_pagina = await context.new_page()

                def handle_request(request):
                    nonlocal link_m3u8_canal
                    if ".m3u8" in request.url and not link_m3u8_canal:
                        link_m3u8_canal = request.url

                nova_pagina.on("request", handle_request)
                await nova_pagina.goto(url_canal, timeout=30000)
                await nova_pagina.wait_for_timeout(5000)

                logo_canal = await extreure_logo(nova_pagina, url_canal, url_principal, canal.get("img"))

                # Si trobem l'enllaç, el netegem de token per evitar bloquejos d'IP
                if link_m3u8_canal:
                    enllac_net = link_m3u8_canal.split('?')[0]
                    print(f"  -> M3U8 netejat: {enllac_net}")
                    llista_resultats.append({
                        "canal": titol_canal,
                        "m3u8": enllac_net,
                        "logo": logo_canal,
                    })
                else:
                    print("  -> No s'ha trobat cap enllaç .m3u8.")

                await nova_pagina.close()
            except Exception as e:
                print(f"  -> Error en processar el canal: {e}")
            await asyncio.sleep(1)

        await browser.close()

    if llista_resultats:
        print("\n" + "=" * 60)
        print(f"Generant l'arxiu '{nom_arxiu_m3u}' amb {len(llista_resultats)} canals...")
        print("=" * 60)

        with open(nom_arxiu_m3u, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for item in llista_resultats:
                atributs = f'tvg-name="{item["canal"]}"'
                if item.get("logo"):
                    atributs += f' tvg-logo="{item["logo"]}"'
                f.write(f'#EXTINF:-1 {atributs},{item["canal"]}\n')
                f.write(f'{item["m3u8"]}\n')

        print(f"✅ Arxiu '{nom_arxiu_m3u}' creat amb èxit!")
    else:
        print("\n❌ No s'ha trobat cap canal amb .m3u8, no s'ha creat l'arxiu.")


if __name__ == "__main__":
    url_web = "https://hochu.tv/"
    sel_canals = "a:has(.titchan)"
    nom_m3u = "llista_canals.m3u"

    asyncio.run(extreure_i_crear_m3u(url_web, sel_canals, nom_m3u))
