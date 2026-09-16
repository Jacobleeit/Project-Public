# Contributing

This is an initial release of a small backup-reporting utility. Bug reports, clearer documentation, anonymized sample formats, and focused improvements are welcome.

1. Describe the operational problem and expected result in an issue.
2. Use fictional object names and diagnostic messages in examples.
3. Keep changes focused. The core currently uses Python's standard library only.
4. Add a test when changing health classification or input validation.
5. Run `python -m unittest -v` and `python backup_report.py --demo`.
6. Open a pull request explaining the behavior change and how you verified it.

Do not include employer/customer exports, passwords, API keys, or personal information. If reporting a potential security issue publicly, provide a minimal synthetic example without sensitive data.

Ideas for later releases: vendor CSV adapters, better freshness reporting, configurable status mappings, and optional ticket drafts. No vendor API integration exists in v0.1.0.
