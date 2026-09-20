# -*- coding: utf-8 -*-
"""语言代码映射：界面所用 ISO 639-1 代码 <-> Whisper 代码 <-> NLLB 代码。"""

# ISO 639-1 code -> (显示名, whisper代码/None自动, NLLB代码)
# whisper 依赖模型内置语言；NLLB 用其 200 语言代码。
LANG_MAP = {
    "en":  ("英文 / English",          "en",     "eng_Latn"),
    "zh":  ("中文(简体) / Chinese",     "zh",     "zho_Hans"),
    "zh_tw":("中文(繁体) / Chinese TW", "zh",     "zho_Hant"),
    "ja":  ("日文 / Japanese",          "ja",     "jpn_Jpan"),
    "ko":  ("韩文 / Korean",            "ko",     "kor_Hang"),
    "fr":  ("法文 / French",            "fr",     "fra_Latn"),
    "de":  ("德文 / German",            "de",     "deu_Latn"),
    "es":  ("西文 / Spanish",           "es",     "spa_Latn"),
    "it":  ("义文 / Italian",           "it",     "ita_Latn"),
    "pt":  ("葡文 / Portuguese",        "pt",     "por_Latn"),
    "ru":  ("俄文 / Russian",           "ru",     "rus_Cyrl"),
    "ar":  ("阿文 / Arabic",            "ar",     "arb_Arab"),
    "hi":  ("印地 / Hindi",             "hi",     "hin_Deva"),
    "th":  ("泰文 / Thai",              "th",     "tha_Thai"),
    "vi":  ("越南 / Vietnamese",        "vi",     "vie_Latn"),
    "id":  ("印尼 / Indonesian",        "id",     "ind_Latn"),
    "tr":  ("土文 / Turkish",           "tr",     "tur_Latn"),
    "nl":  ("荷兰 / Dutch",             "nl",     "nld_Latn"),
    "pl":  ("波兰 / Polish",            "pl",     "pol_Latn"),
    "uk":  ("乌克兰 / Ukrainian",       "uk",     "ukr_Cyrl"),
}

def display_name(code: str) -> str:
    return LANG_MAP.get(code, (code, code, code))[0]

def code_list() -> "list[tuple[str, str]]":
    """返回 (iso代码, 显示名) 列表，供下拉框使用。"""
    return [(c, v[0]) for c, v in LANG_MAP.items()]

def whisper_code(iso: str) -> str:
    return LANG_MAP.get(iso, (iso, iso, iso))[1]

def nllb_code(iso: str) -> str:
    return LANG_MAP.get(iso, (iso, iso, iso))[2]
