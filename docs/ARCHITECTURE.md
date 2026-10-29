# Architecture Technique de TiMonde

Ce document consigne l'architecture globale, les choix de conception et les briques logicielles partagées de TiMonde (v0.2.2).

---

## 1. Philosophie & Principes Directeurs

TiMonde est un lecteur de webradios ultra-léger pour le bureau Linux, fondé sur les principes suivants :
1. **Frugalité stricte (Low-Tech) :** Empreinte mémoire au repos sous le seuil physique de **15 Mo de RAM RSS**.
2. **Architecture hybride asymétrique :**
   - **Cœur temps réel en Rust :** Exécutable unique, sans dépendance lourde, gérant le plateau système, l'audio GStreamer, D-Bus MPRIS2 et les fuseaux horaires.
   - **Suite d'administration graphique en Python 3 / PyGObject GTK3 :** Lancée uniquement à la demande lors de l'accès aux ateliers de configuration ou de découverte, ne consommant zéro ressource résiduelle lorsque fermée.
3. **Neutralité d'affichage :** Intégration irréprochable sous Wayland natif (StatusNotifierItem, D-BusMenu) comme sous X11 (XEmbed, IceWM, Fluxbox, XFCE).
4. **Zéro boîte noire & Vérité de l'interaction humaine :** Toute action promise à l'utilisateur est réalisable de bout en bout via les dialogues graphiques.

---

## 2. Cœur Applicatif (Rust `src/`)

```
src/
├── main.rs              # Point d'entrée, initialisation i18n, boucle d'événements et signal handling
├── audio.rs             # Pipeline audio GStreamer 1.0 (playbin) avec chargement différé (lazy)
├── bookmarks.rs         # Parsing XML et sérialisation atomique de bookmarks.xml
├── discovery.rs         # Moteur de découverte éphémère et sélection aléatoire
├── i18n.rs              # Chargeur binaire direct des catalogues Gettext (.mo) sans runtime externe
├── import.rs            # Moteur d'import/export universel (RadioTray, XML, CSV, M3U)
├── models.rs            # Structures de données fondamentales (Station, Group, Bookmarks)
├── mpris.rs             # Serveur D-Bus MPRIS2 (org.mpris.MediaPlayer2.timonde)
├── playlist.rs          # Résolution et parsing de formats de listes de lecture (PLS, M3U, ASX)
├── radio_browser.rs     # Client HTTP non-bloquant pour l'API Radio-Browser
├── state.rs             # Gestion et persistance d'état (volume, dernière station, favoris)
├── timezone.rs          # Éphémérides solaires, calcul de fuseau horaire et inférence géographique
└── tray/                # Sous-crate modulaire du plateau système
    ├── mod.rs           # Modèle d'état ksni, watchdog audio, dispatch des notifications
    ├── dialogs.rs       # Lancement et communication asynchrone avec les ateliers GTK3
    ├── menu.rs          # Construction dynamique de l'arborescence D-BusMenu
    └── x11_ffi.rs       # Détection et liaison bas-niveau des fenêtres X11/XEmbed
```

### Points Clés de Conception Rust
- **Délai d'anti-rebond (Debounce) sur le volume :** Lors de l'utilisation de la molette sur l'icône de zone de notification, le volume est ajusté immédiatement en temps réel sur GStreamer, tandis que la persistance sur disque (`state.json`) est différée de 300 ms afin de supprimer les I/O disque inutiles.
- **Asynchronisme des notifications tray :** Tout appel de rafraîchissement tray (`request_tray_refresh`) ou émission D-Bus est systématiquement isolé ou différé pour éviter tout auto-verrouillage (*self-deadlock*) sur le verrou d'état du plateau.
- **Gestion de la mémoire :** Un appel ciblé à `libc::malloc_trim(0)` après l'import initial de `bookmarks.xml` libère les pages mémoires allouées par l'allocateur système, garantissant un palier sous 15 Mo de RAM.

---

## 3. Suite Graphique (Python 3 / GTK3 `data/scripts/`)

```
data/scripts/
├── timonde_common.py    # Bibliothèque partagée : helpers UI, réseau, D-Bus, et dialogues modaux
├── timonde_settings.py  # Console unifiée regroupant les ateliers d'administration
├── reorder_groups.py    # Atelier « Mes Radios » (gestion fine, réordonnancement, réparation)
├── browse_bouquets.py   # Ateliers « Recherche », « Bouquets » et « Collections »
├── edit_station.py      # Atelier d'édition unitaire d'une station (nom, URL, pays, fuseau)
├── gnome_tray_helper.py # Assistant d'intégration proactive pour l'extension GNOME AppIndicator
└── timonde_i18n.py      # Couplage avec le domaine Gettext timonde
```

### Briques Communes Partagées (`timonde_common.py`)
1. **`RepairStreamDialog` :** Boîte de dialogue modale partagée permettant de rechercher et tester en direct un flux de remplacement sur Radio-Browser en cas de lien mort, réutilisée à la fois dans `reorder_groups.py` et `browse_bouquets.py`.
2. **`show_group_naming_help_dialog` :** Dialogue d'aide standardisé pour la hiérarchie des groupes (conventions de nommage avec slashs `/France/Nationales`).
3. **`_run_batch_checks` :** Moteur asynchrone de test de disponibilité par lot, parallélisant les requêtes HTTP/audio de façon bornée sans bloquer la boucle GTK.
4. **`status_markup` & `apply_timonde_app_css` :** Conception CSS intrinsèque sans styles arbitraires en dur : balisage de contraste garanti en thèmes sombre et clair (`#2ecc71`, `#f39c12`, `#e74c3c`), avec colonnes de TreeView adaptatives (`set_resizable(True)`, `ellipsize=END`).
5. **Persistance continue `flush_pending()` :** Sécurisation de l'atelier « Mes Radios » en mode intégré : toute modification est sauvegardée immédiatement avant tout changement d'onglet ou fermeture de la console.

---

## 4. Internationalisation (i18n)

- **Pivot unique :** Toutes les chaînes sources en Rust et Python utilisent l'anglais universel comme pivot fondamental (`msgid`).
- **56 langues supportées :** Définies dans `po/*.po` et compilées au format binaire Gettext (`po/locale/*/LC_MESSAGES/timonde.mo`).
- **Intégrité stricte :** Vérification systématique par `msgfmt --check` intégrée au cycle de build.
