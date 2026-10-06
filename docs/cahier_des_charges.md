# Cahier des Charges & Spécifications Fonctionnelles — TiMonde 📻✨

> *Version : 1.1 — Octobre 2026*  
> *Projet : TiMonde (Lecteur de webradios ultra-léger pour barre des tâches Linux)*  
> *Auteurs : Ben Thibaud, BB, Sam, Bob, Jim, Jack*

---

## 1. Vision du Produit & Principes Directeurs

TiMonde est un lecteur audio épuré, pensé pour s'intégrer discrètement dans la zone de notification de tous les environnements de bureau Linux (XFCE, Cinnamon, MATE, KDE Plasma, GNOME, etc.).

### Les piliers inviolables :
1. **Frugalité & Sobriété :** Consommation mémoire stricte sous le seuil des 15 Mo en veille (~10 Mo observés), CPU quasi nul, binaire optimisé en Rust.
2. **Évidence absolue ("Obviousness", Réflexe BB) :** Zéro jargon technique, zéro manipulation obscure. L'utilisateur doit pouvoir écouter, éteindre, classer et découvrir des stations en totale autonomie au premier coup d'œil.
3. **Approche Low-Tech & Fiabilité :** Bannir les usines à gaz matérielles ou logicielles non pérennes. Préférer des flux web stables, directs et en haute fidélité.

---

## 2. Décisions & Arbitrages : Gestion des Bouquets DAB+

### 2.1. Contexte & Abandon du DAB+ Hertzien Matériel (SDR)
Initialement envisagée, l'intégration du DAB+ par les ondes hertziennes physiques (dongle USB RTL-SDR, antenne VHF Bande III 174-240 MHz et démodulation logicielle `welle-cli`) a été **officiellement abandonnée** pour les raisons suivantes :
- **Fausse bonne idée au quotidien :** Exige du matériel encombrant, une antenne télescopique sensible aux obstacles intérieurs, et une démodulation logicielle gourmande en ressources CPU/RAM, en contradiction avec la philosophie de TiMonde.
- **Qualité sonore inférieure :** Le DAB+ hertzien compresse fréquemment les flux à 72-88 kbps HE-AAC pour faire tenir jusqu'à 13 radios par multiplexe, alors que les flux officiels de webradio diffusent en 128 à 320 kbps (MP3 / AAC) avec une dynamique et une clarté sonore bien supérieures.

### 2.2. Redéfinition du rôle du DAB+ dans TiMonde
Le concept de « bouquet DAB+ » est conservé pour son **véritable intérêt utilisateur** : **l'organisation éditoriale claire et hiérarchisée des radios majeures par pays et par région**, mais diffusées via les flux webradio officiels haute fidélité.

### 2.3. Bilan des choix d'ergonomie retenus

#### A. Suppression totale du jargon technique
- **Élimination des codes obscurs :** Disparition des termes de radioamateur ou de multiplexes (`M1`, `M2`, `7A`, `7B`, `8B`, etc.).
- **Dénomination naturelle :** Remplacement par **« Bouquet National »** et **« Régions & Locales »**.

#### B. Structure à deux niveaux : National & Régional
- **⭐ Bouquet National (par défaut) :** Regroupe les grandes stations emblématiques et incontournables du pays sélectionné (généralistes, information, culture, musicales majeures).
- **📍 Bouquets Régionaux / Locaux (à la demande) :** Pensés spécifiquement pour :
  - Les **expatriés** souhaitant garder le lien avec leur terroir ou leur région d'origine.
  - Les auditeurs en **mobilité** ou attachés à une scène locale (ex. : *Bretagne, Île-de-France, Auvergne-Rhône-Alpes, Nouvelle-Aquitaine, Occitanie, etc.*).

