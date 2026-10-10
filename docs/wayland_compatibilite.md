# Compatibilité Wayland & Environnements Modernes (KDE Plasma 6, Mutter, Wayfire, Sway)

Ce document consigne les diagnostics, cas limites et résolutions techniques validés lors des tests en conditions réelles sous **KDE Neon (KDE Plasma 6 / KWin Wayland)**.

---

## 1. Piège du protocole d'activation Wayland (`xdg_activation_v1`)

### Problème rencontré
Lors du déclenchement des fenêtres de dialogue GTK3 (`browse_bouquets.py`) depuis le menu de la barre des tâches (géré par le démon TiMonde en tâche de fond) :
* Le script Python montait immédiatement à **60 % de CPU** et **150 Mo de RAM**, en boucle infinie sans jamais afficher la fenêtre à l'écran.
* L'analyse fine des flux de sockets (`/proc/<pid>/fd/3` sur `/run/user/1000/wayland-0`) révélait un échange ininterrompu :
  ```text
  sendmsg(3, "not-granted-activation-token...") -> recvmsg(3, "not-granted...")
  ```

### Cause racine
Dans `browse_bouquets.py`, un rappel d'événement `map-event` appelait :
```python
def on_map_event(window, event):
    window.present_with_time(Gdk.CURRENT_TIME)
    ...
```
* **Sous X11 (Cinnamon, XFCE, IceWM) :** Cet appel forçait simplement la mise au premier plan sans effet secondaire néfaste.
* **Sous Wayland (KWin) :** Une application lancée en tâche de fond par un démon n'a pas le focus utilisateur initial. KWin rejette la demande de focus (`not-granted`). Dans GTK3 sur le backend Wayland, cette tentative infructueuse déclenchait un restack / re-mapping interne, qui réémettait immédiatement le signal `map-event`.
* **Conséquence :** Boucle infinie d'appels `map-event` <-> `present_with_time` en saturant un cœur processeur complet.

### Résolution appliquée
1. Suppression complète de l'appel récursif `present_with_time` dans `map-event`.
2. Utilisation de `win.set_focus_on_map(True)` et de l'appel standard `win.present()` une seule fois après `win.show_all()`.
3. Résultat : ouverture instantanée (< 100 ms) et 0 % d'utilisation CPU au repos sous Wayland.

---

## 2. Détection du thème sombre/clair du panneau (StatusNotifierItem & D-Bus)

### Problème rencontré
Sous KDE Neon (thème clair par défaut), l'icône de la barre des tâches était invisible à l'œil nu (blanc sur fond bleu très clair).

### Spécification technique Freedesktop / KDE Breeze
Dans Plasma 6 et les environnements modernes, les icônes vectorielles du panneau doivent inclure la feuille de style dynamique :
```xml
<defs>
  <style type="text/css" id="current-color-scheme">
    .ColorScheme-Text { color: #232629; }
    .ColorScheme-PositiveText { color: #27ae60; }
    .ColorScheme-NegativeText { color: #da4453; }
  </style>
</defs>
```
* Les tracés doivent utiliser `class="ColorScheme-Text"` et `stroke="currentColor"`.
* Plasma remplace à chaud `currentColor` par la couleur de texte active du panneau (noir `#232629` sur fond clair, blanc `#eff0f1` sur fond sombre).
* Pour garantir ce comportement, la méthode Rust `icon_theme_path()` priorise désormais le chemin vectoriel `/usr/share/icons/hicolor/scalable/panel`.

---

## 3. Comportement des listes de signets vierges

### Diagnostic
Si un utilisateur installe TiMonde avec un fichier `~/.config/timonde/bookmarks.xml` vide ou fraîchement initialisé (`<bookmarks></bookmarks>`), l'outil d'organisation (`reorder_groups.py`) était bloqué en amont par la garde Rust `if guard.subgroups.is_empty() { return; }`.

### Résolution
La garde a été retirée : l'interface GTK s'ouvre normalement avec une liste vide, ce qui permet à l'utilisateur de cliquer sur **« Nouveau groupe »** et d'organiser ses radios dès le premier lancement.
