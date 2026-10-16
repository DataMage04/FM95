# Milestone 7: Squad operations

Milestone 7 adds local squad registration, basic contracts, transfer windows,
budget-limited transfers, and a persistent transfer log to the manager CLI.

## Use it

Start the CLI with `python -m fm95.manager`, load or start a career, then use:

- **View squad** to inspect the registered players and current match selection.
- **Transfer market** to browse players at other clubs and sign one for a fee.
- **View contracts / renew a contract** to inspect the manager club's contracts
  or renew one for one to five seasons.
- **Transfer history** to review completed moves.

Transfers sign the player to a new contract and register them with the buying
club automatically. Squad registration is limited to 25 players. Every club
must retain a goalkeeper and 10 outfield players so it can field a legal XI.

## Rules in this prototype

- The transfer window is open before the first matchday and at the halfway
  point of the fixture schedule. Transfer actions are only available between
  matchdays.
- Each club starts with a 2,000,000 game-unit transfer allowance. The manager
  enters the agreed fee; the move is rejected if the allowance or cash balance
  is too small.
- Existing players receive a basic three-season contract. New and renewed
  contracts can run for one to five seasons and include a weekly wage.
- Save format version 4 also stores Milestone 8 finances. Earlier save versions
  migrate with initial financial accounts; Milestone 7 transfer history is
  applied to the new cash balances.

Run the complete test suite with:

```sh
python -m unittest discover -s tests -q
```
