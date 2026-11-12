# Wikipedia data source: options considered

The corpus must (1) be topically relevant to the demo questions, (2) be
cleanly attributable (title + URL per passage), (3) stay compatible with the
existing `articles` / `chunks` schema and 384-d MiniLM vectors, and (4) be
reproducible on a student laptop.

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **MediaWiki Action API** (`action=query` + `action=parse`) | Current text; page ids and revision ids for change detection; redirects and disambiguation flags; section structure in the HTML; no bulk download | Network-bound; must respect rate limits | **Used.** Fits a curated corpus of tens to hundreds of articles |
| Action API `prop=extracts` (TextExtracts) | Plain text, so less HTML cleanup | Only one full article per request; math and lists are poorly preserved | Not used; `parse` HTML gives better control |
| Hugging Face `wikimedia/wikipedia` (`20231101.en`, Parquet, ~6.4M articles) | Offline; fast for bulk work; same `id/url/title/text` fields | Frozen Nov 2023 snapshot (misses e.g. recent RAG/LLM articles); no revision ids; section headings flattened; very large download for English | Good for a future large-scale benchmark; can be fed into the same chunker by mapping `id → wiki_page_id` |
| Wikimedia XML / Enterprise HTML dumps | Complete and authoritative | Tens of GB; needs a wikitext/HTML parsing pipeline | Overkill for this project |
| Pre-embedded datasets (e.g. Cohere Wikipedia embeddings) | No embedding cost | Different model and dimensions; incompatible with `VECTOR(384)` and query embeddings | Rejected |

## How articles are selected

- **Curated list** (`data/corpus.json`): topics chosen to match the project
  (databases and MariaDB, vector search and IR, ML, NLP and embeddings, CS basics),
  grouped into categories that become `articles.category`.
- **Category expansion** (`--from-category`) for growing a topic quickly.
  Lists, outlines, glossaries, disambiguation pages and stubs are filtered out.
- Possible quality signals for later work: Wikipedia's
  [Vital articles](https://en.wikipedia.org/wiki/Wikipedia:Vital_articles) lists
  and WikiProject assessment classes (`prop=pageassessments`).

## API etiquette implemented

Wikimedia requires a descriptive User-Agent with contact details and is rolling
out per-client rate limits (HTTP 429). The client sends
`ConstructorUniversityVectorRAG/0.2 (<WIKI_CONTACT>) python-requests/x.y`,
makes serial requests with a configurable delay, sends `maxlag=5`, and backs off
exponentially (honouring `Retry-After`) on 429/5xx and `maxlag` errors.

## Licence

Wikipedia text is CC BY-SA 4.0. The pipeline keeps the article title and URL
for every chunk, and the UI shows them with each source, which provides the
required attribution.
