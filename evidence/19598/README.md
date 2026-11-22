# Preuves en jeu, PR #19598 (MenuSlotPlace::ModItem)

Même méthode que pour #19593 (voir `../19593/README.md`) : jeu complet sans écran, `horizon-ctl`,
classe `Game` de `tools/lan_e2e.py`, mod `menuproof` compilé dans le jeu.

Le mod déclare un `PlaceProvider` `menuproof:back` : une case « dos » par joueur, rangée dans sa case
d'inventaire 17 (comme le test de la PR, qui range la sienne dans l'inventaire), donc visible dans le menu.
Scénario `worn-*` : boîte avec 3 terre en case 2 portée au dos ; 64 pierre en case 9 ; `/menuproof back`
→ `open_menu` + `back_mod_menu_slots(ModItem x27)` → shift-clic (la pierre remplit la boîte) → clic,
shift-clic et clic droit sur la case 17 (la boîte elle-même) : rien ne bouge, curseur vide, menu ouvert →
`/menuproof unequip` (extraction par `ItemPlace::Mod`, vers la case 26) → le menu se ferme ; la boîte
garde son contenu.

| Dossier | Arbre (commit exact) | Commande | Résultat |
|---|---|---|---|
| `branche-19598/solo` | `preuves/19598` = 692eaa9625 + 3fba8b7aa1 (ajoute seulement le mod) | `proof_e2e.py --scenario worn-solo` | 16/16 OK |
| `branche-19598/lan-invite` | idem | `--scenario worn-lan` (sur l'invité LAN, hôte sur son fil serveur) | 16/16 OK |
| `fusion-3-pr/solo` | `preuves/all` = fusion #19593+#19595+#19598 (cdddef0698) + mod, 6868bdaf8e | `--scenario worn-solo` | 16/16 OK |
| `fusion-3-pr/lan-invite` | idem | `--scenario worn-lan` | 16/16 OK |

À noter : sur la branche #19598 seule, l'adossement fait depuis la commande (donc pendant le tour du joueur)
est refusé, `Err(NoPlayerOrWindow)` (le bug que corrige #19593). Le mod le refait alors en fin de tick serveur
(`server_tick`, personne dans le tour) et le dit dans le journal ; tout le reste passe. Sur la fusion,
l'adossement depuis la commande réussit tout de suite (`= Ok(())`).

Commande exacte : celle de `../19593/README.md`, avec `--scenario worn-solo` ou `worn-lan`.
Captures : `-1-opened`, `-2-shift-clicked`, `-3-own-slot-clicked`, `-4-removed`.
