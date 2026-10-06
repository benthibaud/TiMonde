# TiMonde 📻✨
> *The small world of radios from anywhere — Le p'tit monde des ondes à portée de clic.*

**TiMonde** est un lecteur de webradios ultra-léger, minimaliste et universel, conçu pour se loger discrètement dans la zone de notification (systray / panneau) de **n'importe quel environnement de bureau Linux**.

Inspiré par la sobriété historique de **Radio Tray**, TiMonde le modernise pour offrir une expérience fluide, frugale et sans fioriture : le monde entier des ondes musicales et d'information concentré dans un mouchoir de poche.

---

## 🎯 Philosophie & Exigences Fondamentales

- **🍃 Frugalité & Low-Tech :** Démarrage instantané, empreinte mémoire dérisoire, consommation CPU quasi-nulle.
- **🤫 Discrétion absolue :** Aucune fenêtre envahissante. Une icône claire dans le tableau de bord, un menu direct, la musique démarre.
- **💡 Évidence ("Obviousness") :** Validé sous l'œil intraitable de l'agente **BB** : zéro jargon, zéro configuration obscure, tout doit être utilisable immédiatement en totale autonomie.
- **🌍 Universalité des distributions :** 
  - Ne pas être inféodé à Debian/Ubuntu : compatibilité de premier ordre garantie pour **Fedora / Red Hat**, **Arch Linux / Manjaro**, **openSUSE**, **Gentoo**, etc.
- **🖥️ Universalité des environnements de bureau :**
  - Rendu et intégration parfaits sur **XFCE**, **Cinnamon**, **MATE**, **KDE Plasma**, **LXQt**, **GNOME** (avec/sans extension indicateur) et les gestionnaires légers (i3, sway, waybar).
- **🧩 Approche X-Apps (Linux Mint) & Standard FreeDesktop :**
  - Utilisation du modèle d'intégration des **X-Apps** (`XAppStatusIcon`) et du standard universel `StatusNotifierItem` (SNI) sur DBus. Cette couche garantit que l'icône s'affiche fidèlement partout avec son menu natif, quel que soit le gestionnaire de fenêtres ou le serveur d'affichage (X11 / Wayland).

---

## 🚀 Feuille de Route Technique & État d'avancement

- [x] **Définition de l'identité et du cahier des charges d'universalité** (multi-distros & multi-bureaux)
- [x] **Zone de notification discrète sans fenêtre intermédiaire :** Intégration pure StatusNotifierItem (SNI FreeDesktop / X-Apps) via D-Bus natif.
- [x] **Ergonomie directe & évidente :** Clic gauche ouvrant immédiatement la liste des stations, aplatissement du palier intermédiaire `root >`.
- [x] **Moteur audio frugal et optimisé :** Initialisation paresseuse (Lazy Loading), bridage des tampons à 640 Ko, décodeurs légers prioritaires (`faad`, `mpg123`) et purge automatique de la RAM (`malloc_trim`). Empreinte mesurée : 13 Mo en veille, ~45 Mo en lecture.
- [x] **Contrôles essentiels façon chaîne Hi-Fi :** Bouton unique franc `▶ Allumer` / `⏹ Éteindre la radio` (Power On / Off), clic molette instantané et réglage du volume par défilement molette.
- [x] **Auto-réparation des flux muets :** Watchdog 5 secondes avec interrogation de l'annuaire public Radio-Browser et mise à jour persistante dans `bookmarks.xml`.
- [x] **3 icônes SVG légères et transparentes :** `timonde_off.svg`, `timonde_on.svg`, `timonde_error.svg`.
- [x] **Installation universelle :** Fichier `timonde.desktop` FreeDesktop et `Makefile` multi-distributions (`make install`, `make install-user`).
- [x] **Serveur D-Bus MPRIS2 :** Contrôle natif par touches multimédias du clavier et applet son du tableau de bord.
- [x] **Gestion & Importation de radios :** Ajout manuel, recherche multicritères Radio-Browser (genre, pays, langue), import multi-formats (JSON radiotray-ng, M3U, CSV, XML) avec détection des doublons.
- [x] **Fenêtre de gestion & réorganisation hiérarchique :** Classement des groupes et des stations par double-clic et glissement de rang, modification et suppression (menu tray direct et clic droit contextuel).
- [x] **Minuteur de mise en veille (Sleep Timer) :** Extinction programmée douce après 15, 30, 45 ou 60 minutes avec libération de la RAM.
- [x] **Explorateur de bouquets & radios populaires (DAB+ Webradio) :** Découverte intuitive des bouquets nationaux et régionaux par pays (France, Belgique, Suisse, Canada, UK...) et langues, sans clé USB matérielle, avec flux officiels haute fidélité et prévention automatique des doublons.
- [x] **Cahier des charges & spécifications complètes :** Document de référence disponible dans [`docs/cahier_des_charges.md`](docs/cahier_des_charges.md).
- [x] **Packaging natif multi-distributions :** Paquet `.deb` (`make deb`), spécification RPM Fedora et `PKGBUILD` Arch Linux / AUR.

---

## 👥 L'Équipe de conception

Conçu et propulsé avec l'atelier Antigravity :
- **Ben Thibaud** — Porteur du projet & vision
- **Sam** — Architecture logicielle & multiplateforme
- **Bob** — Frugalité système, packaging universel & performance low-tech
- **Jim** — Poésie des ondes & histoire
- **Jack** — Intégration protocoles (DBus, Wayland/X11, SNI)
- **BB** — Crash-test d'ergonomie, bon sens et simplicité d'usage

---

## 📄 Licence

Ce projet est distribué sous licence [GPL v3](LICENSE).
