import pytest

from similarity.fusion import Shared, Soft, connected_components, score_pair

N = 100_000


def test_rare_tracker_plus_template_is_same_campaign():
    result = score_pair(
        shared=[Shared("ga4", "G-7K2QX9LM4T", df=2), Shared("asn", "AS13335", df=31_000)],
        soft=[Soft("dom_minhash", 0.93)],
        corpus_n=N,
    )
    assert result.relation == "same_campaign"
    assert result.decisive is True
    assert result.probability > 0.99
    top = result.evidence[0]
    assert top.kind == "ga4"
    assert top.weight_bits > 10
    assert {e.family for e in result.evidence} == {"track", "infra", "tmpl"}


def test_common_infrastructure_alone_links_nothing():
    result = score_pair(
        shared=[
            Shared("asn", "AS13335", df=31_000),
            Shared("nameserver", "ns1.cloudflare.com", df=22_000),
            Shared("registrar", "NameCheap, Inc.", df=18_000),
        ],
        soft=[],
        corpus_n=N,
    )
    assert result.relation is None
    assert result.probability < 0.01
    assert all(e.weight_bits < 2.5 for e in result.evidence)


def test_hub_marker_is_worth_almost_nothing_even_if_kind_is_strong():
    # Domena skracacza linków: silny typ markera, ale dzieli go 40% korpusu.
    result = score_pair(shared=[Shared("domain", "bit.ly", df=40_000)], soft=[], corpus_n=N)
    assert result.relation is None
    assert result.evidence[0].weight_bits < 1.5
    assert result.decisive is False


def test_two_independent_families_without_decisive_marker():
    result = score_pair(
        shared=[Shared("dom_hash", "9f3a", df=3), Shared("favicon_hash", "-1234", df=3)],
        soft=[],
        corpus_n=N,
    )
    assert result.decisive is False
    assert result.relation == "same_campaign"
    assert set(result.families) == {"tmpl", "infra"}


def test_single_non_decisive_family_is_not_enough():
    result = score_pair(shared=[Shared("dom_hash", "9f3a", df=3)], soft=[Soft("dom_minhash", 1.0)], corpus_n=N)
    assert result.relation != "same_campaign"


def test_correlated_markers_in_one_family_are_discounted():
    result = score_pair(
        shared=[Shared("domain", "zysk-a.example", df=2), Shared("ip", "203.0.113.7", df=2), Shared("tls_fp", "ab12", df=2)],
        soft=[],
        corpus_n=N,
    )
    raw = sum(e.raw_bits for e in result.evidence)
    assert result.families["infra"] < raw
    assert result.families["infra"] == pytest.approx(sum(e.weight_bits for e in result.evidence))
    # najsilniejszy dowód liczy się w całości
    assert result.evidence[0].weight_bits == pytest.approx(result.evidence[0].raw_bits)


def test_shared_narrative_only_is_similar_not_same():
    result = score_pair(
        shared=[Shared("person_mention", "Q12345", df=900)],
        soft=[Soft("text_minhash", 0.9)],
        corpus_n=N,
    )
    assert result.relation == "similar"
    assert result.decisive is False


def test_more_evidence_never_lowers_probability():
    base = score_pair(shared=[Shared("ga4", "G-1", df=2)], soft=[], corpus_n=N)
    more = score_pair(shared=[Shared("ga4", "G-1", df=2), Shared("telegram", "abc", df=2)], soft=[], corpus_n=N)
    assert more.probability >= base.probability
    assert more.bits > base.bits


def test_rarity_holds_in_tiny_corpus():
    # W korpusie 20 reklam częstość nic nie mówi, więc działa prior typu markera.
    result = score_pair(shared=[Shared("ga4", "G-1", df=2)], soft=[], corpus_n=20)
    assert result.evidence[0].raw_bits > 10
    common = score_pair(shared=[Shared("asn", "AS13335", df=2)], soft=[], corpus_n=20)
    assert common.evidence[0].raw_bits < 2.5


def test_soft_similarity_below_threshold_gives_no_evidence():
    result = score_pair(shared=[], soft=[Soft("dom_minhash", 0.35)], corpus_n=N)
    assert result.evidence == []
    assert result.bits == 0


def test_unknown_kind_is_rejected():
    with pytest.raises(KeyError):
        score_pair(shared=[Shared("nie_ma_takiego", "x", df=2)], soft=[], corpus_n=N)


def test_connected_components():
    groups = connected_components([(1, 2), (2, 3), (7, 8)])
    assert sorted(sorted(g) for g in groups) == [[1, 2, 3], [7, 8]]
