Name:           timonde
Version:        0.1.1
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
/usr/share/timonde/scripts/reorder_groups.py
/usr/share/timonde/scripts/edit_station.py
/usr/share/timonde/scripts/browse_bouquets.py
/usr/share/timonde/bouquets/*.xml
/usr/share/timonde/examples/*
/usr/share/timonde/scripts/timonde_i18n.py
/usr/share/timonde/scripts/timonde_common.py
/usr/share/metainfo/io.github.benthibaud.timonde.metainfo.xml

%changelog
* Mon Oct 06 2026 Ben Thibaud <b_thibaud@laposte.net> - 0.1.0-1
- Version initiale de TiMonde avec gestion avancée des signets et minuteur de veille
