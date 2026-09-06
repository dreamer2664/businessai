# Knowledge packs

A pack is one file (`release/packs/<name>.kdw`) the brain searches when asked a question:
compressed passages + tiny numeric fingerprints for search. Built with the trim-and-pack
pipeline in `packs/`; the raw sources never ship, only the trimmed passages.

## business.kdw (milestone 1) — 5.7 MB, 17,908 passages, 751 documents

| source | bulk in | kept | what |
|---|---|---|---|
| OpenStax *Introduction to Business* (CC BY 4.0) | 1.12 M chars | 61 % | economics, ownership forms, management, finance, marketing basics |
| OpenStax *Principles of Marketing* (CC BY 4.0) | 1.23 M chars | 72 % | segmentation, 4 Ps, pricing, promotion, channels, research, digital |
| OpenStax *Entrepreneurship* (CC BY 4.0) | 1.25 M chars | 60 % | opportunity, business plans, funding, launching |
| OpenStax *Principles of Management* (CC BY 4.0) | 1.08 M chars | 49 % | planning, strategy, decisions, motivation |
| OpenStax key-term glossaries (4 books) | 0.30 M chars | 100 % | 2,239 one-line definitions (densest material) |
| Shopify blog — 213 guides (dropshipping, suppliers, pricing, metrics, ads, social, SEO, email, shipping, taxes, returns, fraud, legal) | 3.78 M chars | 66 % | practical e-commerce & dropshipping how-to |
| **total** | **8.75 M chars (~1,900 pages)** | **5.26 M chars (60 %)** | |

Everything is fetched as clean HTML text — no PDFs, no images, no page furniture. Dropped on purpose:
tables of contents, prefaces, indexes, exercises, case studies, anecdotes/stories, "in this chapter you will…",
link lists, product plugs, image captions, teaser lines, duplicates, and paragraphs with a low share of
informative words (definitions, numbers, mechanisms, steps are kept). Density threshold 5.5 (`packs/trim.py`).

### Scores
- `tests/business.txt` (55 questions, 4 blocks): **52/55** — basics 10/11, marketing 15/16, metrics & pricing 13/14, dropshipping & operations 14/14.
  Misses: law of supply & demand (textbook explains it without the phrase), product life cycle (definition found but lacks stage names), friendly fraud (answer buried in a stats paragraph).
- Coverage probe on the 440-question OpenStax marketing MCQ bank (`engine/scripts/coverage.py`, 100-question sample): the correct answer is present in the retrieved passages **77 %** of the time — that is the ceiling for the exam it will sit later.
- Engine setting: `KDR_WIKI_READK=3` (read the 3 best passages instead of 8): +3 questions, 2.5× faster (0.4 s per answer on 2 cores).

### Rebuild
```sh
python3 packs/openstax_fetch.py packs/openstax_books.json ~/.cache/bai/txt     # textbooks → clean TSV
python3 packs/web_fetch.py packs/sources/web_urls.tsv ~/.cache/bai/web/web.tsv         # web guides → TSV
python3 packs/trim.py ~/.cache/bai/txt/*.tsv ~/.cache/bai/web/web.tsv ~/.cache/bai/ext_final
python3 packs/build_pack.py ~/.cache/bai/ext_final release/packs/business.kdw   # embeds new passages, packs
python3 engine/scripts/score_pack.py tests/business.txt release/packs/business.kdw
```
