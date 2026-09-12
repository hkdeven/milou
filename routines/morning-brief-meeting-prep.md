# Morning brief / meeting prep

- **Name:** `morning-brief-meeting-prep`
- **Purpose:** Prepare concise, evidence-linked notes for meetings in a
  calendar fixture.
- **Version/status:** `0.1.0` / tested
- **Inputs:** A `meetings` array containing purpose, attendees, linked context,
  decisions, open questions, commitments, and inaccessible links.
- **Output:** Per-meeting Markdown with time, purpose, attendees, context,
  decisions, open questions, commitments, and inaccessible links.
- **Access/side effects:** Read-only; never contacts attendees or changes,
  accepts, declines, or creates events.
- **Failure behavior:** Empty or missing arrays are reported explicitly;
  missing fields are marked “Not provided” or “None recorded.”
- **Fixture:** `fixtures/meetings.json`.
