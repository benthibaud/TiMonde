Name:           timonde
Version:        0.2.5
Release:        1%{?dist}
Summary:        Lecteur de webradios ultra-léger et discret pour la barre des tâches Linux

License:        GPL-3.0-or-later
URL:            https://github.com/benthibaud/TiMonde
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz

BuildRequires:  cargo
BuildRequires:  rust
BuildRequires:  gcc
Requires:       gstreamer1
Requires:       gstreamer1-plugins-base
Requires:       gstreamer1-plugins-good
Requires:       gstreamer1-plugins-bad-free
Requires:       gstreamer1-plugin-libav
Requires:       glib-networking
Requires:       python3
Requires:       python3-gobject
Requires:       gtk3
Requires:       libdbusmenu-gtk3
Requires:       python3-dbus
Suggests:       gnome-shell-extension-appindicator

%description
TiMonde est un lecteur de radios universel et économe en ressources (< 15 Mo de RAM),
conçu pour s'intégrer discrètement dans la zone de notification de tous les
environnements de bureau Linux (XFCE, Cinnamon, MATE, GNOME, KDE Plasma, etc.).

%prep
%autosetup

%build
cargo build --release

%install
make DESTDIR=%{buildroot} PREFIX=/usr install

%files
/usr/bin/timonde
/usr/share/applications/timonde.desktop
/usr/share/icons/hicolor/scalable/apps/timonde_on.svg
/usr/share/icons/hicolor/scalable/panel/timonde_off.svg
/usr/share/icons/hicolor/scalable/panel/timonde_on.svg
/usr/share/icons/hicolor/scalable/panel/timonde_error.svg
/usr/share/icons/hicolor/*/apps/timonde_*.png
/usr/share/icons/hicolor/*/panel/timonde_*.png
/usr/share/timonde/scripts/reorder_groups.py
/usr/share/timonde/scripts/edit_station.py
/usr/share/timonde/scripts/browse_bouquets.py
/usr/share/timonde/scripts/timonde_xembed_bridge.py
/usr/share/timonde/scripts/show_menu.py
/usr/share/timonde/scripts/patch_cinnamon_status_applet.py
/usr/share/timonde/scripts/timonde_settings.py
/usr/share/timonde/scripts/gnome_tray_helper.py
/usr/share/timonde/bouquets/*.xml
/usr/share/timonde/examples/*
/usr/share/timonde/scripts/timonde_i18n.py
/usr/share/timonde/scripts/timonde_common.py
/usr/share/timonde/scripts/timonde_world_data.py
/usr/share/timonde/icons/pan-end-symbolic*.svg
/usr/share/locale/*/LC_MESSAGES/timonde.mo
/usr/share/metainfo/io.github.benthibaud.timonde.metainfo.xml

%post
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || :
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q || :
fi

# Détection d'environnement de bureau et configurations contextuelles
# 1. Cinnamon : harmonisation automatique du clic gauche/droit unifié
if [ -f "/usr/share/cinnamon/applets/xapp-status@cinnamon.org/applet.js" ] && [ -f "/usr/share/timonde/scripts/patch_cinnamon_status_applet.py" ]; then
    python3 /usr/share/timonde/scripts/patch_cinnamon_status_applet.py --system || :
fi

# 2. GNOME Shell : vérification de la présence de l'extension AppIndicator
if command -v gnome-shell >/dev/null 2>&1; then
    echo "------------------------------------------------------------------"
    echo " [TiMonde] Bureau GNOME détecté :"
    echo " Pour afficher l'icône dans la barre supérieure sous GNOME,"
    echo " installez l'extension AppIndicator si besoin :"
    echo "   gnome-shell-extension-appindicator"
    echo "------------------------------------------------------------------"
fi

%postun
if [ "$1" -eq 0 ]; then
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || :
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q || :
    fi
    # Restauration de l'applet Cinnamon originale si backup présent
    if [ -f "/usr/share/cinnamon/applets/xapp-status@cinnamon.org/applet.js.orig_timonde" ]; then
        mv -f /usr/share/cinnamon/applets/xapp-status@cinnamon.org/applet.js.orig_timonde /usr/share/cinnamon/applets/xapp-status@cinnamon.org/applet.js 2>/dev/null || :
    fi
    rm -f /etc/apt/apt.conf.d/99timonde-cinnamon 2>/dev/null || :
fi

%changelog
* Sun Nov 08 2026 Ben Thibaud <b_thibaud@laposte.net> - 0.2.5-1
- Démarrage du Jalon 2 de la Roadmap (Option B : zéro plantage, zéro blocage UI)
- Élimination des boucles récursives dialog.run() et sécurisation des verrous Rust

