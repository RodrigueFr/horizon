#!/usr/bin/env python3
"""menuproof end to end: the real game, headless, with the menuproof native mod built in.

    python3 tools/proof_e2e.py --tree WORKTREE --bins TARGET/fast --scenario held-solo --out DIR

WORKTREE is a Horizon checkout where tools/install_into.py put menuproof (its tools/ are imported:
lan_e2e.Game, agent_control_e2e.Cli); --bins holds `menuproof-game` and `horizon-ctl`. Each game runs in
a scratch folder as tools/lan_e2e.py runs its two games (offscreen, no pause, its own HORIZON_HOME), from
a copy of the executable with the mod's `horizon-native-mods/menuproof` package beside it, as
tools/mod_dimensions_e2e.py does.

Scenarios:
- held-solo / held-lan (#19593): a shulker box (27 slots through ITEM_ITEMS) holding 5 dirt in its slot
  4 is held in the main hand; a right click in the air opens the mod's menu from the item's `use_item`,
  which backs its slots with the box's (`MenuSlotPlace::HeldItem`). The client's menu shows the dirt after
  the turn; a shift-click moves 64 stone from the inventory into the box, a pickup click moves it on to the
  box's slot 9; closed and reopened, the box keeps it. held-lan does this on the LAN host while a guest is
  connected, then on the guest.
- worn-solo / worn-lan (#19598): the box (3 dirt in its slot 2) is worn in the mod's back slot (a
  `PlaceProvider` keeping it in inventory slot 17); `/menuproof back` opens a menu backed by it
  (`MenuSlotPlace::ModItem`); a shift-click fills it with 64 stone; clicking the box's own slot (17), as a
  pickup and as a shift-click, does nothing; `/menuproof unequip` takes it off the back slot through its
  place and the menu closes. worn-lan does this on a LAN guest (with the host on its server thread).
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

MANIFEST = """id = 'menuproof'
name = 'menuproof'
version = '0.1.0'
api = '0.2'
side = 'both'
capabilities = ['registries']
[native]
game = '26.3'
horizon = '{horizon}'
mixins = '{mixins}'
"""

HELD_BOX = 'minecraft:shulker_box[container=[{slot:4,item:{id:"minecraft:dirt",count:5}}]]'
WORN_BOX = 'minecraft:shulker_box[container=[{slot:2,item:{id:"minecraft:dirt",count:3}}]]'
CONTAINER = 300  # horizon-ctl's id of a menu's first container slot; player slots keep their inventory ids


class Check:
    def __init__(self, out, name):
        self.out, self.name, self.rows = out, name, []

    def __call__(self, what, ok, seen=None):
        self.rows.append({'check': what, 'pass': bool(ok), 'seen': seen})
        print(f'[{self.name}] {"PASS" if ok else "FAIL"} {what}: {json.dumps(seen)[:300]}')
        return ok


def box_slots(game):
    """The open menu's container slots that hold something: {box slot: (item, count)}, and the screen."""
    screen = game('screen')
    slots = {s['slot'] - CONTAINER: (s.get('item'), s.get('count'))
             for s in screen.get('slots', []) if CONTAINER <= s.get('slot', 0) < CONTAINER + 27 and s.get('item')}
    return slots, screen


def player_slot(game, n):
    s = next((s for s in game('screen').get('slots', []) if s.get('slot') == n), None)
    return (s.get('item'), s.get('count')) if s and s.get('item') else None


def chat(game, line, expect=None):
    """Runs a command; with `expect`, its feedback line (a LAN guest's reply comes back as chat, after the
    command's answer: `wait-for chat` catches it)."""
    since = game.raw('events')['last']
    reply = game('command', command=line)
    if expect and not any(expect in c for c in reply.get('chat') or []):
        seen = game.raw('wait-for', 'chat', expect, '--timeout', 10, '--since', since).get('ok')
        # `wait-for chat` answers ok: true once a line holding `expect` arrived.
        reply = dict(reply, chat=[f'(wait-for chat) {expect}'] if seen is True else [])
    game.wait(5)
    return reply


def setup_player(game):
    chat(game, 'gamemode survival')
    chat(game, 'clear @s')
    # A clear sky over the player: the right click is a use in the air, not a placement.
    chat(game, 'tp @s ~ 200 ~')
    chat(game, 'fill ~-1 ~-1 ~-1 ~1 ~-1 ~1 minecraft:glass')
    game.raw('look', 0, -90)


