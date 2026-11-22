# Evidence for horizon-rust/horizon#19593 and #19598

In-game evidence requested in review, produced with the real game run headless (Xvfb, software Vulkan)
and driven by `horizon-ctl`, the way `tools/lan_e2e.py` drives its games.

- `menuproof/`: the small native test mod used for it (MIT). It opens a menu from `use_item` backed by
  the held box (`MenuSlotPlace::HeldItem`, #19593), and a menu backed by a box worn in a `PlaceProvider`
  slot (`MenuSlotPlace::ModItem`, #19598). `menuproof/tools/proof_e2e.py` runs the scenarios;
  `menuproof/README.md` explains how to build and run it.
- `evidence/19593/` and `evidence/19598/`: per scenario (single player, LAN host, LAN guest; the PR's
  branch, a control branch without #19593, and a local merge of #19593 + #19595 + #19598), the client
  action log, the mod's server log lines and a screenshot of each step. The `README.md` in each folder
  gives the exact commit and command (written in French).

This branch is not meant to be merged; it only holds the evidence.
