#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

VERSION="0.1.0"
ARCH="x86_64"
ARCHIVE_NAME="timonde-${VERSION}-linux-${ARCH}.tar.gz"
STAGING_DIR="${ROOT_DIR}/temp/tarball_staging/timonde-${VERSION}"

echo "📦 Préparation de l'archive binaire universelle : ${ARCHIVE_NAME}"

# 1. Compilation release si nécessaire
echo "⚡ Compilation release..."
(cd "${ROOT_DIR}" && cargo build --release)

# 2. Nettoyage et arborescence
rm -rf "${ROOT_DIR}/temp/tarball_staging"
mkdir -p "${STAGING_DIR}/bin"
mkdir -p "${STAGING_DIR}/share/applications"
mkdir -p "${STAGING_DIR}/share/icons/hicolor/scalable/apps"
mkdir -p "${STAGING_DIR}/share/icons/hicolor/scalable/panel"
mkdir -p "${STAGING_DIR}/share/timonde/scripts"
mkdir -p "${STAGING_DIR}/share/timonde/bouquets"
mkdir -p "${STAGING_DIR}/share/timonde/examples"

# 3. Copie des fichiers
install -m 755 "${ROOT_DIR}/target/release/timonde" "${STAGING_DIR}/bin/timonde"
install -m 644 "${ROOT_DIR}/data/timonde.desktop" "${STAGING_DIR}/share/applications/timonde.desktop"
install -m 644 "${ROOT_DIR}/data/icons/timonde_on.svg" "${STAGING_DIR}/share/icons/hicolor/scalable/apps/timonde_on.svg"
install -m 644 "${ROOT_DIR}/data/icons/timonde_off.svg" "${STAGING_DIR}/share/icons/hicolor/scalable/panel/timonde_off.svg"
install -m 644 "${ROOT_DIR}/data/icons/timonde_on.svg" "${STAGING_DIR}/share/icons/hicolor/scalable/panel/timonde_on.svg"
install -m 644 "${ROOT_DIR}/data/icons/timonde_error.svg" "${STAGING_DIR}/share/icons/hicolor/scalable/panel/timonde_error.svg"

install -m 755 "${ROOT_DIR}/data/scripts/reorder_groups.py" "${STAGING_DIR}/share/timonde/scripts/reorder_groups.py"
install -m 755 "${ROOT_DIR}/data/scripts/edit_station.py" "${STAGING_DIR}/share/timonde/scripts/edit_station.py"
install -m 755 "${ROOT_DIR}/data/scripts/browse_bouquets.py" "${STAGING_DIR}/share/timonde/scripts/browse_bouquets.py"
install -m 644 "${ROOT_DIR}/data/scripts/timonde_i18n.py" "${STAGING_DIR}/share/timonde/scripts/timonde_i18n.py"

install -m 644 "${ROOT_DIR}"/data/bouquets/*.xml "${STAGING_DIR}/share/timonde/bouquets/"
install -m 644 "${ROOT_DIR}"/data/examples/* "${STAGING_DIR}/share/timonde/examples/"

# Copie des 55 traductions
for mo in "${ROOT_DIR}"/po/locale/*/LC_MESSAGES/timonde.mo; do
    if [ -f "$mo" ]; then
        lang=$(basename $(dirname $(dirname "$mo")))
        mkdir -p "${STAGING_DIR}/share/locale/${lang}/LC_MESSAGES"
        install -m 644 "$mo" "${STAGING_DIR}/share/locale/${lang}/LC_MESSAGES/timonde.mo"
    fi
done

# 4. Script install.sh bi-mode
cat << 'INSTALL_EOF' > "${STAGING_DIR}/install.sh"
#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$EUID" -eq 0 ]; then
    PREFIX="/usr/local"
    echo "🔧 Installation système (pour tous les utilisateurs) dans ${PREFIX}..."
else
    PREFIX="${HOME}/.local"
    echo "👤 Installation utilisateur dans ${PREFIX} (aucun mot de passe sudo requis)..."
fi

BINDIR="${PREFIX}/bin"
DATADIR="${PREFIX}/share"

mkdir -p "${BINDIR}"
mkdir -p "${DATADIR}/applications"
mkdir -p "${DATADIR}/icons/hicolor/scalable/apps"
mkdir -p "${DATADIR}/icons/hicolor/scalable/panel"
mkdir -p "${DATADIR}/timonde"

