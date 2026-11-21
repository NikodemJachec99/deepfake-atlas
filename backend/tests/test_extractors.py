from extractors import minhash
from extractors.html import extract_page
from extractors.text import extract_text
from extractors.url import url_observations

LANDING_A = """
<html><head><title>Platforma inwestycyjna</title>
<link rel="icon" href="/static/fav.png">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7K2QX9LM4T"></script>
<script>gtag('config', 'G-7K2QX9LM4T'); fbq('init', '1234567890123456'); ym(98765432, "init", {});</script>
<script src="https://cdn.tracker.example/lib.js"></script>
</head><body>
<div class="hero dark"><h1 class="title">Zarabiaj 12 000 zł miesięcznie</h1>
<p class="lead">Napisz: <a href="https://t.me/zysk_support">Telegram</a> albo <a href="tel:+48 600 700 800">zadzwoń</a></p></div>
<section class="steps"><ul class="list">
<li class="item">Krok 1</li><li class="item">Krok 2</li><li class="item">Krok 3</li><li class="item">Krok 4</li>
</ul></section>
<form class="lead-form" action="https://crm.leads.example/api/v2/submit" method="post">
<input class="field" name="name"><input class="field" name="phone"><button class="cta">Dołącz</button></form>
<footer class="foot"><p class="small">kontakt@zysk-a.example</p><p class="small">BTC: bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq</p></footer>
</body></html>
"""

# Ten sam szablon, inne teksty i inny identyfikator analityki.
LANDING_B = LANDING_A.replace("Zarabiaj 12 000 zł", "Odbierz 9 500 zł").replace("G-7K2QX9LM4T", "G-AAAA1111BB")

OTHER = """
<html><head><title>Sklep</title></head><body>
<nav class="menu"><a class="link" href="/a">A</a><a class="link" href="/b">B</a></nav>
<main class="grid"><article class="card"><img class="photo"><h2 class="name">Buty</h2><span class="price">99</span></article>
<article class="card"><img class="photo"><h2 class="name">Kurtka</h2><span class="price">199</span></article>
<article class="card"><img class="photo"><h2 class="name">Czapka</h2><span class="price">49</span></article></main>
<aside class="side"><table class="spec"><tr class="row"><td class="cell">x</td><td class="cell">y</td></tr></table></aside>
</body></html>
"""


def _by_kind(observations):
    out = {}
    for o in observations:
        out.setdefault(o.kind, set()).add(o.value)
    return out


def test_trackers_are_extracted():
    page = extract_page(LANDING_A, "https://zysk-a.example/lp/1")
    kinds = _by_kind(page.observations)
    assert kinds["ga4"] == {"G-7K2QX9LM4T"}
    assert kinds["meta_pixel"] == {"1234567890123456"}
    assert kinds["yandex_metrica"] == {"98765432"}


def test_contacts_and_funnel_are_extracted():
    page = extract_page(LANDING_A, "https://zysk-a.example/lp/1")
    kinds = _by_kind(page.observations)
    assert kinds["telegram"] == {"zysk_support"}
    assert kinds["phone"] == {"48600700800"}
    assert kinds["email"] == {"kontakt@zysk-a.example"}
    assert kinds["crypto_btc"] == {"bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"}
    assert kinds["form_action"] == {"crm.leads.example/api/v2/submit"}
    assert "cdn.tracker.example" in kinds["script_host"]
    assert page.title == "Platforma inwestycyjna"
    assert page.favicon_url == "https://zysk-a.example/static/fav.png"


def test_form_posting_to_own_host_is_not_a_marker():
    html = LANDING_A.replace("https://crm.leads.example/api/v2/submit", "/send.php")
    kinds = _by_kind(extract_page(html, "https://zysk-a.example/lp/1").observations)
    assert "form_action" not in kinds


def test_same_template_with_different_copy_has_same_dom_hash():
    a = extract_page(LANDING_A, "https://zysk-a.example/")
    b = extract_page(LANDING_B, "https://inny-b.example/")
    assert a.dom_hash == b.dom_hash
    assert minhash.similarity(a.dom_signature, b.dom_signature) == 1.0


def test_different_template_is_far_in_minhash_and_shares_no_band():
    a = extract_page(LANDING_A, "https://zysk-a.example/")
    c = extract_page(OTHER, "https://sklep.example/")
    assert a.dom_hash != c.dom_hash
    assert minhash.similarity(a.dom_signature, c.dom_signature) < 0.3
    assert not set(minhash.bands(a.dom_signature)) & set(minhash.bands(c.dom_signature))


def test_small_edit_keeps_template_close():
    edited = LANDING_A.replace('<li class="item">Krok 4</li>', '<li class="item">Krok 4</li><li class="item">Krok 5</li>')
    a = extract_page(LANDING_A, "https://zysk-a.example/")
    e = extract_page(edited, "https://zysk-a.example/")
    assert a.dom_hash != e.dom_hash
    assert minhash.similarity(a.dom_signature, e.dom_signature) > 0.6


