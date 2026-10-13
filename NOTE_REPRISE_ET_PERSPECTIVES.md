# Note de Reprise & Perspectives — TiMonde (Radio Tray Linux)

> **Dossier :** `scratch/TiMonde`  
> **Dépôt Git associé :** `https://github.com/benthibaud/TiMonde.git`  
> **Date de synthèse :** 11 Octobre 2026  
> **Comité technique consultatif :** Sam, Bob, BB, Jim, Jack  

---

## 1. Rappel des Discussions Anciennes & Genèse du Projet

Ce projet a été activement finalisé les **9 et 10 octobre 2026**. Il s'agit de la réécriture moderne et pérenne de l'application légendaire RadioTray, sous le nom **TiMonde**.

### Travaux récemment réalisés :
* **Développement Rust / GTK3 :** Performances optimales, empreinte mémoire minuscule (< 15 Mo), zéro crash.
* **Intégration d'environnement de bureau :**
  * Support complet du protocole StatusNotifierItem / AppIndicator (GNOME via extension, Xfce via greffon statusnotifier, Ubuntu Budgie, Fedora).
  * Menu contextuel épuré, sélecteur de radios mondiales, contrôle de volume.
* **Internationalisation (i18n) :** Traduction et validation des 55 fichiers de langues pour une diffusion internationale.
* **Packaging & Distribution :**
  * Génération des paquets Debian / Ubuntu / Mint (`.deb`).
  * Résolution des dépendances et génération des paquets Fedora / RedHat (`.rpm`).
* **Nouvelle icône :** Déclinaison vectorielle sobre représentant le globe terrestre.

---

## 2. État du Code & Prochaines Étapes Prévues

Le projet est stable en version **0.1.1**, testé avec succès sur Fedora, Ubuntu Budgie et Linux Mint Xfce.
* **Prochain chantier identifié par l'utilisateur :** Fusion du menu des options en un véritable **gestionnaire de paramètres unifié**, programmé après la présentation de cette semaine.

---

## 3. Retours du Conseil de Guerre

* **Sam :** « TiMonde est un projet modèle en termes de qualité de livraison : code compilé Rust, zéro fuite, paquets multi-distributions prêts à l'emploi. »
* **Bob :** « L'icône sobre et le menu natif s'intègrent parfaitement aux directives visuelles système sans détonner avec le bureau de l'utilisateur. »
* **BB :** « Lancer sa radio préférée depuis la barre des tâches en un clic sans fenêtre encombrante, c'est l'essence même de l'efficacité ! »
* **Jim :** « Moins de 15 Mo de RAM consommée : c'est un sans-faute low-tech. »
* **Jack :** « Tous les tags Git et releases sont calés. On peut mettre ce dossier en stand-by serein jusqu'à la semaine prochaine. »

---

## 4. Prompt de Reprise Rapide

```markdown
Tu interviens sur le projet TiMonde (scratch/TiMonde), lecteur radio ultra-léger en barre d'état (Rust / GTK3 / AppIndicator).
Dépôt : https://github.com/benthibaud/TiMonde.git
Prochain chantier : Fusionner le menu options en un gestionnaire de paramètres unifié.
Conserver la rigueur de compilation (cargo build --release) et les tests sur les paquets deb/rpm.
```