cp -f "${DIR}/bin/timonde" "${BINDIR}/"
chmod 755 "${BINDIR}/timonde"

cp -f "${DIR}/share/applications/timonde.desktop" "${DATADIR}/applications/"
cp -rf "${DIR}/share/icons/"* "${DATADIR}/icons/"
cp -rf "${DIR}/share/timonde/"* "${DATADIR}/timonde/"

if [ -d "${DIR}/share/locale" ]; then
    mkdir -p "${DATADIR}/locale"
    cp -rf "${DIR}/share/locale/"* "${DATADIR}/locale/"
fi

# Actualisation des caches de bureau si disponibles
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "${DATADIR}/icons/hicolor" >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${DATADIR}/applications" >/dev/null 2>&1 || true
fi

echo ""
echo "✨ TiMonde 0.1.0 est installé avec succès !"
echo "   - Binaire : ${BINDIR}/timonde"
echo "   - Vous pouvez le lancer en tapant : timonde"
echo "   - Ou le retrouver directement dans le menu de vos applications (section Multimédia / Son)."
INSTALL_EOF
chmod +x "${STAGING_DIR}/install.sh"

# 5. Script uninstall.sh bi-mode
cat << 'UNINSTALL_EOF' > "${STAGING_DIR}/uninstall.sh"
#!/bin/bash
set -e

if [ "$EUID" -eq 0 ]; then
    PREFIX="/usr/local"
    echo "🗑️ Désinstallation système depuis ${PREFIX}..."
else
    PREFIX="${HOME}/.local"
    echo "🗑️ Désinstallation utilisateur depuis ${PREFIX}..."
fi

rm -f "${PREFIX}/bin/timonde"
rm -f "${PREFIX}/share/applications/timonde.desktop"
rm -f "${PREFIX}/share/icons/hicolor/scalable/apps/timonde_on.svg"
rm -f "${PREFIX}/share/icons/hicolor/scalable/panel/timonde_off.svg"
rm -f "${PREFIX}/share/icons/hicolor/scalable/panel/timonde_on.svg"
rm -f "${PREFIX}/share/icons/hicolor/scalable/panel/timonde_error.svg"
rm -rf "${PREFIX}/share/timonde"

for mo_dir in "${PREFIX}/share/locale/"*/LC_MESSAGES; do
    rm -f "${mo_dir}/timonde.mo"
done

echo "✅ TiMonde a été désinstallé proprement sans laisser de trace."
UNINSTALL_EOF
chmod +x "${STAGING_DIR}/uninstall.sh"

# 6. README.md explicatif
cat << 'README_EOF' > "${STAGING_DIR}/README.md"
# TiMonde - Lecteur de flux radio ultra-léger (< 15 Mo de RAM)

## Installation rapide

Pour installer TiMonde sur votre système :

### 1. Installation en session utilisateur (sans mot de passe root / Live USB) :
```bash
./install.sh
```
TiMonde sera installé dans `~/.local/bin` et `~/.local/share`.

### 2. Installation pour tous les utilisateurs du système :
```bash
sudo ./install.sh
```
TiMonde sera installé dans `/usr/local/bin` et `/usr/local/share`.

## Désinstallation
```bash
./uninstall.sh
# ou si installé avec sudo :
sudo ./uninstall.sh
```

## Dépendances système courantes :
TiMonde utilise les bibliothèques multimédia standards de votre distribution :
- GStreamer (`gstreamer1.0`, plugins `base` et `good`)
- Python 3 avec GObject (`python3-gi` ou `python3-gobject`)
- GTK 3
README_EOF

# 7. Création de l'archive tar.gz
(cd "${ROOT_DIR}/temp/tarball_staging" && tar -czf "${ROOT_DIR}/${ARCHIVE_NAME}" "timonde-${VERSION}")
cp "${ROOT_DIR}/${ARCHIVE_NAME}" "${SCRIPT_DIR}/${ARCHIVE_NAME}"
rm -rf "${ROOT_DIR}/temp/tarball_staging"

echo "✅ Archive binaire universelle générée avec succès :"
echo "   - ${ROOT_DIR}/${ARCHIVE_NAME}"
echo "   - ${SCRIPT_DIR}/${ARCHIVE_NAME}"
