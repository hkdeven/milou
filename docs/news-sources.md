# Vetted initial source set for the global AI brief

This source set is the starting authority mix for Milou's daily global AI news
brief. It was reviewed on **September 11, 2026**. The brief should not treat
any one outlet as a complete view of global AI; it should combine regional,
technical, policy, social-impact, and commercial reporting.

| Source | Direct link | Rationale | Geographic focus | Intended role |
| --- | --- | --- | --- | --- |
| [Rest of World](https://restofworld.org/) ([about](https://restofworld.org/about/)) | Nonprofit newsroom focused on technology's effects outside wealthy Western countries, with a large network of journalists reporting on the ground. | Africa, Asia, Latin America, the Middle East, and other under-covered markets. | Core source for global impact: labor, language, adoption, infrastructure, and harms. |
| [MIT Technology Review — Artificial Intelligence](https://www.technologyreview.com/topic/artificial-intelligence/) ([about](https://www.technologyreview.com/supertopic/about-mit-technology-review/)) | Technical and explanatory journalism supported by journalism, scientific research, data analysis, engineering, and business expertise. | Global, with substantial US and European technology coverage. | Explain and verify significance: capabilities, research, deployment risks, and business implications. |
| [IEEE Spectrum — AI](https://spectrum.ieee.org/topic/artificial-intelligence/) ([about](https://spectrum.ieee.org/about)) | IEEE's technology publication provides technically literate reporting on AI, machine learning, robotics, standards, and engineering. | International engineering and research community, with stronger North American and European coverage. | Technical anchor and reality check for research, chips, robotics, and safety claims. |
| [THE DECODER](https://the-decoder.com/) ([about](https://the-decoder.com/about/)) | Independent Germany-based AI specialist that reports globally and separates advertising or sponsored material from editorial work. | Europe, China, and global model and company developments. | Fast specialist layer for models, benchmarks, open source, agents, and product changes. |
| [South China Morning Post — Technology](https://www.scmp.com/tech) ([Big Tech](https://www.scmp.com/tech/big-tech), [about](https://corp.scmp.com/)) | Major Asian news source with regional depth on Chinese companies, semiconductors, AI standards, and markets. | China, Hong Kong, and Asia-Pacific. | Asia and China counterweight for labs, chips, industrial policy, and regional competition. |
| [Euractiv — Artificial Intelligence](https://www.euractiv.com/topics/artificial-intelligence/) ([about](https://www.euractiv.com/about-us/)) | Specialist European policy publication with strong access to EU institutions and policy debates. | European Union and European national governments, with international policy implications. | Policy desk for the AI Act, standards, competition, privacy, copyright, and enforcement. |
| [TechCrunch — Artificial Intelligence](https://techcrunch.com/category/artificial-intelligence/) | High-frequency reporting on AI companies, products, funding, partnerships, and ethical issues. | Primarily US startup and venture coverage, with international companies and investment. | Commercial lead source; claims should be corroborated before ranking highly. |
| [Nikkei Asia — Technology](https://asia.nikkei.com/Business/Technology) | Strong Asian business and technology perspective on chips, manufacturing, telecoms, and industrial strategy. | Japan, China, Korea, India, and broader Asia. | Business and industrial context that is often missing from US-centric coverage. |

## Selection rationale

Rest of World, SCMP, Euractiv, and Nikkei Asia provide the minimum regional
and policy counterweight to a US-centric technology feed. MIT Technology
Review, IEEE Spectrum, and THE DECODER supply technical interpretation.
TechCrunch adds timely commercial leads, but is intentionally not treated as
the sole confirmation of importance.

The mix is deliberately heterogeneous: nonprofit and specialist journalism,
engineering publication, policy reporting, regional business reporting, and a
high-volume commercial outlet. This makes duplicate detection and
cross-source corroboration possible without pretending that all outlets have
the same editorial scope or authority.

## Use and caveats

- Use direct article URLs, not only section or search URLs, in each report
  item.
- Confirm major claims against primary evidence where available: a company
  release, research paper, regulator, court filing, or government document.
- Record publication time and do not treat an undated archive item as fresh.
- Several sources are subscription-gated, JavaScript-driven, or feature-led
  rather than breaking-news wires. Access failure or delayed publication must
  be reported as uncertainty, not silently substituted.
- Euractiv's topic page is live but may return HTTP 403 to automated requests;
  a future implementation must handle that as an unavailable source and
  preserve the resulting confidence caveat.
- SCMP's China coverage and TechCrunch's US venture coverage are useful but
  require triangulation because of their editorial and market concentration.
