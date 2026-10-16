# Milestone 8: Club finances

Milestone 8 adds a deterministic cash account and financial ledger for every
club. In the career menu, **10. Club finances** shows the account summary and
**11. Finance history** lists the latest 30 posted transactions.

## What changes cash

- Each club starts with 10,000,000 game units and the Milestone 7 transfer
  allowance. A transfer fee reduces the buyer's cash and credits the seller.
  Both clubs keep their separate transfer allowances.
- Player contracts carry a weekly wage. Existing squads receive a seeded-data
  wage estimate from player attributes; transfers and renewals let the manager
  set a wage.
- After a complete matchday, each club pays its registered squad's wages and
  receives sponsorship income. Home clubs earn ticket income and pay stadium
  operating costs.
- Attendance is a simple deterministic estimate based on capacity and current
  league position. Ticket prices, sponsorship, capacity, and operating costs
  are visible in the account screen.
- A completed matchday settles once. The ledger records each item, prevents
  duplicate settlement after load/resume, and permits debt when expenses exceed
  the current balance. A negative balance blocks transfer fees the club cannot
  afford.

Save format version 5 persists balances, account settings, financial
transactions, season-aware processed matchdays, and contract wages. Earlier save
formats are migrated; Milestone 7 transfer fees are carried into starting cash
balances. See [Milestone 9](milestone9.md) for multi-season operation.

The income model is prototype scale: attendance, wages, sponsorship, and stadium
costs are simple deterministic rules, not calibrated real-world club accounts.

Run the full test suite with:

```sh
python -m unittest discover -s tests -q
```
