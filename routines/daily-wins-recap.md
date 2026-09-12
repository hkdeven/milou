# Daily wins recap

- **Name:** `daily-wins-recap`
- **Purpose:** Summarize completed work from structured activity fixtures.
- **Version/status:** `0.1.0` / tested
- **Inputs:** An `activities` array with title, status, timestamp, detail, and
  optional evidence URL and `inferred_impact`.
- **Output:** Markdown sections for **Verified facts**, **Inferred impact**, and
  coverage limits. Facts contain only supplied fields; impact is never presented
  as an observed outcome.
- **Access/side effects:** Read-only; no writes, contacts, or external calls.
- **Failure behavior:** Missing or empty activity arrays produce an explicit
  empty result. Missing evidence is called out, not invented.
- **Fixture:** `fixtures/activity.json`.
