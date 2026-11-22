//! menuproof: a small native test mod that exercises mod menus backed by a stack's contents.
//!
//! - **The box in hand** (`MenuSlotPlace::HeldItem`, horizon-rust/horizon#19593). A right click with a
//!   shulker box in the main hand, in the air, opens a 3-row chest menu from the item's `use_item`, on the
//!   server, during the player's own turn, and backs its 27 slots with the box's own 27 slots.
//! - **The box worn on the back** (`MenuSlotPlace::ModItem`, horizon-rust/horizon#19598). The mod registers
//!   a `PlaceProvider`, `menuproof:back`: one back slot per player, kept in their inventory slot 17
//!   (`inventory.8`, the main inventory's top-right slot), which a chest menu shows as its slot 35. The
//!   command `/menuproof back` opens a 3-row menu backed by the worn box's 27 slots.
//!   `/menuproof unequip` takes the box off its back slot through the place (`ItemPlace::Mod`) and puts it
//!   in inventory slot 26, which closes the menu at the write's change notice.
//! - `/menuproof show` writes what both boxes hold to the chat and the log.
//!
//! Every step and every result goes to the game's log as a `menuproof:` line, and after each server tick
//! the contents of the box behind each open proof menu are logged when they changed: what the box holds
//! after the turn that opened the menu, and after each click.

use mod_api::{
    Command, CommandSource, Flow, Hand, HostSide, HostTransaction, Hooks, InteractionResult, ItemPart, ItemPlace,
    ItemResource, ItemStack, MenuClosedEvent, MenuReplace, MenuSlotPlace, PlaceProvider,
    RegisterCommandsEvent, Registrar, RegistrationContext, RunModCommandEvent, ServerHost,
    ServerTickEvent, ServerTickPhase, Text, Transaction, UseItemEvent,
};
use std::collections::HashMap;
use std::sync::Mutex;

/// The item used as the box: vanilla's shulker box, given 27 slots through `ITEM_ITEMS`.
const BOX: &str = "minecraft:shulker_box";
/// The box's slots, and the menu's container slots.
const SLOTS: usize = 27;
/// The back slots' place provider.
const BACK: &str = "menuproof:back";
/// The inventory slot a player's back slot is kept in (`inventory.8`; menu slot 35 of a 3-row chest menu).
const BACK_SLOT: i32 = 17;
/// Where `/menuproof unequip` puts the box (`inventory.17`).
const UNEQUIP_SLOT: i32 = 26;

/// The players who have a back slot, by key: the key is the index.
static PLAYERS: Mutex<Vec<u128>> = Mutex::new(Vec::new());

fn key_of(uuid: u128) -> u64 {
    let mut players = PLAYERS.lock().unwrap();
    let index = players.iter().position(|p| *p == uuid).unwrap_or_else(|| {
        players.push(uuid);
        players.len() - 1
    });
    index as u64
}

fn uuid_of(key: u64) -> Option<u128> {
    PLAYERS.lock().unwrap().get(key as usize).copied()
}

/// Where back slot `key` keeps its stack.
fn back_store(key: u64) -> Option<ItemPlace> {
    Some(ItemPlace::PlayerSlot {
        player: uuid_of(key)?,
        slot: BACK_SLOT,
    })
}

/// `menuproof:back`, an accessory mod's back slot ([`ItemPlace::Mod`]).
struct BackSlot;

impl PlaceProvider for BackSlot {
    fn stack(&self, host: &mut dyn ServerHost, key: u64) -> Option<ItemStack> {
        back_store(key)?.stack(host)
    }
    fn insert(
        &self,
        host: &mut dyn ServerHost,
        tx: &Transaction,
        key: u64,
        resource: &ItemResource,
        amount: u32,
    ) -> u32 {
        back_store(key).map_or(0, |place| place.insert(host, tx, resource, amount))
    }
    fn extract(
        &self,
        host: &mut dyn ServerHost,
        tx: &Transaction,
        key: u64,
        resource: &ItemResource,
        amount: u32,
    ) -> u32 {
        back_store(key).map_or(0, |place| place.extract(host, tx, resource, amount))
    }
}

