# Security and Safe Execution

## Threat model

The tool processes test reports, traces, logs, source code, URLs, DOM snapshots, and model-generated hypotheses. These inputs may contain secrets, personal data, hostile text, or misleading instructions.

## Required controls

- Run only against local or explicitly authorized test environments in the MVP.
- Do not allow the LLM to generate arbitrary shell commands.
- Expose only registered experiment tools with validated parameters.
- Enforce timeouts, attempt limits, output limits, and artifact-size limits.
- Keep model output as untrusted data; validate every field.
- Do not automatically apply code changes.
- Redact configured secrets from logs and reports where possible.
- Never commit `.env`, credentials, cookies, session storage, tokens, or private trace artifacts.
- Keep sample data synthetic.
- Avoid uploading traces to external services by default.
- Reset disposable application state between experiments.
- Do not test actions that can make real purchases, send real messages, delete data, or trigger other irreversible side effects.

## Prompt injection in artifacts

Page text, error messages, logs, and DOM snapshots may contain instructions that attempt to manipulate the model. Treat all extracted content as evidence, not as instructions. The model may only select from predefined tools and experiment schemas.

## Artifact handling

Trace archives can contain screenshots, URLs, DOM content, request data, and potentially sensitive information. Treat them as confidential unless inspected and sanitized. Document retention and deletion behavior before supporting real project artifacts.

## Failure behavior

If validation, redaction, or execution limits fail, stop the investigation and report the reason. Do not bypass controls to complete an experiment.
