# 40k.app core-rules observation artifacts

These artifacts retain secondary-provider observations for review. They are not runtime catalog
input and do not establish official Games Workshop provenance, rule supersession, or semantic
support. Official GW artifacts and versioned, hashed captures from the official Warhammer 40,000
App remain authoritative.

The audit contains only category URLs, section identities, short paraphrased findings, status
fields, and SHA-256 fingerprints of the normalized observation rows. It intentionally contains no
scraped HTML, page bundles, screenshots, or copied page bodies. A row hash detects changes to the
checked-in observation; it does not authenticate the external website.

CI remains offline. Validate the artifact and generated report with:

```text
uv run --no-sync python tools/core_rules_40k_app_audit.py --check
```

Refresh evidence hashes after a reviewed observation edit, then regenerate the report with:

```text
uv run python tools/core_rules_40k_app_audit.py --update-evidence-hashes
uv run python tools/core_rules_40k_app_audit.py
```

The current scope is exactly the 25 core-rules categories. Factions, faction detachments, and
faction datasheet content is explicitly excluded.
