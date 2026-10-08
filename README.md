# TiMonde 📻

**TiMonde** est un lecteur de webradios sobre, rapide et discret, conçu pour se loger dans la zone de notification (systray) de votre bureau Linux.

Inspiré de l'esprit du classique *Radio Tray*, TiMonde se concentre sur l'essentiel : lancer vos flux préférés ou découvrir des radios du monde entier en un clic, sans encombrer votre écran ni consommer inutilement vos ressources.

---

## ✨ Fonctionnalités

* **Intégration discrète dans la barre des tâches :** Aucune fenêtre principale permanente. Tout se pilote depuis l'icône du plateau (compatible XFCE, Cinnamon, MATE, KDE Plasma, GNOME, LXQt, etc.).
* **Frugal et réactif :** Développé en Rust avec GStreamer, il démarre instantanément avec une empreinte mémoire réduite (~15 Mo en veille).
* **Heure locale et décalage horaire :** Affiche discrètement dans le menu l'heure réelle de la région d'émission et son décalage (avec icône jour/nuit ☀️/🌙).
* **Explorateur de bouquets & découverte :** Accès à plus de 130 bouquets de stations (France, Belgique, Suisse, Canada, Afrique, Asie...) et à l'annuaire mondial Radio-Browser, sans doublons.
* **Contrôles directs :**
  * **Clic gauche** : menu direct pour lancer la dernière station écoutée, choisir un flux ou éteindre.
  * **Clic molette** : allumage ou extinction immédiate.
  * **Molette** : réglage progressif du volume sonore.
  * **Touches multimédias** : prise en charge native du standard MPRIS2 (clavier et applet son du système).
* **Organisation simple :** Fenêtres d'édition et de réorganisation des groupes pour classer, renommer ou supprimer vos favoris en toute autonomie.

---

## 🚀 Installation

### 1. Sur Debian, Ubuntu et Linux Mint (paquet `.deb`)

Téléchargez le paquet `.deb` précompilé ou générez-le localement :

```bash
# Génération et installation du paquet :
make deb
sudo dpkg -i packaging/deb/timonde_0.1.0_amd64.deb
```

*Dépendances requises :* `libgstreamer1.0-0`, `gstreamer1.0-plugins-base`, `gstreamer1.0-plugins-good`, `python3-gi`, `gir1.2-gtk-3.0`.

### 2. Compilation depuis les sources (toutes distributions)

**Prérequis :** Rust (`cargo`), GStreamer et bibliothèques de développement :
* **Debian/Ubuntu :** `sudo apt install cargo libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev python3-gi gir1.2-gtk-3.0`
* **Fedora :** `sudo dnf install cargo gstreamer1-devel gstreamer1-plugins-base-devel python3-gobject gtk3`
* **Arch Linux :** `sudo pacman -S rust gstreamer gst-plugins-base gst-plugins-good python-gobject gtk3`

**Compilation et installation pour l'utilisateur courant :**

```bash
git clone https://github.com/benthibaud/TiMonde.git
cd TiMonde

# Compilation en mode release
cargo build --release

# Installation dans ~/.local/bin et ~/.local/share
make install-user
```

---

## 🎧 Utilisation

1. Lancez **TiMonde** depuis votre menu d'applications ou via un terminal :
   ```bash
   timonde
   ```
2. L'icône apparaît dans votre zone de notification :
   * **Éteint (veille) :** Première ligne `▶ Écouter « Nom de la station »` pour reprendre votre écoute.
   * **En lecture :** Première ligne `⏹ Éteindre « Nom de la station »`, accompagnée de l'heure locale, du titre du morceau en cours et du bouton `✏️ Éditer`.
3. Vos stations et préférences sont enregistrées dans :
   * Signets : `~/.config/timonde/bookmarks.xml`
   * État & volume : `~/.config/timonde/state.json`

---

## 📄 Licence

Ce projet est distribué sous licence [GPL v3](LICENSE).
