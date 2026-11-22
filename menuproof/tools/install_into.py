#!/usr/bin/env python3
"""Plug menuproof into a Horizon checkout as a game crate, as crates/horizon-mod-dimension-game does.

    python3 tools/install_into.py /path/to/horizon-worktree [--no-worn]

--no-worn copies the mod without its `worn-only` blocks (each swapped for its `without-worn` line), for a
Horizon build without MenuSlotPlace::ModItem (before horizon-rust/horizon#19598): only the box in hand is
there. (No Cargo feature: the launcher refuses a native mod that declares features, E_NATIVE_FEATURES.)

Writes, in the checkout:
- crates/menuproof/: a copy of this mod (src/, Cargo.toml with the SDK path pointing at ../horizon-mod-api);
- crates/menuproof-game/: the executable the launcher's generated `main` would build, with one native mod,
  menuproof (binary `menuproof-game`);
and adds both to the workspace's members. Build with
    cargo build --profile fast -p menuproof-game -p horizon-client-lib --bin menuproof-game --bin horizon-ctl
The game then needs `horizon-native-mods/menuproof/` (this folder's horizon-mod.toml) beside the
executable, which tools/proof_e2e.py writes.
"""
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]

GAME_TOML = """[package]
name = "menuproof-game"
version = "0.1.0"
edition.workspace = true
license.workspace = true
publish = false
description = "The game with one native mod, menuproof (proof runs for mod menus backed by a stack)"

[[bin]]
name = "menuproof-game"
path = "src/main.rs"
test = false

[dependencies]
horizon-client = { path = "../horizon-client" }
horizon-mod-api = { path = "../horizon-mod-api" }
horizon-mod-host = { path = "../horizon-mod-host" }
menuproof = { path = "../menuproof" }
"""

GAME_MAIN = """//! The game with one native mod, menuproof, built as the launcher's generated `main` is (see
//! crates/horizon-mod-dimension-game). Needs `horizon-native-mods/menuproof` beside the executable.
use mod_api::__private::native::BuiltMod;
use mod_api::{ModEntry, Side};

const BUILT: &[BuiltMod] = &[BuiltMod {
    id: "menuproof",
    version: "0.1.0",
    side: Side::Both,
}];

fn main() {
    horizon_mod_host::exit_if_compile_child();
    let startup = horizon_client::entry::prepare();
    horizon_mod_host::main_with(vec![ModEntry::new("menuproof", menuproof::hooks())], &[], BUILT, startup);
}
"""


def main():
    root = Path(sys.argv[1]).resolve()
    worn = '--no-worn' not in sys.argv[2:]
    assert (root / 'crates/horizon-mod-api').is_dir(), f'not a Horizon checkout: {root}'
    lib = root / 'crates/menuproof'
    shutil.rmtree(lib, ignore_errors=True)
    shutil.copytree(HERE / 'src', lib / 'src')
    if not worn:
        source = lib / 'src/lib.rs'
        text = re.sub(r'[ \t]*// worn-only: begin\n.*?// worn-only: end\n', '', source.read_text(), flags=re.S)
        text = re.sub(r'// without-worn: ', '', text)
        source.write_text(text)
    toml = (HERE / 'Cargo.toml').read_text()
    toml = toml.replace('.horizon/sdk/api/crates/horizon-mod-api', '../horizon-mod-api')
    toml = re.sub(r'edition = "2024"', 'edition.workspace = true', toml)
    (lib / 'Cargo.toml').write_text(toml)
    game = root / 'crates/menuproof-game'
    (game / 'src').mkdir(parents=True, exist_ok=True)
    (game / 'Cargo.toml').write_text(GAME_TOML)
    (game / 'src/main.rs').write_text(GAME_MAIN)
    ws = root / 'Cargo.toml'
    text = ws.read_text()
    anchor = '    "crates/horizon-mod-dimension-game",\n'
    for member in ('crates/menuproof', 'crates/menuproof-game'):
        if f'"{member}"' not in text:
            text = text.replace(anchor, anchor + f'    "{member}",\n', 1)
    ws.write_text(text)
    print(f'menuproof installed into {root}')


if __name__ == '__main__':
    main()
