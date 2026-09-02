# Maintained direct App-data mirror governance artifacts

This directory records the source-governance boundary for Warhammer 40,000
11th Edition Core Rules. The current repository-owner policy recognizes two
non-affiliated maintained direct App-data mirrors: 40k.app and Game
Datamissions. Neither provider is identified as owned by, affiliated with, or
endorsed by Games Workshop.

The audit is provider-level governance evidence. It does not replace the exact
operative rule transcription, stable source ID, provider, URL, App-data version
or observation timestamp, transcription SHA-256, and immutable observation
fingerprint required by an implementation source package.

Validate the artifact and generated report offline with:

```text
uv run --no-sync python tools/core_rules_maintained_mirror_audit.py --check
```

After an intentional reviewed edit, refresh hashes and regenerate the report:

```text
uv run python tools/core_rules_maintained_mirror_audit.py --update-hashes
uv run python tools/core_rules_maintained_mirror_audit.py
```

The live provider sites are never runtime inputs.