/// Which box a proof menu shows.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Kind {
    Held,
    Worn,
}

/// An open proof menu: its kind, and the last contents logged.
struct Open {
    kind: Kind,
    logged: Option<String>,
}

#[derive(Default)]
struct MenuProof {
    /// The proof menus open, by player and window.
    open: Mutex<HashMap<(u128, i32), Open>>,
    /// Worn-box menus whose backing was refused inside the player's turn, backed again at the end of
    /// the server tick, where nobody's state is swapped in.
    retry: Mutex<Vec<(u128, i32)>>,
}

/// The place of the box behind a `kind` menu of player `uuid`.
fn box_place(uuid: u128, kind: Kind) -> ItemPlace {
    match kind {
        Kind::Held => ItemPlace::PlayerHand {
            player: uuid,
            hand: Hand::Main,
        },
        Kind::Worn => ItemPlace::Mod {
            provider: BACK,
            key: key_of(uuid),
        },
    }
}

fn places(uuid: u128, kind: Kind) -> Vec<MenuSlotPlace> {
    (0..SLOTS)
        .map(|slot| match kind {
            Kind::Held => MenuSlotPlace::HeldItem {
                hand: Hand::Main,
                slot,
            },
            // MenuSlotPlace::ModItem is horizon-rust/horizon#19598's. For a build without it,
            // tools/install_into.py --no-worn swaps each `worn-only` block for its `without-worn` line.
            // worn-only: begin
            Kind::Worn => MenuSlotPlace::ModItem {
                provider: BACK,
                key: key_of(uuid),
                slot,
            },
            // worn-only: end
            // without-worn: Kind::Worn => unreachable!("built without MenuSlotPlace::ModItem"),
        })
        .collect()
}

/// The items the proof runs use, to name them in the log (the server has no item names).
const NAMED: [&str; 7] = [
    "minecraft:stone",
    "minecraft:dirt",
    "minecraft:cobblestone",
    "minecraft:oak_planks",
    "minecraft:diamond",
    "minecraft:torch",
    BOX,
];

fn describe(host: &dyn ServerHost, stack: &ItemStack) -> String {
    let name = NAMED
        .iter()
        .find(|id| {
            mod_api::Identifier::parse(id).ok().and_then(|id| host.item_key(&id)) == Some(stack.item())
        })
        .map_or_else(|| format!("{:?}", stack.item()), |id| (*id).to_owned());
    format!("{name} x{}", stack.count())
}

/// Whether `stack` is a box.
fn is_box(host: &dyn ServerHost, stack: &ItemStack) -> bool {
    let id = mod_api::Identifier::parse(BOX).ok();
    id.and_then(|id| host.item_key(&id)) == Some(stack.item())
}

/// What the box at `place` holds: `slot=item xN` for each filled slot, or why there is none.
fn contents(host: &mut dyn ServerHost, place: &ItemPlace) -> String {
    let Some(stack) = place.stack(host) else {
        return "no box there".to_owned();
    };
    if !is_box(host, &stack) {
        return format!("not a box: {}", describe(host, &stack));
    }
    let filled: Vec<String> = (0..SLOTS)
        .filter_map(|slot| {
            let inner = ItemPlace::Nested {
                parent: Box::new(place.clone()),
                slot,
            };
            inner.stack(host).map(|s| format!("{slot}={}", describe(host, &s)))
        })
        .collect();
    if filled.is_empty() {
        "empty".to_owned()
    } else {
        filled.join(", ")
    }
}

