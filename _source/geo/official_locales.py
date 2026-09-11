#!/usr/bin/env python3
"""App Store Connect locales required by the portfolio localization standard."""

import re

OFFICIAL_LOCALES = (
    "ar-SA",
    "bn-BD",
    "ca",
    "cs",
    "da",
    "de-DE",
    "el",
    "en-AU",
    "en-CA",
    "en-GB",
    "en-US",
    "es-ES",
    "es-MX",
    "fi",
    "fr-CA",
    "fr-FR",
    "gu-IN",
    "he",
    "hi",
    "hr",
    "hu",
    "id",
    "it",
    "ja",
    "kn-IN",
    "ko",
    "ml-IN",
    "mr-IN",
    "ms",
    "nl-NL",
    "no",
    "or-IN",
    "pa-IN",
    "pl",
    "pt-BR",
    "pt-PT",
    "ro",
    "ru",
    "sk",
    "sl-SI",
    "sv",
    "ta-IN",
    "te-IN",
    "th",
    "tr",
    "uk",
    "ur-PK",
    "vi",
    "zh-Hans",
    "zh-Hant",
)
OFFICIAL_LOCALE_SET = frozenset(OFFICIAL_LOCALES)

OPEN_GRAPH_LOCALES = {
    "ar-SA": "ar_SA",
    "bn-BD": "bn_BD",
    "ca": "ca_ES",
    "cs": "cs_CZ",
    "da": "da_DK",
    "de-DE": "de_DE",
    "el": "el_GR",
    "en-AU": "en_AU",
    "en-CA": "en_CA",
    "en-GB": "en_GB",
    "en-US": "en_US",
    "es-ES": "es_ES",
    "es-MX": "es_MX",
    "fi": "fi_FI",
    "fr-CA": "fr_CA",
    "fr-FR": "fr_FR",
    "gu-IN": "gu_IN",
    "he": "he_IL",
    "hi": "hi_IN",
    "hr": "hr_HR",
    "hu": "hu_HU",
    "id": "id_ID",
    "it": "it_IT",
    "ja": "ja_JP",
    "kn-IN": "kn_IN",
    "ko": "ko_KR",
    "ml-IN": "ml_IN",
    "mr-IN": "mr_IN",
    "ms": "ms_MY",
    "nl-NL": "nl_NL",
    "no": "no_NO",
    "or-IN": "or_IN",
    "pa-IN": "pa_IN",
    "pl": "pl_PL",
    "pt-BR": "pt_BR",
    "pt-PT": "pt_PT",
    "ro": "ro_RO",
    "ru": "ru_RU",
    "sk": "sk_SK",
    "sl-SI": "sl_SI",
    "sv": "sv_SE",
    "ta-IN": "ta_IN",
    "te-IN": "te_IN",
    "th": "th_TH",
    "tr": "tr_TR",
    "uk": "uk_UA",
    "ur-PK": "ur_PK",
    "vi": "vi_VN",
    "zh-Hans": "zh_CN",
    "zh-Hant": "zh_TW",
}


def open_graph_locale(locale):
    """Return the territory-qualified Open Graph locale for an ASC locale."""
    try:
        value = OPEN_GRAPH_LOCALES[locale]
    except KeyError as error:
        raise ValueError(f"Unsupported Open Graph locale: {locale}") from error
    if not re.fullmatch(r"[a-z]{2,3}_[A-Z]{2}", value):
        raise ValueError(f"Invalid Open Graph locale mapping: {locale}={value}")
    return value


def require_official_locale_coverage(key, locales):
    """Reject partial or noncanonical locale sets before public generation."""
    actual = set(locales)
    missing = sorted(OFFICIAL_LOCALE_SET - actual)
    unexpected = sorted(actual - OFFICIAL_LOCALE_SET)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unexpected:
            details.append(f"unexpected={','.join(unexpected)}")
        raise ValueError(f"{key} must have exactly 50 official locales: {'; '.join(details)}")
