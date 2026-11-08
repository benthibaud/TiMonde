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

### Jalon 1 : Audit et Identification des Bombes à Retardement (Terminé ✅)
- [x] Détection du gel sur `RepairStreamDialog` (signature d'appel divergente).
- [x] Détection de l'appel prématuré à `dialog.destroy()` pendant `dialog.run()` dans `reorder_groups.py`.
- [x] Identification du verrouillage du `Mutex<AudioEngine>` pendant la résolution réseau de playlist dans `dialogs.rs`.
- [x] Détection du spawn synchrone de Python au démarrage dans `ensure_desktop_integration()`.
- [x] Gravure de la doctrine Option B dans `docs/ARCHITECTURE.md` et `docs/ROADMAP.md`.

### Jalon 2 : Sécurisation Immédiate du Code Existant (En cours 🔄)
- [ ] Sortir `resolve_stream_url` du verrou `audio.lock()` dans `src/tray/dialogs.rs`.
- [ ] Remplacer le spawn Python au boot par le test natif `XDG_CURRENT_DESKTOP` dans `src/main.rs`.
- [ ] Corriger l'appel à `RepairStreamDialog` et dépiler proprement `on_check_streams_clicked` dans `reorder_groups.py`.
- [ ] Ajouter la destruction systématique (`dlg.destroy()`) sur tous les dialogues de `browse_bouquets.py`.

### Jalon 3 : Bascule vers l'Option B Complète (À venir ⏳)
- [ ] Exposer une interface de commandes / D-Bus propre côté Rust (`timonde --api ...` ou méthodes D-Bus).
- [ ] Transformer les fenêtres Python en composants `Gtk.Box` purs sans instanciation de `Gtk.Window` fictives.
- [ ] Bannir tous les `dialog.run()` résiduels au profit du pattern `response`.
- [ ] Supprimer les parseurs XML et le pipeline GStreamer redondants de `data/scripts/`.

---

## 3. Règles d'Or Intransgressibles

- **Règle 1 :** Tout correctif doit être validé par un test automatique (`make test` doit réussir à 100%).
- **Règle 2 :** Aucun dialogue modal ne doit être détruit sans que sa boucle d'événements ne soit terminée.
- **Règle 3 :** Préserver scrupuleusement la compatibilité antiX/X11 (pont XEmbed, émulation XTest FFI, police sans émojis cassés).
