"""Profil łowiecki operatora: wzorce wyprowadzone z markerów jego reklam, każdy z pochodzeniem.

Wzorzec ma `role`:
  search   po nim pytamy dzienniki certyfikatów (tokeny nazw domen),
  score    wchodzi do wyniku wstępnego bez sieci do strony (szablon nazwy, wystawca certyfikatu),
  confirm  sprawdzamy go na stronie kandydata przez crawlera (ścieżka zestawu, identyfikator lejka, hash DOM,
           trackery, rejestrator, serwery nazw).
Pochodzenie to reklamy operatora, z których wzorzec wzięto (`ad_ids`, najwyżej 20, i `ad_count`).
"""

from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Count

from evidence.kinds import KINDS
from evidence.models import AdMarker, Marker
from similarity.models import Operator, OperatorMembership

from .names import has_token, label_of, name_template, name_tokens

# Typy markerów sprawdzane na stronie kandydata. Kolejność to kolejność w profilu.
CONFIRM_KINDS = (
    "kit_path", "funnel_id", "dom_hash", "white_dom_hash",
    "ga4", "ga_ua", "gtm", "meta_pixel", "yandex_metrica", "tiktok_pixel", "google_ads",
    "form_action", "funnel_param", "asset_host", "favicon_hash", "url_path_tpl",
    "redirect_domain", "ip", "registrar", "nameserver", "reg_day",
)
MAX_PROVENANCE = 20
# Token obecny w tylu cudzych domenach korpusu jest zbyt pospolity, żeby po nim szukać.
GENERIC_DF = 4
MAX_TOKEN_WEIGHT = 0.9  # nawet unikalny token we wszystkich domenach operatora nie daje pewności samą nazwą
TOP_TOKENS = 3  # tyle najlepszych tokenów operatora idzie do zapytań


@dataclass
class Pattern:
    type: str  # name_token | name_template | cert_issuer | marker
    value: str
    role: str
    kind: str | None = None  # typ markera, gdy type == marker
    label: str = ""
    ad_ids: list[int] = field(default_factory=list)
    weight: float | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        ads = sorted(set(self.ad_ids))
        out = {
            "type": self.type, "kind": self.kind, "label": self.label, "value": self.value, "role": self.role,
            "ad_count": len(ads), "ad_ids": ads[:MAX_PROVENANCE], **self.detail,
        }
        if self.weight is not None:
            out["weight"] = round(self.weight, 3)
        return out


@dataclass
class Profile:
    operator: Operator
    ad_ids: list[int]
    domains: list[str]
    patterns: list[Pattern]

    def of_type(self, type_: str) -> list[Pattern]:
        return [p for p in self.patterns if p.type == type_]

    @property
    def tokens(self) -> list[Pattern]:
        return [p for p in self.of_type("name_token") if p.weight]

    @property
    def search_tokens(self) -> list[Pattern]:
        return sorted(self.tokens, key=lambda p: p.weight, reverse=True)[:TOP_TOKENS]

    def to_dict(self) -> dict:
        return {
            "operator": {"id": self.operator.pk, "key": self.operator.key, "label": self.operator.label},
            "ads": len(self.ad_ids),
            "domains": self.domains,
            "queries": [p.value for p in self.search_tokens],
            "patterns": [p.to_dict() for p in self.patterns],
        }


class CorpusNames:
    """Wszystkie domeny korpusu i ich nazwy. Z tego liczymy, które tokeny są pospolite."""

    def __init__(self) -> None:
        self.domains = set(Marker.objects.filter(kind="domain").values_list("value", flat=True))
        self.labels = {d: label_of(d) for d in self.domains}

    def __contains__(self, domain: str) -> bool:
        return domain in self.domains

    def others_with(self, token: str, own: set[str]) -> int:
        """W ilu domenach spoza `own` nazwa zawiera token (jako słowo albo fragment)."""
        return sum(1 for d, label in self.labels.items() if d not in own and has_token(label, token))


