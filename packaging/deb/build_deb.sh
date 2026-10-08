#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

VERSION="0.1.0"
ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")
PACKAGE_NAME="timonde_${VERSION}_${ARCH}.deb"
STAGING_DIR="${ROOT_DIR}/temp/deb_staging"

echo "📦 Préparation du paquet Debian/Ubuntu/Mint : ${PACKAGE_NAME}"

# 1. Compilation du binaire release si nécessaire
echo "⚡ Compilation de timonde en mode release..."
(cd "${ROOT_DIR}" && cargo build --release)

# 2. Nettoyage et création de l'arborescence
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

# 3. Fichier de contrôle Debian (Zenity retiré, GTK3 natif)
cat << CONTROL_EOF > "${STAGING_DIR}/DEBIAN/control"
Package: timonde
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: ${ARCH}
Depends: libc6, libgstreamer1.0-0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, python3, python3-gi, gir1.2-gtk-3.0
Maintainer: Ben Thibaud <b_thibaud@laposte.net>
Description: Lecteur de webradios ultra-léger et discret pour la barre des tâches Linux
 TiMonde est un lecteur de radios universel et économe en ressources (< 15 Mo de RAM),
 conçu pour s'intégrer discrètement dans la zone de notification de tous les
 bureaux Linux (XFCE, Cinnamon, MATE, GNOME, KDE, etc.).
CONTROL_EOF

# 4. Installation des fichiers dans le paquet
install -m 755 "${ROOT_DIR}/target/release/timonde" "${STAGING_DIR}/usr/bin/timonde"
install -m 644 "${ROOT_DIR}/data/timonde.desktop" "${STAGING_DIR}/usr/share/applications/timonde.desktop"
install -m 644 "${ROOT_DIR}/data/icons/timonde_on.svg" "${STAGING_DIR}/usr/share/icons/hicolor/scalable/apps/timonde_on.svg"
install -m 644 "${ROOT_DIR}/data/icons/timonde_off.svg" "${STAGING_DIR}/usr/share/icons/hicolor/scalable/panel/timonde_off.svg"
install -m 644 "${ROOT_DIR}/data/icons/timonde_on.svg" "${STAGING_DIR}/usr/share/icons/hicolor/scalable/panel/timonde_on.svg"
install -m 644 "${ROOT_DIR}/data/icons/timonde_error.svg" "${STAGING_DIR}/usr/share/icons/hicolor/scalable/panel/timonde_error.svg"
install -m 755 "${ROOT_DIR}/data/scripts/reorder_groups.py" "${STAGING_DIR}/usr/share/timonde/scripts/reorder_groups.py"
install -m 755 "${ROOT_DIR}/data/scripts/edit_station.py" "${STAGING_DIR}/usr/share/timonde/scripts/edit_station.py"
install -m 755 "${ROOT_DIR}/data/scripts/browse_bouquets.py" "${STAGING_DIR}/usr/share/timonde/scripts/browse_bouquets.py"
install -m 644 "${ROOT_DIR}/data/scripts/timonde_i18n.py" "${STAGING_DIR}/usr/share/timonde/scripts/timonde_i18n.py"
install -m 644 "${ROOT_DIR}"/data/bouquets/*.xml "${STAGING_DIR}/usr/share/timonde/bouquets/"
install -m 644 "${ROOT_DIR}"/data/examples/* "${STAGING_DIR}/usr/share/timonde/examples/"

for mo in "${ROOT_DIR}"/po/locale/*/LC_MESSAGES/timonde.mo; do
    if [ -f "$mo" ]; then
        lang=$(basename $(dirname $(dirname "$mo")))
        mkdir -p "${STAGING_DIR}/usr/share/locale/${lang}/LC_MESSAGES"
        install -m 644 "$mo" "${STAGING_DIR}/usr/share/locale/${lang}/LC_MESSAGES/timonde.mo"
    fi
done

# 5. Construction du paquet .deb
dpkg-deb --build --root-owner-group "${STAGING_DIR}" "${ROOT_DIR}/${PACKAGE_NAME}"
cp "${ROOT_DIR}/${PACKAGE_NAME}" "${SCRIPT_DIR}/${PACKAGE_NAME}"
rm -rf "${STAGING_DIR}"

echo "✅ Paquet généré avec succès :"
echo "   - ${ROOT_DIR}/${PACKAGE_NAME}"
echo "   - ${SCRIPT_DIR}/${PACKAGE_NAME}"
