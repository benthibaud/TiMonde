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

---

## 3. Règles d'Or Intransgressibles

- **Règle 1 :** Tout correctif doit être validé par un test automatique (`make test` doit réussir à 100%).
- **Règle 2 :** Aucun dialogue modal ne doit être détruit sans que sa boucle d'événements ne soit terminée.
- **Règle 3 :** Préserver scrupuleusement la compatibilité antiX/X11 (pont XEmbed, émulation XTest FFI, police sans émojis cassés).