def operator_ad_ids(operator: Operator) -> list[int]:
    return list(OperatorMembership.objects.filter(operator=operator).values_list("ad_id", flat=True))


def issuer_name(issuer: str) -> str:
    """Nazwa wystawcy z `issuer_name` crt.sh: wartość CN, np. `R11` z `C=US, O=Let's Encrypt, CN=R11`."""
    for part in issuer.split(","):
        part = part.strip()
        if part.upper().startswith("CN="):
            return part[3:].strip()
    return issuer.strip()


def build_profile(operator: Operator, corpus: CorpusNames | None = None) -> Profile:
    corpus = corpus or CorpusNames()
    ad_ids = operator_ad_ids(operator)
    rows = list(
        AdMarker.objects.filter(ad_id__in=ad_ids, marker__kind__in=("domain", "tls_serial", *CONFIRM_KINDS)).values(
            "ad_id", "marker__kind", "marker__value", "detail"
        )
    )

    domain_ads: dict[str, set[int]] = defaultdict(set)
    by_marker: dict[tuple[str, str], set[int]] = defaultdict(set)
    issuers: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        kind, value, ad_id = row["marker__kind"], row["marker__value"], row["ad_id"]
        if kind == "domain":
            domain_ads[value].add(ad_id)
        elif kind == "tls_serial":
            issuer = issuer_name((row["detail"] or {}).get("issuer", ""))
            if issuer:
                issuers[issuer].add(ad_id)
        else:
            by_marker[(kind, value)].add(ad_id)

    own_domains = set(domain_ads)
    patterns: list[Pattern] = []

    # Tokeny nazw liczymy z każdej domeny osobno, żeby pochodzenie wskazywało reklamy, które ją miały.
    token_domains: dict[str, set[str]] = defaultdict(set)
    templates: dict[str, set[str]] = defaultdict(set)
    for domain in own_domains:
        label = label_of(domain)
        for token in name_tokens(label):
            token_domains[token].add(domain)
        templates[name_template(label)].add(domain)
    total = max(len(own_domains), 1)
    for token, domains in sorted(token_domains.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        others = corpus.others_with(token, own_domains)
        generic = others >= GENERIC_DF
        share = len(domains) / total
        specificity = 1.0 / (1.0 + others)
        weight = 0.0 if generic else MAX_TOKEN_WEIGHT * (0.5 + 0.5 * share) * specificity
        ads = {a for d in domains for a in domain_ads[d]}
        patterns.append(
            Pattern(
                "name_token", token, "search", label="Token nazwy domeny", ad_ids=list(ads), weight=weight,
                detail={"domains": sorted(domains), "other_domains": others, "generic": generic, "share": round(share, 3)},
            )
        )
    for template, domains in sorted(templates.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        ads = {a for d in domains for a in domain_ads[d]}
        patterns.append(
            Pattern("name_template", template, "score", label="Szablon nazwy domeny", ad_ids=list(ads), detail={"domains": sorted(domains)})
        )
    for issuer, ads in sorted(issuers.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        patterns.append(Pattern("cert_issuer", issuer, "score", label="Wystawca certyfikatu", ad_ids=list(ads)))

    order = {kind: i for i, kind in enumerate(CONFIRM_KINDS)}
    for (kind, value), ads in sorted(by_marker.items(), key=lambda kv: (order[kv[0][0]], -len(kv[1]), kv[0][1])):
        patterns.append(Pattern("marker", value, "confirm", kind=kind, label=KINDS[kind].label, ad_ids=list(ads)))

    return Profile(operator, ad_ids, sorted(own_domains), patterns)


def hunted_operators(operator_id: int | None = None) -> list[Operator]:
    """Operatorzy do polowania: niescaleni, z reklamami. Najwięksi pierwsi."""
    queryset = Operator.objects.filter(merged_into__isnull=True).annotate(size=Count("memberships")).filter(size__gte=1)
    if operator_id is not None:
        queryset = queryset.filter(pk=operator_id)
    return list(queryset.order_by("-size", "pk"))
