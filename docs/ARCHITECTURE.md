# Architecture Technique de TiMonde

Ce document consigne l'architecture globale, les choix de conception et les briques logicielles partagées de TiMonde (v0.2.5 en développement).

---

## 1. Philosophie & Principes Directeurs

TiMonde est un lecteur de webradios ultra-léger pour le bureau Linux, fondé sur les principes suivants :
1. **Frugalité stricte (Low-Tech) :** Empreinte mémoire au repos sous le seuil physique de **15 Mo de RAM RSS**.
2. **Architecture hybride asymétrique — Doctrine Option B (Client/Serveur strict) :**
   - **Cœur temps réel et Source Unique de Vérité en Rust :** Exécutable unique gérant l'intégrité des signets XML, l'état persistant (`state.json`), la résolution réseau, les fuseaux horaires, le watchdog et le pipeline audio GStreamer 1.0 unique.
   - **Interface Graphique en Python 3 / PyGObject GTK3 « Dumb UI » (Affichage pur) :** Interdiction formelle pour le code Python d'écrire ou de manipuler directement `bookmarks.xml`, d'instancier un second moteur GStreamer concurrent, ou d'ouvrir des boucles synchrones `dialog.run()`. L'interface graphique n'est qu'un client de présentation, les actions métier sont déléguées au cœur Rust.
3. **Éradication des blocages et boucle GTK saine :** Bannissement absolu de l'anti-pattern `dialog.run()` au profit d'un cycle de vie événementiel pur (`connect("response")` + `show()`), interdisant tout gel d'interface ou dialogue orphelin.
4. **Neutralité d'affichage :** Intégration irréprochable sous Wayland natif (StatusNotifierItem, D-BusMenu) comme sous X11 (XEmbed, IceWM, Fluxbox, XFCE).
5. **Zéro boîte noire & Vérité de l'interaction humaine :** Toute action promise à l'utilisateur est réalisable de bout en bout via les dialogues graphiques.

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
├── edit_station.py               # Atelier d'édition unitaire d'une station (nom, URL, pays, fuseau)
├── patch_cinnamon_status_applet.py # Harmonisation hybride clic gauche/droit pour Linux Mint Cinnamon
├── gnome_tray_helper.py          # Assistant d'intégration proactive pour l'extension GNOME AppIndicator
└── timonde_i18n.py               # Couplage avec le domaine Gettext timonde
```

### Briques Communes Partagées (`timonde_common.py`)
1. **`RepairStreamDialog` :** Boîte de dialogue modale partagée permettant de rechercher et tester en direct un flux de remplacement sur Radio-Browser en cas de lien mort, réutilisée à la fois dans `reorder_groups.py` et `browse_bouquets.py`.
2. **`show_group_naming_help_dialog` :** Dialogue d'aide standardisé pour la hiérarchie des groupes (conventions de nommage avec slashs `/France/Nationales`).
3. **`_run_batch_checks` :** Moteur asynchrone de test de disponibilité par lot, parallélisant les requêtes HTTP/audio de façon bornée sans bloquer la boucle GTK.
4. **`status_markup` & `apply_timonde_app_css` :** Conception CSS intrinsèque sans styles arbitraires en dur : balisage de contraste garanti en thèmes sombre et clair (`#2ecc71`, `#f39c12`, `#e74c3c`), avec colonnes de TreeView adaptatives (`set_resizable(True)`, `ellipsize=END`).
5. **Persistance continue `flush_pending()` :** Sécurisation de l'atelier « Mes Radios » en mode intégré : toute modification est sauvegardée immédiatement avant tout changement d'onglet ou fermeture de la console.
6. **Arborescence Réelle `Gtk.TreeStore` & Gestion des Radios Racines (Option 1) :**
   - L'ancien affichage linéaire à deux niveaux (avec bouton « Retour aux groupes » et état `current_group_idx`) est définitivement remplacé par un modèle `Gtk.TreeStore` hiérarchique natif avec chevrons d'expansion `[▶] / [▼]`.
   - **Option 1 (Radios racines directes) :** Les stations n'appartenant à aucun groupe sont affichées directement au premier niveau du `TreeStore` aux côtés des dossiers, sans conteneur artificiel. À la sérialisation, elles sont inscrites directement sous la balise racine `<bookmarks>` sans élément `<group>`.
   - **Tri « A-Z » contextuel & vue repliée :** Le tri alphabétique cible le groupe sélectionné (ou le groupe parent de la station sélectionnée), et maintient ce groupe grand ouvert et sélectionné après le tri. La vue initiale s'ouvre repliée par défaut pour offrir une vision d'ensemble immédiate.
   - **Sécurisation ergonomique :** La suppression d'un groupe inspecte récursivement son contenu et affiche un avertissement quantifié explicite si des stations sont sur le point d'être supprimées.
