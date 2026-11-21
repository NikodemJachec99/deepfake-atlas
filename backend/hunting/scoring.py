"""Wynik wstępny kandydata: tylko nazwa domeny i certyfikat, bez połączenia ze stroną.

Składniki łączą się jak niezależne poszlaki, 1 - iloczyn (1 - składnik), więc wynik rośnie z każdym i nie przekracza 1:
  tokeny    każdy token profilu z nazwy kandydata daje swoją wagę z profilu (osobne słowo w pełni, sam fragment 0,8)
  szablon   nazwa po zamianie cyfr na `{n}` jest szablonem znanej domeny operatora: +0,3
  wystawca  certyfikat wystawił ten sam wystawca co certyfikaty operatora: +0,1 (słabe: wystawców jest garstka)
"""

from .names import has_token, label_of, name_template
from .profile import Profile, issuer_name

PART_FACTOR = 0.8
TEMPLATE_BONUS = 0.3
ISSUER_BONUS = 0.1
DEFAULT_THRESHOLD = 0.45  # od tego wyniku kandydat jest zapisany i może iść do crawlera


def prelim_score(domain: str, issuer: str, profile: Profile) -> tuple[float, dict]:
    label = label_of(domain)
    matched = []
    gains: list[float] = []
    for pattern in profile.tokens:
        how = has_token(label, pattern.value)
        if not how:
            continue
        gain = pattern.weight * (1.0 if how == "exact" else PART_FACTOR)
        gains.append(gain)
        matched.append({"token": pattern.value, "match": how, "weight": round(gain, 3)})
    parts: dict = {"tokens": matched, "template": None, "issuer": None}
    if matched:
        # Szablon i wystawca niczego nie dowodzą bez nazwy: same nie są tropem.
        template = name_template(label)
        if template in {p.value for p in profile.of_type("name_template")}:
            parts["template"] = template
            gains.append(TEMPLATE_BONUS)
        if issuer and issuer_name(issuer) in {p.value for p in profile.of_type("cert_issuer")}:
            parts["issuer"] = issuer_name(issuer)
            gains.append(ISSUER_BONUS)
    remaining = 1.0
    for gain in gains:
        remaining *= 1.0 - gain
    return round(1.0 - remaining, 3), parts