def test_tiny_page_has_no_dom_signature():
    page = extract_page("<html><body><p>ok</p></body></html>", "https://x.example/")
    assert page.dom_signature == []
    assert page.dom_hash == ""


def test_minhash_estimates_jaccard():
    a = {f"t{i}" for i in range(200)}
    b = {f"t{i}" for i in range(100, 300)}  # Jaccard = 100/300
    est = minhash.similarity(minhash.signature(a), minhash.signature(b))
    assert abs(est - 1 / 3) < 0.15
    assert minhash.similarity([], minhash.signature(a)) == 0.0


def test_url_observations():
    obs = _by_kind(url_observations("https://Go.Zysk-A.example/lp/48213/start?utm_source=fb&sub1=abc&fbclid=XYZ"))
    assert obs["domain"] == {"zysk-a.example"}
    assert obs["url_path_tpl"] == {"/lp/{n}/start"}
    # fbclid dokleja platforma, więc nie jest cechą kampanii
    assert obs["url_param_keys"] == {"sub1,utm_source"}


def test_url_without_path_or_params_gives_only_domain():
    obs = _by_kind(url_observations("https://zysk-a.example/"))
    assert set(obs) == {"domain"}


def test_text_near_duplicates_share_signature():
    t1 = "Polacy zarabiają 12 000 zł miesięcznie dzięki nowej platformie. Sprawdź, zanim usuną ten film!"
    t2 = "Polacy zarabiają 15 000 zł miesięcznie dzięki nowej platformie. Sprawdź, zanim usuną ten film!!!"
    t3 = "Nowa kolekcja butów zimowych już w sklepie. Darmowa dostawa od 200 zł i zwrot do 30 dni."
    a, b, c = extract_text(t1), extract_text(t2), extract_text(t3)
    assert minhash.similarity(a.signature, b.signature) > 0.7
    assert minhash.similarity(a.signature, c.signature) < 0.2


def test_text_contacts():
    kinds = _by_kind(extract_text("Pisz na https://t.me/szybki_zysk lub wa.me/48600700800, mail: a.b@firma.example").observations)
    assert kinds["telegram"] == {"szybki_zysk"}
    assert kinds["whatsapp"] == {"48600700800"}
    assert kinds["email"] == {"a.b@firma.example"}


def _article(seed: int, words: int) -> str:
    """Zmyślony tekst z losowych sylab. Każde ziarno daje inne słowa."""
    import random

    rng = random.Random(seed)
    syllables = [c + v for c in "bcdfghjklmnprstwz" for v in "aeiouy"]
    return " ".join("".join(rng.choice(syllables) for _ in range(rng.randint(2, 4))) for _ in range(words))


def test_same_article_with_appended_section_is_caught():
    """Zapis strony z doklejoną sekcją (komentarze, stopka) to wciąż ten sam artykuł."""
    article = _article(1, 600)
    saved = article + " " + _article(2, 500)
    a, b = extract_text(article), extract_text(saved)
    assert minhash.similarity(a.signature, b.signature) < 0.7  # sam Jaccard tego nie łapie
    assert minhash.text_similarity(a.signature, b.signature) > 0.9


def test_short_text_inside_long_page_is_not_the_same_text():
    """Krótki fragment (baner, stopka) zawarty w długiej stronie nie czyni stron tym samym tekstem."""
    banner = _article(3, 40)
    page = _article(4, 1500) + " " + banner
    a, b = extract_text(banner), extract_text(page)
    assert minhash.text_similarity(a.signature, b.signature) < 0.5


def test_different_articles_stay_apart_in_text_similarity():
    a, b = extract_text(_article(5, 600)), extract_text(_article(6, 600) + " " + _article(7, 400))
    assert minhash.text_similarity(a.signature, b.signature) < 0.5


def test_partly_shared_texts_of_equal_size_keep_jaccard():
    """Dwa teksty podobnej długości ze wspólną połową to nie zawieranie. Wynik zostaje przy Jaccardzie."""
    shared = _article(9, 300)
    a = extract_text(shared + " " + _article(13, 300)).signature
    b = extract_text(shared + " " + _article(14, 300)).signature
    assert minhash.text_similarity(a, b) == minhash.similarity(a, b)


def test_old_signature_without_size_still_compares():
    a = extract_text(_article(8, 300)).signature
    assert minhash.similarity(a[: minhash.NUM_PERM], a) == 1.0
    assert minhash.text_similarity(a[: minhash.NUM_PERM], a) == 1.0
    assert len(minhash.bands(a[: minhash.NUM_PERM])) == minhash.BANDS
