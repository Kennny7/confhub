# Security, privacy, and consent

## Authentication

- Bind to loopback by default.
- Set a long random `API_KEY` before binding to a non-loopback interface.
- Use TLS at the reverse proxy and restrict API access by network policy.
- The Teams webhook uses a separate secret.
- Do not put platform account passwords, OAuth refresh tokens, or API secrets in source control.

## Identity

The assistant joins, when supported, under a bot-labelled identity. Do not change the display name to the account holder's personal name. The service does not make attendance claims on behalf of the account holder.

## Recording

- Recording is disabled by default.
- A recording request is not permission to record.
- Organizer authorisation is tracked separately from participant consent.
- Participant consent stays pending unless a trusted platform integration updates it.
- A provider must notify participants and return a successful recording-state acknowledgement before media is captured or persisted.
- The Python service does not capture raw media in this release.

## Transcripts and notes

- Transcript summarisation requires an explicit request flag confirming processing is authorised.
- The raw transcript is sent to the configured LLM and is not stored by the summarisation endpoint.
- The resulting summary is stored as a meeting note.
- Keep the LLM endpoint private and avoid sending confidential transcripts to an unapproved external provider.

## Retention

Configure `RECORDING_RETENTION_DAYS` and `TRANSCRIPT_RETENTION_DAYS` as policy values for future storage integrations. Automatic deletion jobs are not implemented in this release; storage integrations must enforce these values before production use.
