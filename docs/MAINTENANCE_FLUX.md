# Protocole de Maintenance des Flux & Architecture Documentaire — TiMonde

> **Auteur :** Sam (Architecture & Mémoire de projet) — Équipe Antigravity  
> **Statut :** Validé  
> **Version cible :** TiMonde v0.2.1+  

---

## 1. Philosophie & Principes Fondamentaux

### 1.1 Séparation stricte Dev vs Client (Anti-Pollution Réseau)
Le protocole d'audit et de maintenance des flux **ne doit jamais être exécuté automatiquement en tâche de fond chez l'utilisateur final**. 
- TiMonde est conçu selon un principe de frugalité low-tech (< 15 Mo de RAM, 0% CPU au repos).
- Les vérifications massives de centaines de flux ne se font que lors de sessions de maintenance par les développeurs ou sur déclenchement explicite de l'utilisateur dans l'atelier d'audit de la console de paramètres.
- En conditions normales d'écoute, seul le **watchdog passif** (moteur Rust) surveille le flux en cours et bascule silencieusement sur un flux miroir si et seulement si la radio sélectionnée devient muette.

### 1.2 Distinction Structurante : Bouquets DAB+ vs Fichiers Exemples vs Recherche Mondiale

| Catégorie | Emplacement | Nombre | Critère d'inclusion |
| :--- | :--- | :--- | :--- |
| **Bouquets Officiels** | `data/bouquets/*.xml` | 146 pays/régions | Diffuseurs DAB+ officiels ou réseaux nationaux publics/privés répertoriés. |
| **Fichiers Exemples** | `data/examples/*` | 17 fichiers | Sélections thématiques (Jazz, Classique, Outre-Mer, etc.) fournies comme modèles. |
| **Annuaire Mondial** | API Radio-Browser | +40 000 stations | Découverte dynamique en ligne pour les pays sans bouquets DAB+ ou pour la recherche ad-hoc. |

#### Politique pour les territoires sans bouquets DAB+ officiels :
Pour éviter d'introduire des choix éditoriaux arbitraires dans les bouquets officiels, tout pays sans bouquet DAB+ pré-embarqué affiche une bannière informative claire offrant un bouton d'action direct :
> *« Aucun bouquet DAB+ pré-embarqué pour ce pays. »*  
> ➔ **Explorer les radios de ce pays sur Radio-Browser** (avec pré-sélection automatique du code ISO du pays).