impl MenuProof {
    /// Opens a `kind` menu for `uuid` and backs it. `in_turn` says whether this runs in the player's turn.
    fn open(&self, host: &mut dyn ServerHost, uuid: u128, kind: Kind, from: &str) -> bool {
        let title = match kind {
            Kind::Held => "menuproof: box in hand",
            Kind::Worn => "menuproof: box on the back",
        };
        let place = box_place(uuid, kind);
        log::info!(
            "menuproof: {from}: opening the {kind:?} box menu; the box holds [{}]",
            contents(host, &place)
        );
        let window = match host.open_menu(
            uuid,
            3,
            Text::literal(title),
            Vec::new(),
            MenuReplace::CloseFirst,
        ) {
            Ok(Some(window)) => window,
            other => {
                log::info!("menuproof: {from}: open_menu refused: {other:?}");
                return false;
            }
        };
        let Some(player) = host.player(uuid) else {
            log::info!("menuproof: {from}: no player");
            return false;
        };
        let result = player.back_mod_menu_slots(host, window, places(uuid, kind));
        log::info!("menuproof: {from}: window {window} back_mod_menu_slots({kind:?} x{SLOTS}) = {result:?}");
        // A build without horizon-rust/horizon#19593 refuses a backing from inside the player's turn (a
        // command's): the worn box's menu is then backed after the tick. The box in hand never retries:
        // its `use_item` backing is what #19593 is about.
        if kind == Kind::Worn && result == Err(mod_api::MenuSlotBackRefusal::NoPlayerOrWindow) {
            log::info!("menuproof: {from}: refused inside the turn; backing window {window} again after the tick");
            self.retry.lock().unwrap().push((uuid, window));
            self.open.lock().unwrap().insert((uuid, window), Open { kind, logged: None });
            return true;
        }
        if result.is_err() {
            host.close_menu(uuid);
            log::info!("menuproof: {from}: menu closed, not backed");
            return false;
        }
        self.open.lock().unwrap().insert(
            (uuid, window),
            Open {
                kind,
                logged: None,
            },
        );
        true
    }
}

/// The box's item: a right click in the air with it in the main hand opens its menu.
struct BoxPart {
    proof: &'static MenuProof,
}

#[mod_api::horizon_part]
impl ItemPart for BoxPart {
    fn use_item(&self, host: HostSide, event: &mut UseItemEvent<'_>) -> Option<InteractionResult> {
        if event.hand != Hand::Main {
            return None;
        }
        match host {
            HostSide::Server(host) => {
                self.proof.open(host, event.player, Kind::Held, "use_item");
                Some(InteractionResult::SuccessServer)
            }
            HostSide::Client(_) => Some(InteractionResult::Success),
        }
    }
}

/// The mod's one instance, which the item part also reaches.
static PROOF: std::sync::LazyLock<MenuProof> = std::sync::LazyLock::new(MenuProof::default);

/// The mod: register with `ModEntry::new("menuproof", menuproof::hooks())`.
pub fn hooks() -> Box<dyn Hooks> {
    Box::new(Entry)
}

struct Entry;

#[mod_api::__subscriptions]
impl Hooks for Entry {
    fn register(&self, r: &mut dyn Registrar, _: &RegistrationContext) {
        let key = r.item_key(BOX);
        r.item_container(&key, |_: &dyn mod_api::Host| Some(SLOTS as u32));
        r.item_part(key, BoxPart { proof: &PROOF });
        r.place_provider(BACK, std::sync::Arc::new(BackSlot));
    }

    fn register_commands(&self, _: &mut dyn ServerHost, event: &mut RegisterCommandsEvent<'_>) {
        event.commands.extend([
            Command::new("menuproof back"),
            Command::new("menuproof unequip"),
            Command::new("menuproof show"),
        ]);
    }

