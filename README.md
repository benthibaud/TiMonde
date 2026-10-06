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

## 🚀 Feuille de Route Technique

- [x] Définition de l'identité et du cahier des charges d'universalité
- [ ] Moteur audio léger et robuste (GStreamer / pipelines audio basse consommation)
- [ ] Couche d'affichage unifiée via standard X-Apps / StatusNotifierItem (SNI)
- [ ] Support natif Wayland et X11
- [ ] Gestionnaire de favoris et listes de flux épuré (formats OPML / JSON / M3U)
- [ ] Notifications de bureau légères (changement de piste, métadonnées du flux)
- [ ] Formats de distribution multi-distros (sources CMake/Meson, paquets natifs .deb, .rpm, PKGBUILD Arch, Flatpak)

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