#### C. Gestion native des pays multilingues
Pour les pays plurilingues, l'interface propose un filtre linguistique/communautaire immédiat :
- **Belgique 🇧🇪 :** *Wallonie & Bruxelles (Français)* ou *Flandre (Néerlandais)*.
- **Suisse 🇨🇭 :** *Suisse romande (Français)*, *Suisse alémanique (Allemand)* ou *Tessin (Italien)*.
- **Canada 🇨🇦 :** *Québec & Francophonie (Français)* ou *Canada anglophone (Anglais)*.

#### D. Détection intelligente et prévention des doublons
- L'outil inspecte les signets existants de l'auditeur.
- Si une station est déjà présente dans les favoris (même nom ou même URL) :
  - Un indicateur visuel explicite s'affiche : **`(Déjà dans vos favoris)`**.
  - La case à cocher correspondante est **décochée par défaut**.
- **Bénéfice :** Permet à l'utilisateur d'importer une sélection régionale sans jamais doubler accidentellement les radios nationales communes déjà présentes.

#### E. Personnalisation du groupe d'import
- Champ texte modifiable avec suggestion automatique intelligente (ex. : `Radios Nationales (France)`, `Radios Bretagne`).
- Boutons rapides : `[ Tout cocher ]`, `[ Tout décocher ]`.
- Importation instantanée et rechargement immédiat du menu de la barre des tâches sans redémarrage de l'application.

### 2.4. Architecture Modulaire par Fichiers XML (Modèle `.po` / Internationalisation)
Afin d'intégrer progressivement **tous les bouquets DAB+ et sélections du monde entier**, le système adopte une architecture modulaire calquée sur le principe des fichiers de traduction (`gettext` / fichiers `.po`) :
- **Zéro codage en dur :** Aucune liste de stations n'est figée dans le code source Rust ou Python.
- **Répertoire de données dédié :** `data/bouquets/` (déployé dans `/usr/share/timonde/bouquets/` et `~/.local/share/timonde/bouquets/`).
- **Un fichier XML par pays :**
  - `fr.xml` : France 🇫🇷 (National + Régions : Bretagne, IDF, Rhône-Alpes, etc.)
  - `be.xml` : Belgique 🇧🇪 (Multilingue FR / NL + Régionales)
  - `ch.xml` : Suisse 🇨🇭 (Multilingue FR / DE / IT)
  - `ca.xml` : Canada 🇨🇦 (Multilingue FR / EN)
  - `uk.xml` : Royaume-Uni 🇬🇧 (National BBC / Commercial + Écosse, Pays de Galles, Ulster)
  - `de.xml` : Allemagne 🇩🇪 (National Dlf + Länder Bayern, NRW, etc.)
  - `es.xml` : Espagne 🇪🇸 (National + Catalogne, Andalousie)
  - `it.xml` : Italie 🇮🇹 (National Rai + Régions)
  - `no.xml` : Norvège 🇳🇴 (Pionnier 100% DAB)
  - `nl.xml` : Pays-Bas 🇳🇱 (NPO & Commerciales)
- **Découverte automatique & Frugalité :** L'explorateur scanne dynamiquement les fichiers XML présents. L'ajout d'un nouveau pays ne requiert aucune recompilation. Le parseur ne charge en mémoire que le pays en cours de consultation.
- **Contribution communautaire ouverte :** N'importe quel auditeur peut créer et soumettre le fichier XML de sa nation ou de sa région.

---

## 3. Ergonomie des Contrôles : La vision « Chaîne Hi-Fi »

