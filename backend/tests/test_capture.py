"""Ślady z przechwyceń (HAR, parametry URL). Wzorce pochodzą z paczki organizatora, wartości są zmyślone."""

import base64

from extractors import minhash
from extractors.har import parse_har
from extractors.html import extract_page
from extractors.url import redact_url, url_observations
from people.matching import find_people


def by_kind(observations):
    out = {}
    for o in observations:
        out.setdefault(o.kind, set()).add(o.value)
    return out


def entry(method, url, *, status=200, mime="text/html", text="", b64=False, ip="", post=None, headers=None, location=""):
    content = {"mimeType": mime, "text": base64.b64encode(text.encode()).decode() if b64 else text}
    if b64:
        content["encoding"] = "base64"
    response_headers = [{"name": k, "value": v} for k, v in (headers or {}).items()]
    if location:
        response_headers.append({"name": "Location", "value": location})
    request = {"method": method, "url": url, "headers": []}
    if post is not None:
        request["postData"] = {"mimeType": "application/x-www-form-urlencoded", "text": post}
    return {
        "startedDateTime": "2026-10-09T06:25:24.977Z",
        "request": request,
        "response": {"status": status, "headers": response_headers, "content": content, "redirectURL": location},
        "serverIPAddress": ip,
    }


VISIT = "01a00000-aaaa-7bbb-8ccc-000000000001"
PAGE = f"https://zysk-a.example/?utm_id=AbCdEf123456&utm_medium=x1&utm_campaign=x2&utm_content=x3&utm_visit={VISIT}"
HTML = "<html><head><title>Artykuł</title></head><body><p>treść</p></body></html>"


def funnel_har(domain="zysk-a.example", ip="203.0.113.7"):
    page = PAGE.replace("zysk-a.example", domain)
    return {
        "log": {
            "entries": [
                entry("GET", "https://go.hop.example/c/123?x=1", status=302, location=page, mime=""),
                entry("GET", page, text=HTML, b64=True, ip=ip, headers={"server": "cloudflare", "via": "1.1 Caddy"}),
                entry("GET", f"https://{domain}/aio-static/sdk/main.js", mime="application/javascript", text="fbq('init', '1234567890123456');", ip=ip),
                entry("GET", f"https://{domain}/favicon.ico", mime="image/x-icon", ip=ip),
                entry("GET", "https://cdn.jsdelivr.net/npm/x@1/x.js", mime="application/javascript"),
                entry("GET", "https://vz-0a1b2c3d-123.b-cdn.net/0000aaaa/playlist.m3u8", mime="application/vnd.apple.mpegurl"),
                entry("GET", "https://bf1.clickline.example/click?event8=1", mime="text/plain"),
                entry("GET", "https://www.facebook.com/tr/?id=2000000000000001&ev=PageView", mime="image/gif"),
                entry("GET", "https://googleads.g.doubleclick.net/pagead/viewthroughconversion/17123456789/?random=1", mime="image/gif"),
                entry(
                    "POST",
                    f"https://{domain}/api/v1/trigger/field/{VISIT}/",
                    mime="application/json",
                    ip=ip,
                    post=f"landed_on_landings_uuid=11111111-2222-4333-8444-555555555555&landed_on_landings_types_uuid=66666666-7777-4888-9999-aaaaaaaaaaaa&visit_uuid={VISIT}&browser_time_zone=Europe%2FWarsaw",
                ),
            ]
        }
    }


def test_har_main_document_and_chain():
    summary = parse_har(funnel_har())
    assert summary.page_url == PAGE
    assert summary.html == HTML  # treść zakodowana base64 jest dekodowana
    assert [(hop["status"], hop["via"]) for hop in summary.chain] == [(302, "http"), (200, "http")]
    assert summary.chain[0]["url"].startswith("https://go.hop.example/")
    assert summary.started_at.startswith("2026-10-09")


def test_har_kit_paths_identify_the_funnel_engine():
    kinds = by_kind(parse_har(funnel_har()).observations)
    assert "POST /api/v1/trigger/field/{id}/" in kinds["kit_path"]
    assert "GET /aio-static/sdk/main.js" in kinds["kit_path"]
    # ścieżki, które ma każda strona, nie są odciskiem
    assert not any("favicon" in p or p == "GET /" for p in kinds["kit_path"])


def test_same_engine_on_another_domain_gives_the_same_markers():
    a = by_kind(parse_har(funnel_har("zysk-a.example")).observations)
    b = by_kind(parse_har(funnel_har("inny-b.example", ip="198.51.100.9")).observations)
    assert a["kit_path"] == b["kit_path"]
    assert a["funnel_id"] == b["funnel_id"]
    assert a["ip"] != b["ip"]


def test_har_asset_hosts_skip_public_cdns_and_keep_tenants():
    kinds = by_kind(parse_har(funnel_har()).observations)
    assert kinds["asset_host"] == {"vz-0a1b2c3d-123.b-cdn.net", "clickline.example"}
    assert kinds["redirect_domain"] == {"hop.example"}


def test_har_funnel_ids_exclude_the_visit_id():
    kinds = by_kind(parse_har(funnel_har()).observations)
    assert kinds["funnel_id"] == {"11111111-2222-4333-8444-555555555555", "66666666-7777-4888-9999-aaaaaaaaaaaa"}


