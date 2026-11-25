# Third-party OKF bundles (test fixtures)

`acme_retail/` and `crypto_bitcoin/` are copied unmodified (except that `viz.html` files
were not copied) from Google's Open Knowledge Format reference repository:

- Repository: https://github.com/GoogleCloudPlatform/knowledge-catalog (directory `okf/bundles/`)
- Commit: `62651738dab0b497b0e3fd804c87bcd235f027b8` (2026-08-21)
- Licence: Apache License 2.0 (`LICENSE.md` in this directory)

They are used only as independently produced bundles for the OKF consumer's
interoperability tests (`tests/test_knowledge/test_okf.py`). Nothing in them is executed.
