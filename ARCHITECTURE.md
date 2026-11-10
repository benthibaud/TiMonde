# Architecture Technique — TiMonde

Ce document détaille les principes architecturaux directeurs de TiMonde.

---

## 1. Règle d'Or : Rust-First & Dumb UI Python

Pour garantir une consommation mémoire minimale, une réactivité immédiate et une absence totale de blocage sur le bureau Linux :

* **Cœur Métier Exclusif en Rust (`src/`) :**
  - Gestion du pipeline audio GStreamer (lecture, volume, détection de flux).
  - Persistance, parsing et sauvegarde atomique de `bookmarks.xml`.
  - Intégration système : serveur MPRIS2 D-Bus, plateau StatusNotifierItem (ksni).
  - Sondage réseau non-bloquant des flux audio (`probe_stream_url`).
  - Découverte et filtrage des bouquets XML (`discovery.rs`).
  - Moteur de recherche Radio-Browser et inférence des fuseaux horaires (`timezone.rs`).

* **Présentation Graphique en Python / GTK3 (`data/scripts/`) :**
  - Les scripts Python ne sont que des **terminaux de présentation passifs (Dumb UI)**.
  - **Zéro persistance locale en boîte noire :** Python ne modifie pas les fichiers XML directement. Les données transitent par des flux structurés JSON via stdin/stdout avec le binaire Rust (`timonde --dump-bookmarks-json`, `timonde --save-bookmarks-json`).
  - **Zéro requête HTTP / réseau autonome :** Python n'importe ni `urllib`, ni `requests`. Toute vérification de flux délègue à `timonde --probe-stream` ou au serveur MPRIS2 via D-Bus.

---

## 2. Flux de Données & Intégrité des Signets

```
   [ bookmarks.xml sur disque ]
                ▲
                │ (Sauvegarde atomique .tmp + rename + .bak)
                ▼
      [ Moteur Rust TiMonde ]
          ▲             │
          │ JSON        │ JSON
          │ (stdin)     │ (stdout)
          │             ▼
    [ UI GTK3 : reorder_groups.py ]
    (Affichage, drag & drop, filtres de vue)
```

### Garde-fous Anti-Perte de Données :
1. **Isolation des Filtres d'Affichage :** L'activation d'un filtre visuel (ex: *« Liens morts uniquement »*) restreint l'arbre GTK3 affiché à l'écran mais **ne modifie jamais la collection complète `self.data` en mémoire**.
2. **Contrôle d'Intégrité Rust :** La fonction `save_bookmarks_from_json()` vérifie le nombre de stations résultant. Toute tentative d'écraser un fichier existant contenant des stations par une liste vide est formellement rejetée avec un message explicite.
3. **Avertissement à la Fermeture :** Si l'utilisateur quitte une fenêtre de gestion alors que des modifications sont en attente (`dirty == True`), une confirmation explicite lui est demandée.
