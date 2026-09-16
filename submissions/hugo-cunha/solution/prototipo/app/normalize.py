"""Text normalization shared by training (scripts/train.py) and the API.

The same function must be applied at training time and at prediction time so
that the TF-IDF vocabulary matches. It is intentionally simple and
deterministic: lowercase, drop e-mails/URLs/long numbers, strip punctuation,
remove a short list of EN+PT stopwords and collapse whitespace.

Property: ``normalize(normalize(x)) == normalize(x)`` (idempotent).
"""

from __future__ import annotations

import re

__all__ = ["STOP", "normalize"]

# Short, hand-picked list. Kept small on purpose: domain words such as
# "not", "down", "error", "vpn" must survive because they carry signal.
# "hello" is intentionally NOT a stopword (contract: tests/test_normalize.py).
STOP: frozenset[str] = frozenset(
    """
    a an the and or of to in on at for with is are was were be been being i you he she it we they
    me my your our their this that these those please hi dear thanks thank regards kind best team
    o a os as um uma de do da dos das e ou em no na nos nas por para com sem que se eu você ele ela nós eles
    oi olá obrigado obrigada atenciosamente prezado prezada
    """.split()
)

_EMAIL = re.compile(r"\S+@\S+")
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_NUM = re.compile(r"\b\d{3,}\b")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str | None) -> str:
    """Return a lowercase, punctuation-free, stopword-free version of ``text``.

    ``None`` and empty input yield ``""``. Accented characters are kept
    (Dataset 2 is English; Portuguese input still works, just unaccented and
    accented forms are distinct tokens).
    """
    t = (text or "").lower()
    t = _EMAIL.sub(" ", t)
    t = _URL.sub(" ", t)
    t = _NUM.sub(" ", t)
    t = _PUNCT.sub(" ", t).replace("_", " ")
    tokens = [w for w in t.split() if w not in STOP and not w.isdigit()]
    return " ".join(tokens)