7. **Unification de l'assignation de groupe & Déplacement intelligent :**
   - Suppression des doubles contrôles contradictoires (case à cocher vs champ de saisie) dans l'atelier *Collections & Fichiers*.
   - Le sélecteur de groupe du pied de page devient l'unique source de vérité (`(Dossiers d'origine)`, `[ / ] (Racine)`, ou saisie libre). La colonne *Dossier / Groupe* de la table réagit dynamiquement en temps réel pour refléter la destination exacte avant validation.
   - En cas d'importation d'une radio déjà existante dans un groupe différent, `add_stations_to_bookmarks_xml` déplace automatiquement le signet vers le nouveau groupe ciblé au lieu de le rejeter silencieusement.

---

## 4. Internationalisation (i18n)

- **Pivot unique :** Toutes les chaînes sources en Rust et Python utilisent l'anglais universel comme pivot fondamental (`msgid`).
- **56 langues supportées :** Définies dans `po/*.po` et compilées au format binaire Gettext (`po/locale/*/LC_MESSAGES/timonde.mo`).
- **Intégrité stricte :** Vérification systématique par `msgfmt --check` intégrée au cycle de build.

---

## 5. Intégration Environnements de Bureau & Harmonisation Cinnamon

### Problématique Technique de Linux Mint Cinnamon
Dans l'environnement Cinnamon, l'applet de notification système standard (`xapp-status@cinnamon.org`) n'ouvre le menu contextuel D-BusMenu qu'au **clic secondaire** (`BUTTON_SECONDARY`, clic droit).
Lors d'un **clic primaire** (`BUTTON_PRIMARY`, clic gauche), Cinnamon n'émet qu'un signal D-Bus `Activate`. Sous Mutter/Clutter, un mécanisme de capture exclusive du pointeur (*pointer grab*) empêche la réinjection synthétique d'événements (via XTest dans `x11_ffi.rs`), ce qui privait l'utilisateur de l'ouverture intuitive du menu par simple clic gauche.

### Architecture de la Solution Hybride (`patch_cinnamon_status_applet.py`)
TiMonde met en œuvre une stratégie à deux niveaux pour garantir une expérience utilisateur fluide sans jamais compromettre la stabilité du système ni subir d'écrasement lors des mises à jour :

1. **Ciblage chirurgical à zéro effet de bord :**
   Dans le fichier JavaScript de l'applet (`applet.js`), la conversion du clic primaire en clic secondaire est strictement conditionnée à la présence de `"timonde"` dans la chaîne d'identification de l'icône (`iconStr.indexOf('timonde') !== -1`).
   Toutes les autres applications du système (VLC, Steam, NetworkManager, Bluetooth...) conservent leur comportement 100% natif.

2. **Mode Utilisateur & Priorité Locale (Zéro écrasement APT) :**
   - Lorsqu'installé en mode utilisateur (`make install-user`), l'applet patchée est déployée dans `~/.local/share/cinnamon/applets/xapp-status@cinnamon.org/`.
   - **Règle Cinnamon :** Cinnamon donne une priorité absolue aux applets locales utilisateur sur les applets système situées dans `/usr/share/cinnamon/applets/`.
   - **Garantie anti-écrasement :** Les mises à jour du système d'exploitation ou du paquet `cinnamon` via APT n'affectent jamais `~/.local/share/`. Le patch utilisateur est totalement imperméable aux mises à niveau système.
   - Rechargement à chaud instantané via l'interface D-Bus de Cinnamon (`org.Cinnamon.ReloadXlet`).

3. **Mode Système & Pérennisation via Hook APT & Scriptlets RPM :**
   - Lorsqu'installé via le paquet Debian (`.deb`), le paquet RPM (`.rpm`), ou en mode administrateur (`sudo make install`), le patch est appliqué directement sur `/usr/share/cinnamon/applets/xapp-status@cinnamon.org/applet.js` (avec sauvegarde automatique `applet.js.orig_timonde`).
   - Pour les distributions basées sur Debian/Ubuntu/Mint, un hook APT persistant est déployé dans `/etc/apt/apt.conf.d/99timonde-cinnamon` :
     ```text
     DPkg::Post-Invoke {"if [ -x /usr/share/timonde/scripts/patch_cinnamon_status_applet.py ]; then python3 /usr/share/timonde/scripts/patch_cinnamon_status_applet.py --system >/dev/null 2>&1 || true; fi";};
     ```
   - Pour les distributions basées sur RPM (Fedora Cinnamon, openSUSE, RHEL), les scriptlets `%post` et `%postun` intégrés dans `packaging/rpm/timonde.spec` et `Cargo.toml` (`post_install_script`, `post_uninstall_script`) assurent l'exécution automatique de l'harmonisation et la régénération des caches d'icônes et de bureau.
   - À chaque mise à jour du paquet Cinnamon par APT, le script réapplique automatiquement le ciblage chirurgical en fin de transaction.

4. **Contrôle et Visibilité dans l'Interface Graphique :**
   - L'atelier **Préférences** de `timonde_settings.py` intègre une carte d'état dédiée à Cinnamon.
   - Cette carte sonde l'état du patch via `--check`, affiche un voyant clair et propose un bouton pour activer ou réactiver l'harmonisation à chaud d'un simple clic sans jamais recourir à un terminal.

5. **Cycle de Vie & Désinstallation Propre :**
   - Lors de la désinstallation (`make uninstall`, `make uninstall-user`, suppression du paquet `.deb` via `postrm` ou du paquet `.rpm` via `%postun`), le fichier d'origine est fidèlement restauré et le hook APT `/etc/apt/apt.conf.d/99timonde-cinnamon` est purgé.

---

## 6. Spécification Normative : Doctrine Option B (Zéro Plantage & Client/Serveur Strict)

Pour bannir définitivement la dette technique et les blocages récents, la **Doctrine Option B** régit désormais tous les développements futurs :

### Règle d'Or 1 : Rust = Source Unique de Vérité Métier
- **Fichiers de données :** Seul le cœur Rust manipule, assainit et écrit dans `~/.config/timonde/bookmarks.xml` et `~/.config/timonde/state.json`. Aucun script Python ne doit réimplémenter un moteur d'écriture XML ou de persistance d'état.
- **Réseau & Audio :** Le pipeline GStreamer 1.0 est strictement unique et réside dans le démon Rust. Python ne doit plus instancier de `playbin` local concurrent. Toute demande de test de flux ou de pré-écoute doit être transmise au moteur audio de TiMonde via son interface de contrôle.
- **Normalisation :** Le nettoyage d'URL (`clean_stream_url`), la détection de doublons, les fuseaux horaires et les métadonnées IANA sont validés côté Rust.

### Règle d'Or 2 : Python = Affichage Pur (Dumb UI) & Zéro `dialog.run()`
- **Composants en conteneurs `Gtk.Box` :** Les ateliers de l'interface (`reorder_groups.py`, `browse_bouquets.py`, etc.) ne doivent plus instancier de `Gtk.Window` fictives avec `embedded=True` pour leur voler des widgets. Ils héritent directement de `Gtk.Box`. Seule la coquille d'accueil crée la fenêtre principale.
- **Bannissement de `dialog.run()` :** Les boucles d'événements récursives sont proscrites. Toute fenêtre modale ou dialogue doit impérativement utiliser `connect("response", self._on_response)` suivi de `show_all()`, avec destruction explicite (`destroy()`) dans le callback de réponse.
- **Communication par API claire :** Les flux de données entre l'interface et le cœur Rust sont formalisés (CLI d'administration `--api` ou D-Bus), interdisant les lectures/écritures disques parallèles et asynchrones non coordonnées.

### Règle d'Or 3 : Briques Métier Déléguées à Rust (Zéro Doublon)
- **Décodage Universel de Fichiers (`timonde --parse-file-json <FICHIER>`) :** Tous les formats audio/playlists (`.json`, `.m3u`, `.pls`, `.csv`, `.xml`) sont décodés exclusivement par le moteur Rust `crate::import`. Les 261 lignes de parseurs manuels Python ont été éradiquées.
- **Recherche Annuaire Radio-Browser (`timonde --search ... --json`) :** L'interrogation multi-miroirs, le filtrage des flux brisés et le typage des réponses sont pilotés par Rust. Python ne fait plus de requêtes HTTP directes d'exploration.
- **Référentiel Géographique & Fuseaux Horaires (`timonde --dump-countries-json` et `--infer-timezone`) :** Base exhaustive des 251 pays et territoires ISO mondiaux embarquée en Rust. Python n'embarque plus de tables statiques redondantes et résout les fuseaux via le moteur Rust avec mise en cache mémoire locale.

### Règle d'Or 4 : Tolérance Zéro aux Paniques & Mutex Anti-Poisoning
- **Éradication des `.unwrap()` :** Tout le code actif de production Rust est strictement exempt de `.unwrap()`. Les potentielles erreurs d'I/O, de parsing ou de conversion sont gérées défensivement via `match`, `if let`, `?` ou fallbacks explicites.
- **Trait `SafeLock` (`src/sync_util.rs`) :** L'accès aux `Mutex` partagés s'effectue systématiquement via `.safe_lock()`, qui récupère l'état interne même en cas d'empoisonnement (`poisoned.into_inner()`), interdisant toute cascade de crashs ou blocage de la barre des tâches.

### Règle d'Or 5 : Probing Réseau Déporté en Rust (`timonde --probe-stream`)
- **Vérification HTTP & Métadonnées ICY :** La vérification de disponibilité des stations, l'analyse des en-têtes ICY/Shoutcast/Icecast et la détection des géo-blocages (403, 451, serveurs tiers) sont exécutées nativement par Rust (`src/probe.rs` via `ureq`).
- **Économie de GIL et de sockets :** Python ne crée plus de pools de sockets lourds (`urllib`) ni de `ThreadPoolExecutor(8)` bloquants ; il délègue à `timonde --probe-stream <URL> --json` et charge paresseusement ses dictionnaires de données.

---

## 7. Règle d'Or Desktop Linux : Rust-First Absolu & Dumb UI Python (Anti-Dérive)

Afin d'éradiquer la propension naturelle des agents et assistants à injecter du code métier en Python, la séparation architecturale suivante est contractuelle et irréversible :

1. **Rust est le Cerveau Unique du Système :**
   - 100 % du réseau (streaming audio, interrogation HTTP Radio-Browser, probing de flux, soumission de radios, DNS).
   - 100 % du parsing (XML bookmarks, OPML, M3U, PLS, CSV, JSON d'état).
   - 100 % de la persistance (`bookmarks.xml`, `state.json` atomique avec fichier temporaire unique par PID/nanoseconde).
   - 100 % de la gestion audio (GStreamer 1.0 `playbin`, horodatages solaires, notifications D-Bus MPRIS2).

2. **Python est un Simple Terminal Graphique (« Dumb UI ») :**
   - STRICTEMENT confiné à la construction de fenêtres GTK3, aux TreeViews, formulaires et gestionnaires d'événements utilisateur.
   - Interdiction absolue d'importer `urllib`, `requests` ou `http.client` dans les scripts de production.
   - Interdiction absolue d'exécuter des requêtes réseau directes ou du parsing XML métier. Tout besoin de données transite par les sous-commandes CLI du binaire Rust (`timonde --json ...`) ou par D-Bus.
   - Interdiction absolue d'ouvrir des dialogues modaux bloquants (`dlg.run()`) : tout dialogue doit utiliser le modèle asynchrone non-bloquant (`connect("response")` + `show_all()`).

3. **Garde-Fou Automatisé de Non-Régression (`make check-arch`) :**
   - Un script de contrôle statique (`scripts/check_architecture.py`) est intégré dans la suite de tests (`make test`).
   - Tout import réseau interdit ou tout appel synchrone `dlg.run()` dans `data/scripts/` fait échouer immédiatement la chaîne de build et les tests.