def held(game, out, check, tag):
    setup_player(game)
    chat(game, f'item replace entity @s hotbar.0 with {HELD_BOX}')
    chat(game, 'item replace entity @s inventory.0 with minecraft:stone 64')  # inventory slot 9
    game('select', slot=1)
    game.wait(5)
    game('use_item')
    game.wait(10)
    slots, screen = box_slots(game)
    check(f'{tag}: the menu opened from use_item', screen.get('screen') not in ('playing', None), screen.get('screen'))
    check(f'{tag}: after the turn the menu shows the box (5 dirt in its slot 4)', slots == {4: ('minecraft:dirt', 5)}, slots)
    game.shot(out, f'{tag}-1-opened')
    game.raw('click-slot', 9, 'shift')
    game.wait(5)
    slots, _ = box_slots(game)
    check(f'{tag}: a shift-click moves the 64 stone into the box', slots == {0: ('minecraft:stone', 64), 4: ('minecraft:dirt', 5)}, slots)
    check(f'{tag}: the stone left the inventory', player_slot(game, 9) is None, player_slot(game, 9))
    game.raw('click-slot', CONTAINER + 0)
    game.wait(3)
    game.raw('click-slot', CONTAINER + 9)
    game.wait(5)
    slots, screen = box_slots(game)
    check(f'{tag}: a pickup click moves the stone on to the box\'s slot 9', slots == {9: ('minecraft:stone', 64), 4: ('minecraft:dirt', 5)}, slots)
    check(f'{tag}: the cursor is empty', not screen.get('carried'), screen.get('carried'))
    game.shot(out, f'{tag}-2-after-clicks')
    shown = chat(game, 'menuproof show', 'menuproof: hand [4=minecraft:dirt x5, 9=minecraft:stone x64]')
    check(f'{tag}: the server\'s box holds it (menuproof show)', 'Stone' in json.dumps(shown) or 'stone x64' in json.dumps(shown), shown.get('chat'))
    game('close')
    game.wait(10)
    inv = game('inventory')
    check(f'{tag}: closed, the box is still in the hand', (inv.get('hotbar') or [None])[0] and inv['hotbar'][0].get('item') == 'minecraft:shulker_box', (inv.get('hotbar') or [None])[0])
    game('use_item')
    game.wait(10)
    slots, _ = box_slots(game)
    check(f'{tag}: reopened, the box kept the stone and the dirt', slots == {9: ('minecraft:stone', 64), 4: ('minecraft:dirt', 5)}, slots)
    game.shot(out, f'{tag}-3-reopened')
    game('close')
    game.wait(5)