### 3.1. Suppression du concept ambigu de « Pause »
Sur une station de radio en direct, la mise en pause est un non-sens : elle induit en erreur (l'utilisateur pense suspendre le temps, alors que la reprise saute au direct avec un décalage ou nécessite une mise en mémoire tampon superflue).

### 3.2. Bouton unique Marche / Arrêt (Power Hi-Fi)
L'interface adopte la franchise des boutons physiques d'un ampli ou d'un tuner Hi-Fi de salon :
- **Quand la radio joue :** Un bouton unique en haut du menu : **`⏹ Éteindre la radio`**.
  - Coupe immédiatement le son.
  - Ferme la connexion réseau et appelle `malloc_trim` pour libérer la RAM.
- **Quand la radio est éteinte :** Un bouton unique en haut du menu : **`▶ Allumer : [Nom de la dernière radio]`** (ou la première station des favoris si aucune n'a été jouée).
  - Relance instantanément le direct en un seul clic.

### 3.3. Raccourcis Molette sur l'icône de barre des tâches
- **Clic molette (bouton du milieu) :** Interrupteur instantané **Allumer / Éteindre**, sans avoir besoin d'ouvrir le menu déroulant.
- **Défilement molette (scroll haut/bas) :** Réglage fluide du volume pas à pas (par paliers de 5 %).

---

## 4. Architecture Technique & Performance

### 4.1. Composants logiciels
- **Noyau principal (Rust) :**
  - Plateau système D-Bus : `ksni` (protocole `StatusNotifierItem` FreeDesktop / X-Apps).
  - Moteur audio : `gstreamer-rs` avec playbin optimisé, tampons bridés à 640 Ko, exclusion des décodeurs vidéo et priorité aux décodeurs C légers (`faad`, `mpg123`).
  - Contrôle multimédia D-Bus : serveur `mpris-server` (touches multimédias et intégration applet son du bureau).
- **Interfaces d'appoint (Python 3 / GTK+ 3) :**
  - `reorder_groups.py` : Réorganisation hiérarchique des groupes et des stations, modification et suppression.
  - `edit_station.py` : Modification rapide du nom ou de l'URL d'une station.
  - `browse_bouquets.py` : Explorateur visuel des bouquets nationaux et régionaux par pays et langues.
  - *Principe d'isolation mémoire :* Les fenêtres GTK ne résident jamais en RAM permanente ; elles se lancent à la demande et libèrent 100 % de leurs ressources dès fermeture.

### 4.2. Formats de stockage
- Fichier principal : `~/.config/timonde/bookmarks.xml` (compatibilité avec le format Radio Tray historique).
- Prise en charge des imports : JSON (`radiotray-ng`), M3U/M3U8, CSV, XML.

### 4.3. Packaging & Distribution Multi-Distributions
- **Debian / Ubuntu / Linux Mint :** Paquet natif `.deb` généré via `make deb`.
- **Fedora / RHEL :** Fichier de spécification `packaging/rpm/timonde.spec`.
- **Arch Linux / Manjaro :** Recette `packaging/arch/PKGBUILD` pour installation AUR / makepkg.
- **Compilation universelle :** `make install` et `make install-user`.

---

## 5. Synthèse des Évolutions par Rapport à Radio Tray Historique

| Critère | Radio Tray d'origine (Python 2) | Radio Tray Lite (C++ 2018) | TiMonde (Rust 2026) |
| :--- | :--- | :--- | :--- |
| **Statut de maintenance** | Abandonné | Obsolète (dépendances mortes) | **Actif & Moderne** |
| **Empreinte mémoire** | ~40-60 Mo (Python 2 / GTK2) | ~15 Mo (C++) | **~10 Mo en veille (Rust)** |
| **Compatibilité Wayland/X11** | Partielle | Partielle | **Universelle (SNI / D-Bus)** |
| **Contrôle Hi-Fi** | Bouton Stop séparé | Basique | **Power On/Off franc + Molette** |
| **Gestion DAB / Bouquets** | ❌ Aucune | ❌ Aucune | **Explorateur National & Régions** |
| **Prévention doublons** | ❌ Aucune | ❌ Aucune | **Détection automatique intégrée** |
| **Auto-réparation de flux** | ❌ Aucune | ❌ Aucune | **Watchdog 5s + Radio-Browser** |
| **Minuteur de sommeil** | ❌ Non | ❌ Non | **Intégré (15 à 60 min)** |
