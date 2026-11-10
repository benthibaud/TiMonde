# Feuille de Route & Journal des Décisions — TiMonde (ROADMAP)

> **Tenue de projet :** Sam (Architecture & Mémoire de projet) & Céline (Auditrice technique)  
> **Objectif suprême :** Frugalité absolue, zéro régression, zéro plantage.

---

## 1. Vision & Décision Architecturale Fondatrice (Novembre 2026)

### La Doctrine « Option B » (Client/Serveur Strict)
Face à la dette technique accumulée (duplication de code entre Rust et Python, 3 pipelines GStreamer concurrents, boucles récursives `dialog.run()` ayant entraîné des gels d'interface), l'équipe a acté à l'unanimité le rejet des rustines au profit d'un contrat d'ingénierie strict :

1. **Rust est l'unique source de vérité :**
   - Écriture atomique et validation de `bookmarks.xml` et `state.json`.
   - Pipeline GStreamer unique (lecture normale et pré-écoute).
   - Inférence des pays, fuseaux horaires et normalisation des flux.
2. **Python est un client d'affichage pur (Dumb UI) :**
   - Aucune logique métier dupliquée, aucune écriture disque directe.
   - Ateliers conçus sous forme de `Gtk.Box` pures (fin de la bidouille des `Gtk.Window` avec `embedded=True`).
   - Éradication intégrale de `dialog.run()` : tout dialogue GTK est asynchrone via `connect("response", ...)` et `show_all()`.

---

## 2. État des Jalons

### Jalon 1 : Audit, Stabilisation et Publication v0.2.4 (Terminé ✅)
- [x] Détection et correction du gel sur `ContributeStationDialog` (Radio Tayna Goma).
- [x] Rafraîchissement direct de la colonne Détails/Pays dans l'arbre « Mes radios ».
- [x] Intégration du test unitaire de la boucle d'événements GTK (`test_gtk_event_loop.py`).
- [x] Gravure de la doctrine Option B dans `docs/ARCHITECTURE.md`, `ROADMAP.md` et `MAINTENANCE_FLUX.md`.
- [x] Release et publication GitHub de la version `v0.2.4`.

### Jalon 2 : Sécurisation Immédiate du Code Existant — v0.2.5 (Terminé ✅)
- [x] Sortir `resolve_stream_url` du verrou `audio.lock()` dans `src/tray/dialogs.rs`.
- [x] Remplacer le spawn Python au boot par le test natif `XDG_CURRENT_DESKTOP` dans `src/main.rs`.
- [x] Corriger l'appel à `RepairStreamDialog` et dépiler proprement `on_check_streams_clicked` dans `reorder_groups.py`.
- [x] Ajouter la destruction systématique (`dlg.destroy()`) sur tous les dialogues de `browse_bouquets.py`.

### Jalon 3 : Bascule vers l'Option B Complète (Terminé ✅)
- [x] Exposer une interface de commandes CLI et D-Bus propre côté Rust (`timonde --reload`, `--preview-play`, `--preview-stop`, `--save-bookmarks-json` + méthodes D-Bus MPRIS `PlayPreview`, `StopPreview`, `ReloadBookmarks`).
- [x] Supprimer le pipeline GStreamer `playbin` Python redondant de `data/scripts/` (`StreamPreviewPlayer` s'appuie désormais 100% sur l'instance Rust active).
- [x] Éradiquer les écritures XML directes de signets côté Python au profit du moteur de persistance natif Rust (`save_bookmarks_tree` -> `timonde --save-bookmarks-json`).
- [x] Sécuriser de manière atomique la réparation locale de bouquets XML dans `browse_bouquets.py`.

### Jalon 4 : Dumb UI & Asynchronisme Intégral (Terminé ✅)
- [x] Découpler les vues et fenêtres : `ReorderWidget(Gtk.Box)` pur et `ReorderWindow(Gtk.Window)` conteneur léger, éliminant les doubles parents et les surfaces X11 fantômes.
- [x] Éradiquer 100% des `.run()` interactifs (`dialog.run()`, `chooser.run()`) dans `reorder_groups.py`, `browse_bouquets.py`, `edit_station.py` et `timonde_common.py` au profit de `connect("response", ...)`.
- [x] Valider l'intégrité de la boucle GTK et l'asynchronisme complet via `test_gtk_event_loop.py` et la suite `make test`.

### Jalon 5 : Unification Totale Option B & Éradication du Code Mort (Terminé ✅)
- [x] **Unification totale lecture/écriture :** Rust expose `GetBookmarksJson()` sur D-Bus, `--dump-bookmarks-json` et `--save-bookmarks-json [DEST]`. `load_bookmarks_tree(path)` et `save_bookmarks_tree(path)` délèguent 100% de la désérialisation/sérialisation à Rust.
- [x] **Éradication totale du code mort en Python :** Suppression de `_write_bookmarks_element_tree_atomic` (-100 lignes), suppression du parsing manuel XML dans `timonde_settings.py` (`get_bookmarks_stats`, `build_section_discovery` passent par `load_bookmarks_tree`).
- [x] **Éradication des fenêtres fantômes :** Découplage de `browse_bouquets.py` avec `DiscoverRadiosViews` (contrôleur et vues pures sans fenêtre) et `DiscoverRadiosWindow` (conteneur CLI autonome). Fin définitive de `embedded=True` sur une `Gtk.Window`.
- [x] **Validation intégrale :** 54 tests Rust + 17 tests unitaires Python + 4 tests GTK loop / AST scope = 100% vert.

### Jalon 6 : Éradication des Doublons Rust/Python & Dumb UI Intégral (Terminé ✅)
- [x] **Chantier 1 (Fichiers) :** Décodage universel de fichiers par Rust via `timonde --parse-file-json <FICHIER>`. Éradication de 261 lignes de vieux parseurs manuels M3U/PLS/CSV/XML/JSON dans `browse_bouquets.py`.
- [x] **Chantier 2 (Réseau Radio-Browser) :** Recherche multicritères déléguée au moteur Rust via `timonde --search [...] --json` avec bascule automatique de miroir, filtrage et typage strict.
- [x] **Chantier 3 (Géographie & Fuseaux) :** `COUNTRY_REGISTRY` enrichi à 251 pays/territoires en Rust. Commandes CLI `timonde --dump-countries-json` et `timonde --infer-timezone`. Suppression de 230+ lignes de tables statiques et tests ad hoc dans `timonde_common.py`.
- [x] **Validation intégrale :** 56 tests Rust + 17 tests unitaires Python + 4 tests GTK loop / AST scope = 100% vert.

### Jalon 7 : Standard Industriel, Sécurisation Absolue & Probing Réseau Natif (Terminé ✅)
- [x] **Chantier 1 (Sécurisation Rust & Éradication des `.unwrap()`) :** Recensement et élimination des 98 `.unwrap()` du code actif de production. Mise en place du trait `SafeLock` (`sync_util.rs`) garantissant la tolérance aux mutex empoisonnés (anti-poisoning) et interdisant les paniques en cascade.
- [x] **Chantier 2 (Probing Réseau Natif Rust) :** Création du module `src/probe.rs` et de la commande `timonde --probe-stream <URL> [--timeout <SECS>] [--json]`. Déportation de `check_stream_url` vers Rust, éliminant les sockets urllib et le blocage de GIL Python.
- [x] **Chantier 3 (Dégraissage Géographie & Lazy Loading) :** Initialisation paresseuse (*lazy*) via `_LazyDict` des 520 Ko de dictionnaires multilingues dans `timonde_world_data.py`. Démarrage instantané des outils GTK.
- [x] **Chantier 4 (Architecture Modulaire Rust) :** Découpage du "God File" `src/main.rs` (réduit de 991 à 404 lignes) avec extraction de `src/cli.rs`.
- [x] **Chantier 5 (Informations Système dans les Préférences) :** Affichage de la version installée et du chemin physique du binaire détecté en tête des Préférences.
- [x] **Validation intégrale :** 58 tests Rust + 17 tests unitaires Python + 4 tests GTK loop / AST scope = 100% vert. Clippy `-D warnings` 100% propre.


### Jalon 8 : Unification de la Session Audio & Éradication des Deadlocks — v0.2.6 (Terminé ✅)
- [x] **Unification transactionnelle (`PlaybackSession`) :** Fusion des 7 mutex dispersés en un modèle transactionnel à verrou unique dans `src/session.rs`. Éradication mathématique de tout interblocage ABBA.
- [x] **Règle d'or GStreamer :** Démontage (`set_state(Null)`), instanciation et démarrage de flux exécutés hors de tout verrou partagé.
- [x] **Option A & Maîtrise mémoire :** Drop déterministe hors verrou avec `malloc_trim(0)`. Exclusion de `libav` (FFmpeg) plafonnant la consommation RAM en écoute active à 45 Mo (les 45 Mo historiques de TiMonde) sans aucune fuite lors des zappings.
- [x] **Validation intégrale :** 62 tests unitaires et banc de stress-test automatisé avec 10 commutations rapides (latence D-Bus moyenne 20.0 ms, zéro gel).

### Jalon 9 : Règle d'Or « Rust-First Absolu », Optimisation & Dumb UI Python — v0.2.7 (Terminé ✅)
- [x] **Éradication des failles de concurrence résiduelles :** Résolution de la course « radio fantôme » via génération atomique sous verrou, GStreamer hors lock session, isolation de `StopPreview` et écriture atomique immunisée aux collisions.
- [x] **Rapatriement réseau et parsing intégral dans Rust :** Implémentation native de `--lookup-url` et `--contribute-station` vers Radio-Browser, parsing haute vitesse des bouquets DAB+ (`--dump-bouquet-json`, `--list-bouquets`) et calcul des fuseaux horaires (`--list-timezones`).
- [x] **Dumb UI Python stricte & Zéro `xml.etree` :** Éradication totale de `xml.etree` dans l'interface et des reliquats `dialog.run()` au profit du modèle asynchrone connecté au signal `response`.
- [x] **Briques UI mutualisées :** Factorisation de `attach_country_completion` et `GroupSelectorBar` partagés entre tous les dialogues.
- [x] **Allègement packaging :** Rétrogradation de `gstreamer1.0-libav` en `Recommends` (-80 Mo sur le système cible).
- [x] **Garde-fou CI :** Script `scripts/check_architecture.py` audité automatiquement à chaque `make test`.
- [x] **Validation intégrale :** 65 tests Rust + 30 tests Python + 11 scripts audités = 100 % vert.


---

## 3. Règles d'Or Intransgressibles

- **Règle 1 :** Tout correctif doit être validé par un test automatique (`make test` doit réussir à 100%).
- **Règle 2 :** Aucun dialogue modal ne doit être détruit sans que sa boucle d'événements ne soit terminée.
- **Règle 3 :** Préserver scrupuleusement la compatibilité antiX/X11 (pont XEmbed, émulation XTest FFI, police sans émojis cassés).
