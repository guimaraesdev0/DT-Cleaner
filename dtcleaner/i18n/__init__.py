"""Internationalization layer (English / Brazilian Portuguese).

Design notes:

* English is the source language and the fallback. A missing key in another
  locale falls back to English, and a key missing everywhere renders as the key
  itself rather than crashing -- the UI must never die over a translation.
* Locales live in `locales/*.json` as flat dotted keys ("home.title"), which
  keeps diffing and reviewing translations trivial.
* `t()` reads the active language from a module-level singleton so screens can
  call it without threading a translator object through every constructor.
  `set_language()` is called once at startup and again when the user changes it
  in Settings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).parent / "locales"

DEFAULT_LANGUAGE = "en"

#: Language code -> label shown in the Settings screen (always in its own tongue).
AVAILABLE_LANGUAGES: dict[str, str] = {
    "en": "English",
    "pt_br": "Portugues (Brasil)",
}


class Translator:
    """Holds one active language plus the English fallback table."""

    def __init__(self, language: str = DEFAULT_LANGUAGE) -> None:
        self._fallback: dict[str, str] = _load_locale(DEFAULT_LANGUAGE)
        self._language = DEFAULT_LANGUAGE
        self._table: dict[str, str] = self._fallback
        self.set_language(language)

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> str:
        """Switch language. Unknown codes silently fall back to English."""
        code = (language or DEFAULT_LANGUAGE).lower().replace("-", "_")
        if code not in AVAILABLE_LANGUAGES:
            code = DEFAULT_LANGUAGE
        self._language = code
        self._table = self._fallback if code == DEFAULT_LANGUAGE else _load_locale(code)
        return code

    def get(self, key: str, /, **params: Any) -> str:
        """Translate `key`, interpolating `params` with str.format."""
        template = self._table.get(key) or self._fallback.get(key) or key
        if not params:
            return template
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            # A malformed translation must not break rendering.
            return template


_translator: Translator | None = None


def get_translator() -> Translator:
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def set_language(language: str) -> str:
    return get_translator().set_language(language)


def current_language() -> str:
    return get_translator().language


def t(key: str, /, **params: Any) -> str:
    """Shorthand used across the UI: `t("home.title")`."""
    return get_translator().get(key, **params)


def _load_locale(code: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{code}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: str(v) for k, v in data.items() if isinstance(k, str)}
