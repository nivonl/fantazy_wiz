# Capturing 9cat.co.il's real API

`providers/cat9.py` is stubbed to a manual-JSON squad loader because the authenticated
endpoints aren't known yet. To fill in `Cat9Client` for real:

1. Open 9cat.co.il in a browser we control (the Claude Browser pane or Claude-in-Chrome) and
   log in with your account.
2. Navigate to the La Liga Classic Fantasy squad page (same pattern as the Premier League one
   found during exploration: `/en/football/classic-fantasy/pick-team/<la-liga-slug>` — the
   slug wasn't discoverable while logged out; it may be in a league switcher once logged in,
   or reachable straight from a "La Liga" nav item that only appears when the competition's
   window is open).
3. With the network tab open, note the XHR/fetch calls the page makes — looking for the
   equivalents of what `continuation-protocol.md` found on fantasy.one.co.il:
   - full player pool (id, name, team, position, price)
   - your saved squad (starting XI, bench, captain)
   - fixtures/gameweek deadline
4. Record the exact request URLs, required headers/cookies, and response shapes here, then
   implement `Cat9Client` in `providers/cat9.py` against them.

Until this is done, maintain your current La Liga squad in a JSON file matching
`providers.cat9.ManualSquad` (see `SAMPLE_SQUAD_JSON` in that module) and pass it to
`recommend/laliga.py` — nothing else in the pipeline depends on the source.
