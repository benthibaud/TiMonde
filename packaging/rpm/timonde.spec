Name:           timonde
Version:        0.2.0
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
/usr/share/locale/*/LC_MESSAGES/timonde.mo
/usr/share/metainfo/io.github.benthibaud.timonde.metainfo.xml

%changelog
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
