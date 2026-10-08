# 📂 Fichiers exemples et personnalisés de TiMonde

Ce répertoire regroupe les collections thématiques prêtes à l'emploi et sert de modèle pour importer facilement vos propres listes de radios dans **TiMonde**.

Tous les fichiers placés ici apparaissent automatiquement dans la liste déroulante de l'onglet **« 📂 Sample Files / Fichiers exemples »** de la fenêtre *« 📻 Découvrir & Importer des radios »*.

---

## 📌 Où placer vos propres fichiers ?

Vous avez deux possibilités selon votre mode d'utilisation :

1. **Dans votre dossier utilisateur personnel (Recommandé, sans `sudo`) :**
   ```bash
   ~/.local/share/timonde/examples/
   ```
   *Tout fichier déposé ici est automatiquement détecté au lancement de l'outil d'importation.*

2. **Dans le dossier des sources (pour les développeurs) :**
   ```bash
   data/examples/
   ```

3. **Au niveau du système entier (partagé pour tous les utilisateurs, requiert `sudo`) :**
   ```bash
   /usr/share/timonde/examples/
   ```

---

## ❓ Le nom du fichier doit-il commencer par `x-` ?

**Non, absolument pas !**

N'importe quel nom de fichier est accepté, par exemple :
- `mes-radios.csv`
- `musique-baroque.xml`
- `webradios-favorites.json`
- `jazz.m3u`

*(Le préfixe `x-` utilisé sur les fichiers fournis avec TiMonde est simplement une convention interne signifiant « eXample » pour les distinguer des bouquets officiels DAB+).*

---

## 📄 Formats de fichiers acceptés & Exemples de syntaxe

TiMonde supporte nativement **5 formats de fichiers** :

### 1. Format CSV (`.csv`)
Le format le plus simple pour préparer vos radios dans un tableur (LibreOffice Calc, Excel) ou un éditeur de texte.

```csv
Nom, URL, Pays
FIP, https://icecast.radiofrance.fr/fip-midfi.mp3, FR
Radio Swiss Jazz, https://stream.srg-ssr.ch/m/rsj/mp3_128, CH
BBC Radio 6 Music, https://stream.live.vc.bbcmedia.co.uk/bbc_6music, GB
```

*Variantes acceptées :*
- 2 colonnes : `Nom, URL`
- 3 colonnes : `Nom, URL, Pays`
- 4 colonnes : `Groupe, Nom, URL, Pays`

---

### 2. Format XML Signets (`.xml`)
Format historique de Radio Tray et TiMonde avec support des groupes, séparateurs et drapeaux pays :

```xml
<bookmarks>
    <group name="Musique">
        <bookmark name="FIP" url="https://icecast.radiofrance.fr/fip-midfi.mp3" country="FR"/>
        <separator title="Jazz &amp; Blues"/>
        <bookmark name="TSF Jazz" url="https://tsfjazz.ice.infomaniak.ch/tsfjazz-high.mp3" country="FR"/>
    </group>
</bookmarks>
```

---

### 3. Format JSON (`.json`)
Structure structurée idéale pour les scripts et automatisations :

```json
[
  {
    "group": "Mes Radios",
    "stations": [
      {
        "name": "FIP",
        "url": "https://icecast.radiofrance.fr/fip-midfi.mp3",
        "country": "FR"
      },
      {
        "name": "SomaFM Groove Salad",
        "url": "https://ice1.somafm.com/groovesalad-128-mp3",
        "country": "US"
      }
    ]
  }
]
```

---

### 4. Playlists M3U / M3U8 (`.m3u`, `.m3u8`)
Format standard des lecteurs multimédia (VLC, Audacious, etc.) avec support des métadonnées `#EXTINF` :

```m3u
#EXTM3U
#EXTINF:-1 group-title="Électro",FIP Electro
https://icecast.radiofrance.fr/fipelectro-midfi.mp3
#EXTINF:-1 group-title="Jazz",Radio Swiss Jazz
https://stream.srg-ssr.ch/m/rsj/mp3_128
```

---

### 5. Playlists PLS (`.pls`)
Format classique de streaming Shoutcast / Icecast.

```ini
[playlist]
NumberOfEntries=1
File1=https://icecast.radiofrance.fr/fip-midfi.mp3
Title1=FIP
Length1=-1
```

---

## ⚡ Prise en compte dans TiMonde

Dès que vous ajoutez ou modifiez un fichier dans `~/.local/share/timonde/examples/` (ou `data/examples/`) :
1. Ouvrez le menu TiMonde -> **Options** -> **📻 Découvrir & Importer des radios...**
2. Rendez-vous sur le 3ᵉ onglet **« 📂 Sample Files »**.
3. Votre fichier est immédiatement disponible dans la liste déroulante du haut avec son icône de format !
