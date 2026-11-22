# Preuves en jeu, PR #19593 (un mod adosse son menu depuis le tour du joueur)

Jeu complet lancé sans écran (Xvfb :77 + lavapipe), piloté par `horizon-ctl` avec la classe `Game` de
`tools/lan_e2e.py` (hors écran, `--no-pause`, dossiers jetables). Mod : `menuproof`
(`menuproof`, commit c66b4ee),
compilé dans le jeu comme `crates/horizon-mod-dimension-game` (`tools/install_into.py`).

Scénario `held-*` (voir `proof-mod/tools/proof_e2e.py`) : boîte (shulker box, 27 cases via ITEM_ITEMS)
avec 5 terre en case 4, tenue en main ; 64 pierre en case 9 de l'inventaire ; clic droit en l'air →
`use_item` du mod → `open_menu` + `back_mod_menu_slots(HeldItem x27)` → contenu visible après le tour →
shift-clic (pierre dans la boîte) → clic case 0 puis case 9 de la boîte → `/menuproof show` → fermer,
rouvrir, contenu gardé.

| Dossier | Arbre (commit exact) | Commande | Résultat |
|---|---|---|---|
| `branche-19593/solo` | `preuves/19593` = ea9d0b0115 + 9abed3664e (ajoute seulement le mod, sans ModItem : `install_into.py --no-worn`) | `proof_e2e.py --scenario held-solo` | 9/9 OK |
| `branche-19593/lan-hote-et-invite` | idem | `--scenario held-lan` (hôte LAN puis son invité) | 18/18 OK |
| `fusion-3-pr/solo` | `preuves/all` = fusion #19593+#19595+#19598 (cdddef0698) + mod, 6868bdaf8e | `--scenario held-solo` | 9/9 OK |
| `fusion-3-pr/lan-hote-et-invite` | idem | `--scenario held-lan` | 18/18 OK |
| `temoin-sans-19593/solo` | `preuves/19598` = 692eaa9625 (sans #19593) + mod, 3fba8b7aa1 | `--scenario held-solo` | **échoue, attendu** : `back_mod_menu_slots(Held x27) = Err(NoPlayerOrWindow)` |

Commande exacte (worktree et binaires au choix) :

```
Xvfb :77 -screen 0 1280x720x24 &
cd menuproof
TMPDIR=/tmp/mp RUST_LOG=info DISPLAY=:77 VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json \
  python3 tools/proof_e2e.py --tree <worktree> --bins <dossier avec menuproof-game et horizon-ctl> \
  --resources <horizon-checkout>/.local/horizon-client/26.3 --scenario held-solo --out <dossier>
```

Binaires : `cargo build --profile fast -p menuproof-game -p horizon-client-lib --bin menuproof-game --bin horizon-ctl`
dans le worktree, `CARGO_TARGET_DIR=<horizon-checkout>/target`.
(`TMPDIR` court : le chemin du socket de contrôle doit faire moins de 108 octets.)

Fichiers par dossier : `results.json` (chaque vérification, OK ou non, avec ce qui a été vu), `actions.log`
(chaque commande `horizon-ctl` et sa réponse), `*-menuproof.log` (les lignes du mod), `*-latest.log` (journal
complet du jeu), captures PNG (`-1-opened`, `-2-after-clicks`, `-3-reopened`). Chemins remplacés par
`<scratch>`, `<horizon>`.
