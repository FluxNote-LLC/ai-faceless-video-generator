# Contributing

Keep examples small, dependency-free, and consistent across JavaScript and Python. Submit changes with mock tests; do not require live credentials or paid generation in CI.

Before submitting:

```bash
python3 -m unittest discover -s tests -v
node --test tests/javascript.test.mjs
```

Do not include customer data, screenshots from customer accounts, credentials, generated receipts, or proprietary source code. New contributions must be compatible with the MIT license.

Changes to defaults that can increase generation cost must be clearly documented. Preserve explicit confirmation, saved job IDs, bounded polling, and credential-free media downloads.
