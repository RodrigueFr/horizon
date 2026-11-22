# menuproof

A small native test mod for Horizon (MIT, written from scratch against the mod SDK; no code from any
other mod). It exists to show, in the real game, the two pull requests on mod menus backed by a stack:

- horizon-rust/horizon#19593: a mod backs its menu's slots from the player's own turn (`use_item`).
- horizon-rust/horizon#19598: `MenuSlotPlace::ModItem`, a menu backed by a stack worn in a mod place.

## What it does (server side)

| Thing | How |
|---|---|
| The box | Vanilla's `minecraft:shulker_box`, given 27 slots through `ITEM_ITEMS` (`r.item_container`). |
| Box in hand (#19593) | Right click **in the air** with the box in the main hand: its `use_item` (an `ItemPart`) opens a 3-row chest menu (`open_menu`) and backs its 27 slots with the box's (`back_mod_menu_slots`, `MenuSlotPlace::HeldItem`). This runs inside the player's turn. |
| Back slot (#19598) | A `PlaceProvider` named `menuproof:back`: one back slot per player, kept in their inventory slot 17 (`inventory.8`, top-right of the main inventory). Put the box there with `/item replace entity @s inventory.8 with minecraft:shulker_box`. |
| `/menuproof back` | Opens a 3-row menu backed by the worn box (`MenuSlotPlace::ModItem { provider: "menuproof:back", .. }`). If the build refuses a backing inside the player's turn (a build without #19593), it backs it again at the end of the server tick, and says so in the log. |
| `/menuproof unequip` | Takes the box off the back slot through its place (`ItemPlace::Mod`) into inventory slot 26: the menu closes. |
| `/menuproof show` | Writes what the box in hand and the worn box hold to the chat and the log. |

Every step logs a `menuproof:` line (`log::info!`, in the game's log): the open, the backing's result, the
box's contents after each server tick where they changed (what the menu shows after the turn, after each
click), and the close. The client needs nothing from the mod: the menu is a plain chest menu.

## Build

The mod needs a Horizon SDK that has `MenuSlotPlace::ModItem` (#19598). For a build without it,
`tools/install_into.py --no-worn` copies the source without its `// worn-only` blocks (only the box in hand).
There is no Cargo feature for this: the launcher refuses a native mod that declares `[features]`
(`E_NATIVE_FEATURES`). `Cargo.lock` pins `log` 0.4.34, the version Horizon's workspace uses.

### Into a Horizon checkout, as the repository's own mod game crates are built (Linux, used for the proofs)

```sh
python3 tools/install_into.py /path/to/horizon-checkout          # --no-worn for a build without #19598
cd /path/to/horizon-checkout
cargo build --profile fast -p menuproof-game -p horizon-client-lib --bin menuproof-game --bin horizon-ctl
```

`install_into.py` copies `src/` to `crates/menuproof/`, writes `crates/menuproof-game/` (the `main` the
launcher generates, with one mod: `ModEntry::new("menuproof", menuproof::hooks())` and its `BuiltMod`), and
adds both to the workspace. The executable checks a package beside it, `horizon-native-mods/menuproof/`
(this folder's `horizon-mod.toml`, a `Cargo.toml` and a `src/`); `tools/proof_e2e.py` writes it.

### As a standalone native mod (launcher route, e.g. for a Windows build)

The crate's `Cargo.toml` points at the SDK where the mod tool fetches it, `.horizon/sdk/api/crates/horizon-mod-api`,
as Vast Packs does. `horizon-mod.toml`'s `[native] horizon` must be the commit of the Horizon build it is
installed into (one with #19598); the value here is the local proof branch `preuves/all`
(`cdddef069843f9cf0c70e42b24844310ab35875d`), which is not published. `mixins` is Vast Packs' value
(`e59da9094f0c2fdda6c627fe9eff22dec6a906f0`), which the PC build was packaged with. The entry point is `menuproof::hooks()`.

## Run the proofs

```sh
Xvfb :77 -screen 0 1280x720x24 &
DISPLAY=:77 VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json \
  python3 tools/proof_e2e.py --tree /path/to/horizon-checkout --bins $CARGO_TARGET_DIR/fast \
  --resources /path/to/.local/horizon-client/26.3 --scenario held-solo --out out/held-solo
```

Scenarios: `held-solo`, `held-lan` (on the LAN host, then on its guest), `worn-solo`, `worn-lan` (on a LAN guest).
Each writes `results.json` (every check, passed or not, with what was seen), the games' logs, their
`menuproof:` lines alone, and screenshots.

## Licence

MIT (see LICENSE).