def test_har_trackers_from_requests_and_script_bodies():
    kinds = by_kind(parse_har(funnel_har()).observations)
    assert kinds["meta_pixel"] == {"1234567890123456", "2000000000000001"}
    assert kinds["google_ads"] == {"17123456789"}


def test_har_cloudflare_address_is_not_an_ip_marker():
    kinds = by_kind(parse_har(funnel_har(ip="188.114.96.12")).observations)
    assert "ip" not in kinds
    assert kinds["cdn"] == {"cloudflare"}
    assert by_kind(parse_har(funnel_har(ip="203.0.113.7")).observations)["ip"] == {"203.0.113.7"}
    assert kinds["server_sig"] == {"cloudflare|caddy"}


def test_url_params_carry_pixels_affiliate_keys_and_ad_references():
    url = (
        "https://ineptsolid.example/?pxl=1000000000000002&acc=zz11_tv1_feed1&ad_name=tvtext_a1"
        "&ad_id=120000000000000001&adset_name=0101_pl_w_%D1%81%D1%81_d1&key=abcd1234efgh5678ijkl&geo=PL"
        "&utm_campaign=%7Baccount.id%7D&utm_id=120000000000000002&fbclid=XYZ"
    )
    kinds = by_kind(url_observations(url))
    assert kinds["meta_pixel"] == {"1000000000000002"}
    assert kinds["funnel_param"] == {"key=abcd1234efgh5678ijkl", "acc=zz11_tv1_feed1"}
    assert kinds["meta_ad_ref"] == {"120000000000000001", "120000000000000002"}
    assert kinds["ad_naming"] == {"ad_name=tvtext_a1", "adset_name=0101_pl_w_сс_d1"}
    assert kinds["lang_trace"] == {"cyrillic"}
    assert "acc,ad_id,ad_name,adset_name,geo,key,pxl,utm_campaign,utm_id" in kinds["url_param_keys"]


def test_nonstandard_utm_key_makes_the_parameter_set_a_marker():
    funnel = by_kind(url_observations(PAGE))
    assert funnel["url_param_keys"] == {"utm_campaign,utm_content,utm_id,utm_medium,utm_visit"}
    plain = by_kind(url_observations("https://x.example/a?utm_source=fb&utm_medium=paid&utm_campaign=wiosna"))
    assert "url_param_keys" not in plain
    # wartości jednorazowe nie są markerami
    assert "funnel_param" not in funnel and "meta_ad_ref" not in funnel


def test_access_token_is_never_stored_in_clear():
    url = "https://summit.example/?fbpx=1500000000000003&access_token=EAATESTfake0000000000000000000000000000tokenA&ad_id=120000000000000003"
    clean = redact_url(url)
    assert "EAATESTfake00000000" not in clean and "access_token=sha256-" in clean
    kinds = by_kind(url_observations(url))
    assert kinds["meta_pixel"] == {"1500000000000003"}
    token = next(iter(kinds["capi_token"]))
    assert token.startswith("sha256-") and "EAAU" not in token
    assert by_kind(url_observations(clean))["capi_token"] == {token}  # po redakcji marker zostaje ten sam


def test_page_markers_title_brand_and_text_signature():
    html = (
        "<html><head><title>«Wiem, kto strzelał»: zamach na znanego biznesmena — Gazeta.pl</title></head><body>"
        + "".join(f"<p class='t'>Akapit numer {i} opisuje wydarzenia, które wstrząsnęły całą Polską tego wieczoru.</p>" for i in range(30))
        + "</body></html>"
    )
    a = extract_page(html, "https://civicday.example/?x=1")
    b = extract_page(html, "https://across.example/?x=2")
    kinds = by_kind(a.observations)
    assert kinds["brand_impersonated"] == {"Gazeta.pl"}
    assert kinds["page_title"] == {"«wiem, kto strzelał»: zamach na znanego biznesmena — gazeta.pl"}
    assert kinds["page_name"] == {"civicday"}
    assert minhash.similarity(a.text_signature, b.text_signature) == 1.0
    # prawdziwa domena marki nie jest podszyciem
    assert "brand_impersonated" not in by_kind(extract_page(html, "https://wiadomosci.gazeta.pl/x").observations)


def test_cyrillic_in_page_source_is_a_trace():
    html = "<html><head><title>Oferta</title><!-- кнопка заказа --></head><body><p>Zamów teraz</p></body></html>"
    assert by_kind(extract_page(html, "https://x.example/").observations)["lang_trace"] == {"cyrillic"}


def test_people_are_found_despite_polish_inflection():
    people = [(1, "Rafał Wiśniewski", []), (2, "Monika Zielińska", []), (3, "Iga Lewicka", ["Lewicka Iga"])]
    text = "Rozmowa z Rafałem Wiśniewskim, założycielem firmy. Potem Monika Zielińska powiedziała jedno zdanie."
    assert find_people(text, people) == [1, 2]
    assert find_people("Wywiad z Igą Lewicką po finale", people) == [3]
    assert find_people("Rafał Kowalski i Anna Wiśniewska rozmawiali", people) == []
