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
- **Un fichier XML par pays (100 % de l'Union Européenne couverte + partenaires) :**
  - **Union Européenne (27/27 pays membres) :**
    - 🇫🇷 France (`fr.xml` : National + 8 régions françaises)
    - 🇧🇪 Belgique (`be.xml` : Multilingue Wallonie FR / Flandre NL + Régionales)
    - 🇩🇪 Allemagne (`de.xml` : National Dlf + Länder Bayern, NRW, SWR, NDR)
    - 🇪🇸 Espagne (`es.xml` : National + Catalogne, Andalousie)
    - 🇮🇹 Italie (`it.xml` : National Rai & grandes privées)
    - 🇳🇱 Pays-Bas (`nl.xml` : NPO & commerciales)
    - 🇦🇹 Autriche (`at.xml` : ORF Ö1, Ö3, FM4, Wien & privées)
    - 🇵🇹 Portugal (`pt.xml` : RTP Antena 1, 2, 3, Comercial, RFM, Renascença)
    - 🇮🇪 Irlande (`ie.xml` : RTÉ Radio 1, 2FM, Lyric, Gaeltachta, Today FM)
    - 🇸🇪 Suède (`se.xml` : Sveriges Radio P1, P2, P3, P4, Mix Megapol, Rix FM)
    - 🇩🇰 Danemark (`dk.xml` : Danmarks Radio P1, P2, P3, P4, Nova, Pop FM)
    - 🇫🇮 Finlande (`fi.xml` : Bilingue finnois Yle / suédois Vega & privées)
    - 🇵🇱 Pologne (`pl.xml` : Polskie Radio 1, 2, 3, 4, 24, RMF FM, ZET)
    - 🇨🇿 Tchéquie (`cz.xml` : Český rozhlas Radiožurnál, Dvojka, Vltava, Wave)
    - 🇬🇷 Grèce (`gr.xml` : ERT Proto, Deftero, Trito, Kosmos, Melodia, Red)
    - 🇷🇴 Roumanie (`ro.xml` : Radio România Actualități, Cultural, Kiss, ZU)
    - 🇭🇺 Hongrie (`hu.xml` : MTVA Kossuth, Petőfi, Bartók, Retro Rádió)
    - 🇸🇰 Slovaquie (`sk.xml` : RTVS Slovensko, Regina, Devín, _FM, Expres)
    - 🇭🇷 Croatie (`hr.xml` : HRT HR1, HR2, HR3, Otvoreni, Radio Dalmacija)
    - 🇸🇮 Slovénie (`si.xml` : RTV Slovenija Prvi, Val 202, ARS, Radio 1)
    - 🇧🇬 Bulgarie (`bg.xml` : BNR Horizont, Hristo Botev, BG Radio, Darik)
    - 🇱🇺 Luxembourg (`lu.xml` : Multilingue RTL Lëtzebuerg / L'essentiel FR)
    - 🇱🇹 Lituanie (`lt.xml` : LRT Radijas, Klasika, Opus, M-1, Radiocentras)
    - 🇱🇻 Lettonie (`lv.xml` : Latvijas Radio 1, 2, 3, Pieci.lv, Radio SWH)
    - 🇪🇪 Estonie (`ee.xml` : ERR Vikerraadio, Raadio 2, Klassika, Sky Plus)
    - 🇨🇾 Chypre (`cy.xml` : CyBC Proto, Deftero, Trito, Tetarto, Super FM)
    - 🇲🇹 Malte (`mt.xml` : PBS Radju Malta 1 & 2, Magic Malta, 89.7 Bay)
  - **Partenaires & Internationaux :**
    - 🇨🇭 Suisse (`ch.xml` : Multilingue Romande FR / Alémanique DE / Tessin IT)
    - 🇬🇧 Royaume-Uni (`uk.xml` : BBC 1 à 6, Commercial + Écosse, Galles, Ulster)
    - 🇳🇴 Norvège (`no.xml` : NRK P1, P2, P3, Klassisk, P4 Hele Norge)
  - **Les Amériques (Nord, Centrale, Caraïbes & Sud) :**
    - 🇺🇸 États-Unis (`us.xml` : National NPR, WNYC, KEXP Seattle, KCRW LA, WWOZ New Orleans + Métropoles NY, Californie, Texas)
    - 🇨🇦 Canada (`ca.xml` : Multilingue Québec FR / Anglophone EN)
    - 🇲🇽 Mexique (`mx.xml` : IMER Opus 94, Reactor 105.7, W Radio, Radio Fórmula, Alfa)
    - 🇧🇷 Brésil (`br.xml` : EBC Rádio Nacional, MEC, Jovem Pan, BandNews, CBN, NovaBrasil)
    - 🇦🇷 Argentine (`ar.xml` : Radio Nacional Argentina, Mitre, La 100, Rivadavia, Aspen, Rock & Pop)
    - 🇨🇴 Colombie (`co.xml` : Radio Nacional, Radiónica, Caracol, W Radio, Blu, Olímpica)
    - 🇨🇱 Chili (`cl.xml` : Cooperativa, Bío-Bío, ADN, Concierto, Futuro, Beethoven)
    - 🇵🇪 Pérou (`pe.xml` : Radio Nacional, RPP Noticias, Oxígeno, Panamericana, Studio 92)
    - 🇺🇾 Uruguay (`uy.xml` : Radio Uruguay, Babel, Sarandí, Carve, Del Sol, Océano)
    - 🇨🇺 Cuba (`cu.xml` : Radio Rebelde, Progreso, Taíno, Habana Cuba, Enciclopedia)
    - 🇻🇪 Venezuela (`ve.xml` : Éxitos, Onda, La Mega, Unión Radio Noticias, RNV)
  - **L'Afrique (Nord, Ouest, Centrale, Est & Australe) :**
    - 🇲🇦 Maroc (`ma.xml` : SNRT Al Idaa Al Watania, Chaîne Inter FR, Amazighe, Medi 1, Hit Radio, 2M, Mars)
    - 🇩🇿 Algérie (`dz.xml` : Radio Algérie Chaîne 3 FR, Chaîne 1, Chaîne 2, Jil FM, RAI, El Bahdja)
    - 🇹🇳 Tunisie (`tn.xml` : RTCI Tunis FR, Nationale, Jeunes, Culturelle, Mosaïque FM, IFM, Jawhara)
    - 🇪🇬 Égypte (`eg.xml` : Holy Quran Radio Cairo, Sawt Al Arab, Nogoum FM, Mega, Nagham, Hits 88.2)
    - 🇸🇳 Sénégal (`sn.xml` : RTS RSI, RFM Sénégal, Zik FM, Sud FM, Walf FM, Lamp Fall, Al-Fayda)
    - 🇨🇮 Côte d'Ivoire (`ci.xml` : Radio Côte d'Ivoire, Fréquence 2, Nostalgie CI, Jam, Vibe, Al Bayane)
    - 🇨🇲 Cameroun (`cm.xml` : CRTV Poste National, Balafon Douala, Equinoxe, Sweet FM, Kalak FM)
    - 🇨🇩 RD Congo (`cd.xml` : Radio Okapi, Top Congo FM Kinshasa, RTNC, B-One, Maendeleo)
    - 🇳🇬 Nigéria (`ng.xml` : Wazobia FM Pidgin, Cool FM Lagos, Nigeria Info, Beat 99.9, Classic 97.3)
    - 🇿🇦 Afrique du Sud (`za.xml` : SABC SAfm, 5FM, Metro FM, RSG Afrikaans, Ukhozi Zulu, 702 Talk, Jacaranda)
    - 🇰🇪 Kenya (`ke.xml` : KBC English & Taifa Swahili, Capital FM Nairobi, Classic 105, Citizen)
    - 🇲🇬 Madagascar (`mg.xml` : RNM Anosy, Radio Don Bosco, Alliance 92, RDJ 96.6, Kolo FM)
  - **Le Moyen-Orient :**
    - 🇱🇧 Liban (`lb.xml` : Radio Liban 98.1 FR, VDL, Mix FM, Radio One Beirut, Sawt El Ghad, Nostalgie)
    - 🇦🇪 Émirats Arabes Unis (`ae.xml` : Dubai Eye 103.8, Virgin Radio Dubai, Al Arabiya 99, Pulse 95 Sharjah)
    - 🇸🇦 Arabie Saoudite (`sa.xml` : Quran Riyadh, Riyadh Radio, Jeddah Radio, MBC FM, Panorama, Rotana)
    - 🇹🇷 Turquie (`tr.xml` : TRT Radyo 1, TRT FM, TRT 3 Klasik & Caz, Power FM, Kral FM, Süper FM)
    - 🇮🇱 Israël (`il.xml` : Kan Tarbut, Kan Bet, Kan Gimel, Kan 88, Galgalatz, Galei Tzahal)
    - 🇯🇴 Jordanie (`jo.xml` : Radio Jordan 90 FM English, Al-Urduniyah, Mood 92, Beat 102.5, Play 99.6)
  - **L'Asie & l'Océanie :**
    - 🇦🇺 Australie (`au.xml` : ABC NewsRadio, triple j, ABC RN, ABC Classic, Double J, Triple M, Nova 96.9)
    - 🇳🇿 Nouvelle-Zélande (`nz.xml` : RNZ National, RNZ Concert, The Rock NZ, Newstalk ZB, Mai FM, George FM)
    - 🇯🇵 Japon (`jp.xml` : NHK Radio 1, NHK Radio 2, NHK FM Tokyo, J-Wave 81.3, Tokyo FM 80.0, Shonan Beach FM)
    - 🇰🇷 Corée du Sud (`kr.xml` : KBS 1Radio, KBS 1FM Classic, KBS 2FM Cool FM, MBC Standard, SBS Power FM)
    - 🇹🇼 Taïwan (`tw.xml` : RTI Français & Mandarin, ICRT English Taipei, BCC i radio, Hit FM Taiwan)
    - 🇭🇰 Hong Kong (`hk.xml` : RTHK Radio 1, Radio 2 Cantopop, Radio 3 English, Radio 4 Fine Music Classical)
    - 🇸🇬 Singapour (`sg.xml` : Mediacorp CNA938, Gold 905, Symphony 924 Classical, 987FM, YES 933, Warna 942)
    - 🇹🇭 Thaïlande (`th.xml` : MCOT Active 99 FM, Thinking Radio 96.5, MET 107 English, Cool Fahrenheit 93)
    - 🇻🇳 Viêt Nam (`vn.xml` : VOV1 Actualités, VOV2 Culture, VOV3 Musique, VOV5 Français, VOV Giao Thông)
    - 🇮🇩 Indonésie (`id.xml` : RRI Programa 3 Berita Nasional, Pro 1, Pro 2 Muda, Prambors FM Jakarta, Gen FM)
    - 🇵🇭 Philippines (`ph.xml` : Wish 107.5 Manila Bus Live, Monster RX 93.1, Barangay LS 97.1, 90.7 Love Radio)
    - 🇲🇾 Malaisie (`my.xml` : RTM Radio Klasik, Nasional FM, TraXX FM English, Ai FM Chinois, Minnal Tamil, Fly FM)
    - 🇮🇳 Inde (`in.xml` : All India Radio Vividh Bharati, AIR National, AIR FM Gold, Radio Mirchi, Red FM)
    - 🇰🇿 Kazakhstan (`kz.xml` : Qazaq Radiosy, Radio Shalkar, Radio Classic Almaty, Radio NS, Gakku FM)
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
