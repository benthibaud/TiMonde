#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

VERSION="0.1.1"
ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")
PACKAGE_NAME="timonde_${VERSION}_${ARCH}.deb"
STAGING_DIR="${ROOT_DIR}/temp/deb_staging"

echo "Préparation du paquet Debian/Ubuntu/Mint : ${PACKAGE_NAME}"

# 1. Compilation du binaire release si nécessaire
if command -v cargo >/dev/null 2>&1; then
    (cd "${ROOT_DIR}" && cargo build --release)
elif [ ! -f "${ROOT_DIR}/target/release/timonde" ]; then
    echo "cargo est requis pour compiler timonde."
    exit 1
fi

# 2. Génération des icônes matricielles PNG (16x16 à 256x256)
python3 "${ROOT_DIR}/data/scripts/generate_png_icons.py"

# 3. Nettoyage et création de l'arborescence
rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}/DEBIAN"
mkdir -p "${STAGING_DIR}/usr/bin"
mkdir -p "${STAGING_DIR}/usr/share/applications"
mkdir -p "${STAGING_DIR}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${STAGING_DIR}/usr/share/icons/hicolor/scalable/panel"
mkdir -p "${STAGING_DIR}/usr/share/timonde/scripts"
mkdir -p "${STAGING_DIR}/usr/share/timonde/bouquets"
mkdir -p "${STAGING_DIR}/usr/share/timonde/examples"
mkdir -p "${STAGING_DIR}/usr/share/locale/fr/LC_MESSAGES"
mkdir -p "${STAGING_DIR}/usr/share/locale/en/LC_MESSAGES"

# 4. Fichier de contrôle Debian
cat << CONTROL_EOF > "${STAGING_DIR}/DEBIAN/control"
Package: timonde
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: ${ARCH}
Depends: libc6, libgstreamer1.0-0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, gstreamer1.0-plugins-bad, gstreamer1.0-libav, glib-networking, python3, python3-gi, gir1.2-gtk-3.0, gir1.2-dbusmenu-gtk3-0.4
Maintainer: Ben Thibaud <b_thibaud@laposte.net>
Description: Lecteur de webradios ultra-léger et discret pour la barre des tâches Linux
 TiMonde est un lecteur de radios universel et économe en ressources (< 15 Mo de RAM),
 conçu pour s'intégrer discrètement dans la zone de notification de tous les
 bureaux Linux (IceWM, Fluxbox, Cinnamon, XFCE, MATE, GNOME, KDE, etc.).
CONTROL_EOF

# 5. Scripts postinst et postrm (rafraîchissement du cache d'icônes et menu desktop)
cat << 'POSTINST_EOF' > "${STAGING_DIR}/DEBIAN/postinst"
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q || true
fi
exit 0
POSTINST_EOF
chmod 755 "${STAGING_DIR}/DEBIAN/postinst"

cat << 'POSTRM_EOF' > "${STAGING_DIR}/DEBIAN/postrm"
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q || true
    fi
fi
exit 0
POSTRM_EOF
chmod 755 "${STAGING_DIR}/DEBIAN/postrm"

# 6. Installation des fichiers dans le paquet
install -m 755 "${ROOT_DIR}/target/release/timonde" "${STAGING_DIR}/usr/bin/timonde"
install -m 644 "${ROOT_DIR}/data/timonde.desktop" "${STAGING_DIR}/usr/share/applications/timonde.desktop"
mkdir -p "${STAGING_DIR}/usr/share/metainfo"
install -m 644 "${ROOT_DIR}/data/io.github.benthibaud.timonde.metainfo.xml" "${STAGING_DIR}/usr/share/metainfo/io.github.benthibaud.timonde.metainfo.xml"
mkdir -p "${STAGING_DIR}/usr/share/doc/timonde"
install -m 644 "${ROOT_DIR}/packaging/deb/copyright" "${STAGING_DIR}/usr/share/doc/timonde/copyright"

# Icônes vectorielles SVG
install -m 644 "${ROOT_DIR}/data/icons/timonde_on.svg" "${STAGING_DIR}/usr/share/icons/hicolor/scalable/apps/timonde_on.svg"
install -m 644 "${ROOT_DIR}/data/icons/timonde_off.svg" "${STAGING_DIR}/usr/share/icons/hicolor/scalable/panel/timonde_off.svg"
install -m 644 "${ROOT_DIR}/data/icons/timonde_on.svg" "${STAGING_DIR}/usr/share/icons/hicolor/scalable/panel/timonde_on.svg"
install -m 644 "${ROOT_DIR}/data/icons/timonde_error.svg" "${STAGING_DIR}/usr/share/icons/hicolor/scalable/panel/timonde_error.svg"

# Icônes matricielles PNG multi-résolutions (16, 22, 24, 32, 48, 64, 128, 256)
cp -r "${ROOT_DIR}/data/icons/hicolor"/* "${STAGING_DIR}/usr/share/icons/hicolor/"

# Scripts et modules
install -m 755 "${ROOT_DIR}/data/scripts/reorder_groups.py" "${STAGING_DIR}/usr/share/timonde/scripts/reorder_groups.py"
install -m 755 "${ROOT_DIR}/data/scripts/edit_station.py" "${STAGING_DIR}/usr/share/timonde/scripts/edit_station.py"
install -m 755 "${ROOT_DIR}/data/scripts/browse_bouquets.py" "${STAGING_DIR}/usr/share/timonde/scripts/browse_bouquets.py"
install -m 755 "${ROOT_DIR}/data/scripts/timonde_xembed_bridge.py" "${STAGING_DIR}/usr/share/timonde/scripts/timonde_xembed_bridge.py"
install -m 644 "${ROOT_DIR}/data/scripts/timonde_i18n.py" "${STAGING_DIR}/usr/share/timonde/scripts/timonde_i18n.py"
install -m 644 "${ROOT_DIR}"/data/bouquets/*.xml "${STAGING_DIR}/usr/share/timonde/bouquets/"
install -m 644 "${ROOT_DIR}"/data/examples/* "${STAGING_DIR}/usr/share/timonde/examples/"

# Localisation
for mo in "${ROOT_DIR}"/po/locale/*/LC_MESSAGES/timonde.mo; do
    if [ -f "$mo" ]; then
        lang=$(basename $(dirname $(dirname "$mo")))
        mkdir -p "${STAGING_DIR}/usr/share/locale/${lang}/LC_MESSAGES"
        install -m 644 "$mo" "${STAGING_DIR}/usr/share/locale/${lang}/LC_MESSAGES/timonde.mo"
    fi
done

# 7. Construction du paquet .deb
dpkg-deb --build --root-owner-group "${STAGING_DIR}" "${ROOT_DIR}/${PACKAGE_NAME}"
cp "${ROOT_DIR}/${PACKAGE_NAME}" "${SCRIPT_DIR}/${PACKAGE_NAME}"
rm -rf "${STAGING_DIR}"

echo "Paquet généré avec succès :"
echo "   - ${ROOT_DIR}/${PACKAGE_NAME}"
echo "   - ${SCRIPT_DIR}/${PACKAGE_NAME}"
