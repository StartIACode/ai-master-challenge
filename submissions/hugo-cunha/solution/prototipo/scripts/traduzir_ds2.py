#!/usr/bin/env python3
"""Translate Dataset 2 (English, preprocessed IT tickets) to pt-BR with Argos Translate (offline).

Why: the demo and the classifier must work in Portuguese (decision by Hugo). The Kaggle dataset is
English, so we machine-translate the text once and version the result as derived data
(``data/ds2_pt.csv.gz``: row_id, Document (pt), Topic_group). Labels are untouched.

One-time requirement (NOT a runtime dependency of the prototype):
    pip install argostranslate  &&  python -c "import argostranslate.package as p; p.update_package_index(); \
        pk=[x for x in p.get_available_packages() if x.from_code=='en' and x.to_code=='pt'][0]; p.install_from_path(pk.download())"

Engine: CTranslate2 + SentencePiece from the Argos package, called directly in batches (the Argos
sentence pipeline was ~10x slower on this corpus). Notes: product/technical names are protected from translation by capitalizing them (the model keeps
proper nouns); documents are split in 40-word chunks because the source has no punctuation;
progress is checkpointed to ``data/ds2_pt.partial.jsonl`` so an interrupted run resumes.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import pathlib
import re
import sys
import time

PROTO = pathlib.Path(__file__).resolve().parents[1]
SRC = PROTO / "data" / "all_tickets_processed_improved_v3.csv"
OUT = PROTO / "data" / "ds2_pt.csv.gz"
META = PROTO / "data" / "ds2_pt.meta.json"
PARTIAL = PROTO / "data" / "ds2_pt.partial.jsonl"
CHUNK_WORDS = 20  # the source has no punctuation; 20-word pieces translate best/fastest
BEAM = 2
BATCH = 64

PROTECT = [
    "windows", "outlook", "office", "excel", "word", "powerpoint", "teams", "sharepoint", "onedrive", "skype",
    "azure", "sap", "oracle", "jira", "confluence", "github", "git", "linux", "ubuntu", "citrix", "vmware",
    "docker", "sql", "mysql", "aws", "cisco", "lenovo", "dell", "hp", "macbook", "iphone", "android", "adobe",
    "acrobat", "chrome", "edge", "firefox", "vpn", "wifi", "laptop", "notebook", "desktop", "pc", "po", "cr",
    "ad", "erp", "crm", "pdf", "usb", "hdmi", "vga", "ssd", "ram", "cpu", "gpu", "lan", "wan", "dns", "dhcp",
    "ip", "url", "api", "sso", "mfa", "otp", "token", "ticket", "email", "e-mail", "login", "id", "vip",
]
_RX = re.compile(r"\b(" + "|".join(map(re.escape, PROTECT)) + r")\b")


def protect(text: str) -> str:
    return _RX.sub(lambda m: m.group(1).upper() if len(m.group(1)) <= 4 else m.group(1).capitalize(), text)


def _load_engine():
    """CTranslate2 model + SentencePiece from the installed Argos package (en_pt 1.9), used directly in batches."""
    import ctranslate2
    import sentencepiece as spm

    pkg = next(p for p in pathlib.Path.home().glob(".local/share/argos-translate/packages/*en_pt*") if p.is_dir())
    translator = ctranslate2.Translator(str(pkg / "model"), device="cpu", compute_type="int8", inter_threads=1, intra_threads=6)
    sp = spm.SentencePieceProcessor(model_file=str(pkg / "sentencepiece.model"))
    return pkg.name, translator, sp


def _pieces(text: str) -> list[str]:
    words = text.split()
    return [" ".join(words[k : k + CHUNK_WORDS]) for k in range(0, len(words), CHUNK_WORDS)] or [""]


def _detok(tokens: list[str]) -> str:
    return re.sub(r"\s+", " ", "".join(tokens).replace("\u2581", " ")).strip()


def translate_docs(translator, sp, docs: list[tuple[int, str]]) -> dict[int, str]:
    """Translate a list of (row_id, text) in one batched call per group of pieces; returns {row_id: pt}."""
    pieces = [(i, c) for i, d in docs for c in _pieces(d)]
    toks = [sp.encode(protect(c), out_type=str) for _, c in pieces]
    res = translator.translate_batch(toks, beam_size=BEAM, max_batch_size=BATCH, batch_type="examples",
                                     max_decoding_length=CHUNK_WORDS * 3 + 10)
    out: dict[int, list[str]] = {}
    for (i, _), r in zip(pieces, res):
        out.setdefault(i, []).append(_detok(r.hypotheses[0]))
    return {i: " ".join(parts) for i, parts in out.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="translate only the first N rows (smoke test)")
    args = ap.parse_args()

    with open(SRC, newline="", encoding="utf-8") as fh:
        rows = [(i, r["Document"], r["Topic_group"]) for i, r in enumerate(csv.DictReader(fh))]
    if args.limit:
        rows = rows[: args.limit]
    done: dict[int, str] = {}
    if PARTIAL.exists():
        for line in PARTIAL.open(encoding="utf-8"):
            rec = json.loads(line)
            done[rec["i"]] = rec["pt"]
    todo = [(i, t) for i, t, _ in rows if i not in done]
    print(f"{len(rows)} docs, {len(done)} já traduzidos, {len(todo)} a traduzir", flush=True)

    t0 = time.time()
    n = 0
    pkg_name, translator, sp = _load_engine()
    GROUP = 200  # docs per batched call (~1.5 s)
    with PARTIAL.open("a", encoding="utf-8") as ck:
        for g in range(0, len(todo), GROUP):
            group = todo[g : g + GROUP]
            for i, pt in translate_docs(translator, sp, group).items():
                done[i] = pt
                ck.write(json.dumps({"i": i, "pt": pt}, ensure_ascii=False) + "\n")
            n += len(group)
            ck.flush()
            if (g // GROUP) % 5 == 0 or n == len(todo):
                rate = n / (time.time() - t0)
                eta = (len(todo) - n) / rate if rate else 0
                print(f"{n}/{len(todo)}  {rate:.1f} docs/s  ETA {eta/60:.1f} min", flush=True)

    with gzip.open(OUT, "wt", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row_id", "Document", "Topic_group"])
        for i, _, label in rows:
            w.writerow([i, done[i], label])
    from importlib.metadata import version as _pkg_version

    META.write_text(json.dumps({
        "source": SRC.name, "rows": len(rows), "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "translator": f"argostranslate {_pkg_version('argostranslate')}", "package": pkg_name + " (Argos Open Tech, CTranslate2 int8, beam 2)",
        "chunk_words": CHUNK_WORDS, "protected_terms": PROTECT, "seconds": round(time.time() - t0, 1),
    }, ensure_ascii=False, indent=2))
    print(f"gravado {OUT} ({OUT.stat().st_size/1e6:.1f} MB) em {(time.time()-t0)/60:.1f} min", flush=True)


if __name__ == "__main__":
    sys.exit(main())