    fn run_mod_command(&self, host: &mut dyn ServerHost, event: &mut RunModCommandEvent<'_>) -> Flow {
        if event.command.literals.first().map(String::as_str) != Some("menuproof") {
            return Flow::Continue;
        }
        let CommandSource::Player { player, .. } = event.source else {
            return Flow::Continue;
        };
        let uuid = player.uuid();
        let line = match event.command.literals.get(1).map(String::as_str) {
            // worn-only: begin
            Some("back") => {
                let opened = PROOF.open(host, uuid, Kind::Worn, "/menuproof back");
                format!("menuproof: back menu opened and backed: {opened}")
            }
            // worn-only: end
            // without-worn: Some("back") => "menuproof: built without MenuSlotPlace::ModItem".to_owned(),
            Some("unequip") => unequip(host, uuid),
            Some("show") => format!(
                "menuproof: hand [{}]; back [{}]",
                contents(host, &box_place(uuid, Kind::Held)),
                contents(host, &box_place(uuid, Kind::Worn))
            ),
            _ => return Flow::Continue,
        };
        log::info!("{line}");
        let _ = host.commands().feedback(Text::literal(line));
        Flow::Cancel
    }

    /// After each server tick, the contents of each open proof menu's box, when they changed.
    fn server_tick(&self, host: &mut dyn ServerHost, event: &mut ServerTickEvent<'_>) {
        if !matches!(event.phase, ServerTickPhase::ServerTickEnd { .. }) {
            return;
        }
        let retry = std::mem::take(&mut *PROOF.retry.lock().unwrap());
        for (uuid, window) in retry {
            let result = host
                .player(uuid)
                .map(|player| player.back_mod_menu_slots(host, window, places(uuid, Kind::Worn)));
            log::info!("menuproof: after the tick: window {window} back_mod_menu_slots(Worn x{SLOTS}) = {result:?}");
            if !matches!(result, Some(Ok(()))) {
                PROOF.open.lock().unwrap().remove(&(uuid, window));
                host.close_menu(uuid);
            }
        }
        let open: Vec<((u128, i32), Kind, Option<String>)> = PROOF
            .open
            .lock()
            .unwrap()
            .iter()
            .map(|(k, o)| (*k, o.kind, o.logged.clone()))
            .collect();
        for ((uuid, window), kind, logged) in open {
            let now = contents(host, &box_place(uuid, kind));
            let shown = host.menu(uuid, window).map(|menu| {
                let filled: Vec<String> = (0..SLOTS)
                    .filter_map(|slot| {
                        ItemPlace::MenuSlot { menu, slot }
                            .stack(host)
                            .map(|s| format!("{slot}={}", describe(host, &s)))
                    })
                    .collect();
                filled.join(", ")
            });
            let line = format!("box [{now}]; menu slots [{}]", shown.unwrap_or_else(|| "menu gone".into()));
            if logged.as_deref() != Some(line.as_str()) {
                log::info!("menuproof: after tick: window {window} ({kind:?}) {line}");
                if let Some(o) = PROOF.open.lock().unwrap().get_mut(&(uuid, window)) {
                    o.logged = Some(line);
                }
            }
        }
    }

    fn menu_closed(&self, host: &mut dyn ServerHost, event: &mut MenuClosedEvent) {
        if let Some(open) = PROOF.open.lock().unwrap().remove(&(event.uuid, event.window)) {
            let kind = open.kind;
            log::info!(
                "menuproof: menu_closed: window {} ({kind:?}); the box holds [{}]",
                event.window,
                contents(host, &box_place(event.uuid, kind))
            );
        }
    }
}

/// Takes the box off the player's back slot, through its place, into inventory slot 26.
fn unequip(host: &mut dyn ServerHost, uuid: u128) -> String {
    let worn = box_place(uuid, Kind::Worn);
    let Some(resource) = worn.resource(host) else {
        return "menuproof: unequip: nothing on the back".to_owned();
    };
    let to = ItemPlace::PlayerSlot {
        player: uuid,
        slot: UNEQUIP_SLOT,
    };
    let moved = host.transaction(|host, tx| {
        let taken = worn.extract(host, tx, &resource, 1);
        if taken != 1 || to.insert(host, tx, &resource, 1) != 1 {
            return Err(taken);
        }
        Ok(())
    });
    format!("menuproof: unequip: box moved from the back slot to inventory slot {UNEQUIP_SLOT}: {moved:?}")
}