def worn(game, out, check, tag):
    setup_player(game)
    chat(game, f'item replace entity @s inventory.8 with {WORN_BOX}')  # inventory slot 17: the back slot
    chat(game, 'item replace entity @s inventory.0 with minecraft:stone 64')  # inventory slot 9
    game('select', slot=1)
    reply = chat(game, 'menuproof back', 'menuproof: back menu opened and backed: true')
    game.wait(10)
    slots, screen = box_slots(game)
    check(f'{tag}: /menuproof back opened a backed menu', 'true' in json.dumps(reply.get('chat')) and screen.get('screen') not in ('playing', None), [reply.get('chat'), screen.get('screen')])
    check(f'{tag}: the menu shows the worn box (3 dirt in its slot 2)', slots == {2: ('minecraft:dirt', 3)}, slots)
    game.shot(out, f'{tag}-1-opened')
    game.raw('click-slot', 9, 'shift')
    game.wait(5)
    slots, _ = box_slots(game)
    check(f'{tag}: a shift-click fills the box with the 64 stone', slots == {0: ('minecraft:stone', 64), 2: ('minecraft:dirt', 3)}, slots)
    check(f'{tag}: the stone left the inventory', player_slot(game, 9) is None, player_slot(game, 9))
    game.shot(out, f'{tag}-2-shift-clicked')
    for how in ([], ['shift'], ['right']):
        game.raw('click-slot', 17, *how)
        game.wait(5)
        slots, screen = box_slots(game)
        label = ' '.join(how) or 'pickup'
        check(f'{tag}: a {label} click on the box\'s own slot does nothing: the box stays in slot 17',
              player_slot(game, 17) == ('minecraft:shulker_box', 1), player_slot(game, 17))
        check(f'{tag}: ... the cursor stays empty and the menu open', not screen.get('carried') and screen.get('screen') not in ('playing', None),
              [screen.get('carried'), screen.get('screen')])
        check(f'{tag}: ... and the box keeps its contents', slots == {0: ('minecraft:stone', 64), 2: ('minecraft:dirt', 3)}, slots)
    game.shot(out, f'{tag}-3-own-slot-clicked')
    reply = chat(game, 'menuproof unequip', 'inventory slot 26: Ok(())')
    game.wait(10)
    screen = game('screen')
    check(f'{tag}: removing the box from its place closes the menu', screen.get('screen') == 'playing', [reply.get('chat'), screen.get('screen')])
    shown = chat(game, 'menuproof show', 'back [no box there]')
    check(f'{tag}: the back slot is empty afterwards', 'back [no box there]' in json.dumps(shown.get('chat')), shown.get('chat'))
    inv = game('inventory')
    moved = [s for s in (inv.get('main') or []) if s and s.get('slot') == 26]
    check(f'{tag}: the box, with its contents, is in inventory slot 26', bool(moved) and moved[0].get('item') == 'minecraft:shulker_box', moved)
    game.shot(out, f'{tag}-4-removed')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tree', required=True)
    p.add_argument('--bins', required=True)
    p.add_argument('--resources', default=os.environ.get('HORIZON_TEST_RESOURCES'))
    p.add_argument('--scenario', required=True, choices=['held-solo', 'held-lan', 'worn-solo', 'worn-lan'])
    p.add_argument('--out', required=True)
    args = p.parse_args()
    tree = Path(args.tree).resolve()
    sys.path.insert(0, str(tree / 'tools'))
    import lan_e2e  # noqa: E402
    import lab  # noqa: E402
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    bins = Path(args.bins).resolve()
    resources = Path(args.resources).resolve()
    # The game beside its package, as the launcher installs a native build.
    folder = Path(tempfile.mkdtemp(prefix='menuproof-bin-'))
    package = folder / 'horizon-native-mods/menuproof'
    (package / 'src').mkdir(parents=True)
    commit = os.popen(f'git -C {tree} rev-parse HEAD').read().strip()
    (package / 'horizon-mod.toml').write_text(MANIFEST.format(horizon=commit, mixins='e59da9094f0c2fdda6c627fe9eff22dec6a906f0'))
    (package / 'Cargo.toml').write_text("[package]\nname = 'menuproof'\nversion = '0.1.0'\n")
    (package / 'src/lib.rs').write_text('// Built into the executable.\n')
    game_bin = folder / 'horizon-client'
    shutil.copy2(bins / 'menuproof-game', game_bin)
    ctl = bins / 'horizon-ctl'
    launch = ['launch', '--game', game_bin, '--offscreen', '--no-pause']
    check = Check(out, args.scenario)
    host = lan_e2e.Game('host', ctl, resources)
    guest = lan_e2e.Game('guest', ctl, resources) if args.scenario.endswith('-lan') else None
    started = time.time()
    try:
        host.pid = host.raw(*launch)['pid']
        host.raw('open', 'W', 5, 'creative')
        host('wait_ready', seconds=400)
        host('command', command='time set day')
        host('command', command='gamerule spawn_mobs false')
        if guest:
            port = host.raw('lan', 'open', 0, 'commands')['port']
            guest.pid = guest.raw(*launch)['pid']
            guest.raw('connect', f'127.0.0.1:{port}', lan_e2e.GUEST_NAME)
            guest.raw('wait-for', 'loaded', '--timeout', 300)
            guest.wait(40)
        if args.scenario == 'held-solo':
            held(host, out, check, 'single-player')
        elif args.scenario == 'held-lan':
            held(host, out, check, 'lan-host')
            held(guest, out, check, 'lan-guest')
        elif args.scenario == 'worn-solo':
            worn(host, out, check, 'single-player')
        else:
            worn(guest, out, check, 'lan-guest')
    except Exception as e:  # noqa: BLE001 - recorded as a failed check, logs still saved
        check('the scenario ran to its end', False, repr(e)[:600])
    finally:
        for g in [x for x in (guest, host) if x]:
            log = g.close()
            (out / f'{g.name}-console.log').write_text(log)
            # The game's own log (log::info!, the mod's lines among them), in its HORIZON_HOME.
            latest = g.work / 'home/logs/latest.log'
            text = latest.read_text(errors='replace') if latest.exists() else ''
            (out / f'{g.name}-latest.log').write_text(text)
            (out / f'{g.name}-menuproof.log').write_text(
                '\n'.join(line for line in text.splitlines() if 'menuproof' in line) + '\n')
            shutil.rmtree(g.work, ignore_errors=True)
        shutil.rmtree(folder, ignore_errors=True)
    result = {'scenario': args.scenario, 'tree': str(tree), 'commit': commit, 'seconds': round(time.time() - started),
              'pass': bool(check.rows) and all(r['pass'] for r in check.rows), 'checks': check.rows}
    (out / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('scenario', 'commit', 'pass')}))
    sys.exit(0 if result['pass'] else 1)


if __name__ == '__main__':
    main()