* Sun Nov 08 2026 Ben Thibaud <b_thibaud@laposte.net> - 0.2.4-1
- Détection des flux réaffectés et stations saisonnières via extraction ICY en direct
- Bouton interactif « Aligner le nom » en cas de divergence avec le flux d'antenne
- Module de vérification d'unicité et contribution guidée vers Radio-Browser
- Prise en charge des serveurs SHOUTcast v1 (protocole ICY 200 OK)
- Icônes contrastées adaptatives pour thèmes sombres et sélections claires/vertes
- Bouquet France d'Outre-mer 100 % opérationnel (116/116 stations, codes ISO GP/MQ/GF/PM/RE/YT/NC/PF/WF)

* Fri Nov 06 2026 Ben Thibaud <b_thibaud@laposte.net> - 0.2.3-1
- Navigation arborescente naturelle Gtk.TreeStore dans l'atelier « Mes Radios »
- Gestion fidèle des radios sans groupe au premier niveau (Option 1 racine directe)
- Maintien du groupe déployé et sélectionné lors du tri alphabétique A-Z
- Vue d'ensemble repliée par défaut à l'ouverture pour une lisibilité immédiate
- Sécurisation ergonomique de la suppression avec décompte récursif des stations
- Factorisation de la boîte de dialogue textuelle prompt_text_dialog et purge du code mort
- Centralisation de la version applicative TIMONDE_VERSION

* Thu Oct 29 2026 Ben Thibaud <b_thibaud@laposte.net> - 0.2.2-1
- Optimisation de la mémoire vive au repos (< 15 Mo de RAM avec malloc_trim)
- Anti-rebond sur la persistance du volume sonore (debounce 300 ms)
- Factorisation des composants partagés (RepairStreamDialog, _run_batch_checks)
- Harmonisation du Design System GTK3 (status_markup, TreeView adaptatifs sans ascenseur horizontal forcé)
- Parité absolue et complétude des 56 catalogues Gettext
- Documentation technique consolidée (docs/ARCHITECTURE.md)

* Wed Oct 28 2026 Ben Thibaud <b_thibaud@laposte.net> - 0.2.1-1
- Modularisation de l'architecture Rust (découpage en sous-modules src/tray/)
- Factorisation du socle partagé Python timonde_common.py
- Ajout du fichier exemple complet pour la France d'Outre-mer (8 territoires)
- Passerelle dynamique vers Radio-Browser pour les pays sans bouquet DAB+ pré-embarqué
- Restauration et mise à jour des flux radio hors-ligne (BF, BJ, CD, KH, BD, FR)
- Tests unitaires et multithread-safety renforcés

* Sat Oct 17 2026 Ben Thibaud <b_thibaud@laposte.net> - 0.2.0-1
- Traduction intégrale native dans 56 langues avec catalogues Gettext compilés (.mo)
- Intégration de 146 bouquets DAB+ et sélections officielles par pays
- 19 sélections thématiques restaurables (ajout de Bollywood, etc.)
- Refonte ergonomique du sélecteur de bouquets et de l'organiseur de favoris
- Outil interactif de réparation des flux radio hors-ligne via Radio-Browser
- Correction des entités Pango (&amp;) et robustesse du runtime Python

* Fri Oct 16 2026 Ben Thibaud <b_thibaud@laposte.net> - 0.1.3-1
- Amélioration de la lisibilité et contraste maximal dans la barre des tâches (dark/light)
- Cartouche en écoute aéré avec copie du titre dans le presse-papier au clic
- Centre de contrôle paramètres unifié avec onglets interactifs directs (Option 2)
- Écoute et vérification directe des flux dans l'explorateur et l'organisateur

* Fri Oct 16 2026 Ben Thibaud <b_thibaud@laposte.net> - 0.1.2-1
- Recherche de pays multilingue intégrale dans les 55 langues pour les bouquets DAB+ et Radio-Browser
- Enrichissement des alias linguistiques (anglais et variantes orthographiques Radio-Browser)
- Persistance du volume sonore, écriture XML atomique et isolation de la minuterie de veille

* Sat Oct 10 2026 Ben Thibaud <b_thibaud@laposte.net> - 0.1.1-1
- Harmonisation multi-bureaux (LXQt, XFCE, Cinnamon, KDE Plasma, GNOME)
- Clic gauche instantané 0 ms via XTest sous X11 et fallback show_menu.py
- Support complet des thèmes clairs/sombres Breeze KDE Plasma
- Empaquetage complet des icônes multi-résolutions et scripts compagnons