Les sélections personnalisées (ex: radios d'Outre-Mer français) sont hébergées dans `data/examples/` afin de respecter la neutralité des 146 bouquets nationaux.

---

## 2. Architecture Technique & Briques Système

### 2.1 Moteur Rust Core (`src/`)
- **GStreamer 1.0 (`playbin`)** : Décodage universel bas niveau (MP3, AAC, OGG, Opus, flux HLS `.m3u8`).
- **ksni / D-Bus / X11** : Intégration systray universelle (StatusNotifierItem, XEmbed fallback via `timonde_xembed_bridge.py` et patch Cinnamon).
- **MPRIS2 (`src/mpris.rs`)** : Contrôle multimédia standardisé par le bureau Linux (touches multimédia, widget de volume).
- **Fuseaux Horaires & Astronomie (`src/timezone.rs`)** : Détection du décalage horaire local et affichage des icônes jour/nuit (`☀️`, `🌅`, `🌙`, `✨`).

### 2.2 Console Unifiée de Paramètres (`timonde_settings.py`)
- Fenêtre centrale GTK3 intégrant les 5 ateliers essentiels :
  1. **Mes Radios** (`reorder_groups.py` intégré in-process) : Tri, création de dossiers, renommage, suppression, audit en direct.
  2. **Rechercher en ligne** (`browse_bouquets.py` / `view_search`) : Recherche mondiale Radio-Browser par nom, tag, pays ou langue.
  3. **Bouquets par pays** (`browse_bouquets.py` / `view_bouquets`) : Exploration des 146 pays avec drapeaux, stations et statut DAB+.
  4. **Collections & Fichiers** (`browse_bouquets.py` / `view_files`) : Import/Export XML, JSON, CSV, M3U, PLS et restauration des 17 exemples.
  5. **Préférences & Autostart** : Bascule du démarrage de session, détection de bureau et statistiques de signets.
- **Règle ergonomique modale** : Tout dialogue ou fenêtre fille doit obtenir sa fenêtre parente via `get_parent_window()` pour éviter tout dialogue flottant orphelin.

### 2.3 Internationalisation Stricte (i18n)
- **Pivot Anglais Universel** : Les fonctions `crate::i18n::tr("...")` en Rust et `_("...")` en Python utilisent rigoureusement des clés pivots en **anglais**.
- **Distinction des dialectes chinois** : Prise en charge native de `zh_CN` (Mandarin simplifié) et `zh_TW` (Cantonais / Traditionnel).
- **56 Catalogues `.mo`** : Recompilés via `make mo` et distribués sous `/usr/share/locale/<lang>/LC_MESSAGES/timonde.mo`.

---

## 3. Protocole de Mise à Jour & Audit des Flux

### 3.1 Outils d'Investigation & Test
Pour tester l'accessibilité d'un flux sans interface graphique :
```bash
# Test rapide d'en-tête HTTP et redirection
curl -ILs --max-time 5 "https://mon-flux.example.com/stream" | grep -E "(HTTP/|content-type:)"

# Test audio direct avec GStreamer
gst-launch-1.0 playbin uri="https://mon-flux.example.com/stream"
```

### 3.2 Cas Particuliers Fréquents
1. **Flux Géobloqués (ex: FM Yokohama 84.7 [JP])** :
   - Ces stations renvoient souvent un code HTTP 403 Forbidden ou une page HTML de restriction depuis les IP situées hors du pays de diffusion.
   - Ne pas supprimer le flux s'il est officiel : l'auditeur local ou sous VPN légitime doit pouvoir l'écouter. Le testeur marque le flux avec `[?] Geo-restricted`.
2. **Serveurs à jetons éphémères (ex: StreamSurfer, Cloudflare Workers)** :
   - Les URL contenant des paramètres horodatés (`?t=1777886974408`) expirent dans le temps. Privilégier systématiquement l'URL canonique directe du serveur Icecast/Shoutcast (`/stream`, `/live`, `;`).

---

## 4. Schéma des Données & Persistance

### 4.1 Fichier Signets (`~/.config/timonde/bookmarks.xml`)
Format XML rétrocompatible Radio Tray, enrichi avec les attributs géographiques :
```xml
<bookmarks>
  <group name="Musique">
    <station name="FIP" url="https://icecast.radiofrance.fr/fip-midfi.mp3" country="FR" timezone="Europe/Paris"/>
    <separator/>
    <header name="Jazz"/>
    <station name="TSF Jazz" url="http://tsfjazz.ice.infomaniak.ch/tsfjazz-high.mp3" country="FR" timezone="Europe/Paris"/>
  </group>
</bookmarks>
```

### 4.2 Fichier d'État Applicatif (`~/.config/timonde/state.json`)
Persistance légère et asynchrone pour reprise immédiate à la prochaine session :
```json
{
  "volume": 0.85,
  "last_station": {
    "name": "FIP",
    "url": "https://icecast.radiofrance.fr/fip-midfi.mp3",
    "country": "FR",
    "timezone": "Europe/Paris"
  }
}
```

---

## 5. Procédure de Packaging & Release

Pour recompiler l'ensemble des catalogues de traduction, générer les binaires optimisés et empaqueter les versions finales :
```bash
# 1. Compilation des traductions et exécution des tests complets
make mo
make test
cargo clippy -- -D warnings

# 2. Génération des paquets de distribution
make deb    # Produit packaging/dist/timonde_0.2.1_amd64.deb
make rpm    # Produit packaging/dist/timonde-0.2.1-1.x86_64.rpm
```
