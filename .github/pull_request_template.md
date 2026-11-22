## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## How I checked it

<!-- Tests you ran, builds, and screenshots for anything you can see (light and dark, Mac and/or Windows). -->

## Checklist

- [ ] The unit tests pass (`python3 -B -m unittest app.tests.test_bridge app.tests.test_setup app.tests.test_data_folder app.tests.test_what_ships app.tests.test_update app.tests.test_address_search app.tests.test_topic_search app.tests.test_validate_topics app.tests.test_libq app.tests.test_video_transcripts app.tests.test_video_moments app.tests.test_library_extract`).
- [ ] Localization changes pass the catalogue and engine checks. [Commands](../docs/i18n.md#verification)
- [ ] No new network access: no port, socket, web address in `web/`, telemetry, automatic update check or new allowed host. Network use only through `engine/setup/download.py`.
- [ ] No personal or household details: no home area, coordinates, user or machine names, LAN addresses, keys or tokens.
- [ ] Guide changes cite real pages in the library, and `tools/validate_topics.py` passes.
- [ ] Any new dependency is offline-only and listed in `THIRD_PARTY_NOTICES.md` with its licence.
