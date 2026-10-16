# Milestone 9: Long-term world progression

Milestone 9 lets a local manager career continue across seasons. Clubs and the
league stay fixed; completed tables are archived while the next season gets a
new fixture schedule and deterministic seed.

## Manager workflow

After the last fixture, choose **12. Advance to next season**. The game records
the final table and champion, progresses player ages and abilities, retires
some older players, removes players whose contracts expired, and introduces a
youth intake. It also replenishes each club's annual transfer allowance. The
new season's pre-season transfer window then opens.

Choose **13. Season history** to review champions, final tables, retirements,
expired contracts, and generated youth players. Career saves preserve this
history and can resume partway through a later season.

## Progression rules

- Every season is a seeded home-and-away round robin with the same club IDs and
  league structure. Season seeds are derived from the preceding season seed.
- Players gain one year of age at each rollover. Attributes can improve for
  younger players based on their potential, remain mostly stable in their
  prime, and gradually decline with age. Development and retirement use stable
  per-player seeds for reproducible careers.
- Retirement chance rises from age 34; retirement is certain after age 39.
  Contracts expiring at the end of a season release the player. Vacancies are
  filled while preserving a legal squad, with at least one new youth player per
  club each season until registration reaches 25.
- New players are 16–19 years old, have generated attributes and potential, and
  receive a three-season contract. Retained contracts keep their absolute end
  season; renewals start in the current season.
- Club cash and the finance ledger carry forward. Settlements are keyed by
  season and matchday to prevent duplicate payments after a save is reloaded.

Save format version 5 stores player age and potential, season number, previous
season tables, youth and retirement records, and season-aware finance data.
Versions 1–4 remain loadable with sensible defaults for the fields they did not
store.

Run the complete validation suite with:

```sh
python -m unittest discover -s tests -q
```
