# Daily global AI news brief

## Contract

- **Name:** `daily-global-ai-news-brief`
- **Purpose:** Produce a concise, cited daily brief of the most globally
  discussed AI stories, with an explicit non-US and geographic-diversity
  emphasis.
- **Owner:** Milou supervisor
- **Version:** `0.1.0`
- **Status:** `proposed`

## Trigger and scope

- **Trigger:** Daily scheduled run or explicit user request.
- **Schedule:** Once per day, using the user's configured delivery time.
- **Freshness window:** Prefer articles published or materially updated in the
  previous 24 hours. Include older context only when it is necessary to explain
  a current development, and label it as context.
- **In scope:** AI research, models, products, infrastructure, labor and
  social impact, policy, safety, standards, business, and significant regional
  adoption or harms.
- **Out of scope:** General technology news without a meaningful AI angle,
  rumor presented as fact, opinion without a news development, and duplicate
  versions of the same underlying story.

## Inputs and sources

The initial vetted source set is documented in
[`docs/news-sources.md`](../docs/news-sources.md). The routine may scan those
outlets and primary evidence linked by their reporting. Live feeds, APIs,
scrapers, and external credentials are intentionally not implemented in this
repository yet.

Required input fields for a future implementation:

| Input | Required | Handling |
| --- | --- | --- |
| Article URL, headline, outlet, publication/update time | Yes | Preserve as citation metadata. |
| Article text or accessible summary | Yes | Do not infer beyond available evidence. |
| Primary source link, when available | Preferred | Use for corroboration and label source type. |
| Region and topic tags | Yes | Use for diversity and geographic weighting. |

## Ranking and selection

Rank candidate stories using explicit, explainable signals:

1. **Global discussion:** independent coverage across multiple regions or
   outlets, credible attention from institutions or practitioners, and
   evidence that the development affects more than one market.
2. **Significance:** likely effect on people, policy, research, safety,
   infrastructure, labor, or major AI capabilities.
3. **Freshness:** recency within the 24-hour window, with a clear penalty for
   older material.
4. **Evidence quality:** direct reporting, named sources, primary evidence, and
   corroboration score higher than anonymous claims or unsupported promotion.
5. **Under-covered perspective:** credible reporting from outside the US and
   from regions underrepresented in the candidate pool receives a positive
   diversity adjustment.

Use source diversity and geography as constraints, not as an excuse to include
low-significance stories. A daily report should aim for:

- at least half of its selected items to be led by non-US reporting,
  non-US institutions, or material non-US impact;
- representation from at least three geographic groupings when the day's
  credible candidate pool allows it;
- no more than two items led by the same outlet;
- a mix of at least three source roles where available: regional/global
  impact, technical or scientific, policy, and business;
- a separate note when the available high-confidence news is unusually
  concentrated in one region.

## Duplicate handling

Cluster articles covering the same underlying event by entities, event type,
date, and central claim. Select one lead article with the strongest evidence
and geographic or firsthand value. Add a second link only when it contributes
materially different regional reporting, technical evidence, or a primary
source. Never list several rewrites of the same press release as separate
stories.

## Output

Produce a short report with:

1. A date and freshness-window statement.
2. A ranked list of the selected stories.
3. For each item:
   - a clear headline;
   - a few concise sentences only when needed to explain what happened and why
     it matters;
   - region and topic labels;
   - a direct article/source link;
   - primary-source or corroborating links when available;
   - a brief uncertainty label when facts, access, timing, or significance
     remain unresolved.
4. A one-line note on geographic and source diversity.
5. A short “not included” note when a major candidate was excluded as a
   duplicate, stale item, unsupported claim, or low-confidence report.

The report must separate verified facts from analysis. It must not fabricate
headlines, publication times, article contents, geographic labels, or links.

## Citation and uncertainty requirements

- Every item requires a direct, resolvable article or primary-source URL.
- Cite the specific article used, not only an outlet homepage.
- Preserve the outlet and publication/update time.
- Mark inaccessible, paywalled, undated, conflicting, or single-source claims
  as uncertainty.
- If a story cannot meet the citation requirement, omit it or place it in an
  explicitly labeled “unverified leads” section; do not rank it as established
  news.
- If the source set cannot support geographic diversity on a given day, say so
  plainly rather than inventing balance.

## Permissions and side effects

- **Access level:** `read-only`
- **Side effects:** None. The routine may produce a report artifact only.
- **Approval required:** None for generating the report; per-action approval is
  required before any future routine could post, email, message, subscribe,
  bookmark, or alter source settings.

The routine must not contact sources or people, publish stories, change feeds,
follow links that trigger mutations, or treat a report as editorial approval.

## Reliability and evaluation

- **Timeout:** Future implementation must fail visibly if source collection
  exceeds its configured limit.
- **Retries:** Retry only transient retrieval failures; preserve the original
  error and never replace an unavailable source with an unmarked guess.
- **Partial results:** Allowed only when the report states which sources were
  unavailable and how that affects confidence and diversity.
- **Evaluation:** Track freshness, citation validity, duplicate rate, source
  diversity, geographic coverage, false positives, missed significant stories,
  uncertainty labeling, and reader usefulness.
- **Known limitation:** The initial source set is not a complete global news
  index and may underrepresent regions not covered by the listed outlets.

## Activation checklist

- [ ] Source links and access behavior have been tested.
- [ ] Candidate clustering and duplicate handling have representative fixtures.
- [ ] Ranking produces explainable signals and honors diversity constraints.
- [ ] Every output item has a direct citation and freshness metadata.
- [ ] Uncertainty and unavailable-source behavior has been tested.
- [ ] The report remains read-only and does not publish or contact anyone.
- [ ] The living case study records the activation decision and validation.
