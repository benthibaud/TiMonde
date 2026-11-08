#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

CARGO_TOML="${ROOT_DIR}/Cargo.toml"
VERSION_FROM_CARGO=$(grep -m1 '^version = ' "${CARGO_TOML}" 2>/dev/null | cut -d '"' -f2)
VERSION="${1:-${VERSION_FROM_CARGO:-0.2.5}}"
ARCH="x86_64"
RPM_NAME="timonde-${VERSION}-1.${ARCH}.rpm"
DIST_DIR="${ROOT_DIR}/packaging/dist"
STAGING_DIR="${ROOT_DIR}/temp/rpm_staging"
RPMBUILD_DIR="${ROOT_DIR}/temp/rpmbuild"
mkdir -p "${DIST_DIR}"

echo "Préparation du paquet RPM (Fedora, openSUSE, RHEL) : ${RPM_NAME} (v${VERSION})"

# 1. Compilation du binaire release si nécessaire
if command -v cargo >/dev/null 2>&1; then
    (cd "${ROOT_DIR}" && cargo build --release)
elif [ ! -f "${ROOT_DIR}/target/release/timonde" ]; then
    echo "Erreur : cargo est requis pour compiler le binaire release de timonde."
    exit 1
fi

# 2. Génération des icônes matricielles PNG (16x16 à 256x256)
if [ -f "${ROOT_DIR}/data/scripts/generate_png_icons.py" ]; then
    python3 "${ROOT_DIR}/data/scripts/generate_png_icons.py"
fi

# 3. Compilation des catalogues de traduction Gettext
if [ -f "${ROOT_DIR}/Makefile" ]; then
    make -C "${ROOT_DIR}" mo
fi

# 4. Construction du RPM (Priorité à rpmbuild standard, puis fallback sur cargo-generate-rpm)
BUILT_RPM=""

if command -v rpmbuild >/dev/null 2>&1; then
    echo "Construction avec rpmbuild natif..."
    rm -rf "${RPMBUILD_DIR}"
    mkdir -p "${RPMBUILD_DIR}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS,BUILDROOT}

    # Préparation du BUILDROOT via make install
    BUILDROOT="${RPMBUILD_DIR}/BUILDROOT/timonde-${VERSION}-1.${ARCH}"
    mkdir -p "${BUILDROOT}"
    make -C "${ROOT_DIR}" DESTDIR="${BUILDROOT}" PREFIX=/usr install

    # Copie du fichier spec ajusté pour la version demandée
    SPEC_TMP="${RPMBUILD_DIR}/SPECS/timonde.spec"
    sed -e "s/^Version:.*/Version:        ${VERSION}/" "${SCRIPT_DIR}/timonde.spec" > "${SPEC_TMP}"

    # Construction du binaire RPM (sans ré-exécuter %build / %install car BUILDROOT est déjà préparé)
    rpmbuild --define "_topdir ${RPMBUILD_DIR}" \
             --define "_buildrootdir ${RPMBUILD_DIR}/BUILDROOT" \
             --buildroot "${BUILDROOT}" \
             -bb --short-circuit "${SPEC_TMP}" || \
    rpmbuild --define "_topdir ${RPMBUILD_DIR}" \
             --define "_buildrootdir ${RPMBUILD_DIR}/BUILDROOT" \
             -bb "${SPEC_TMP}"

    FOUND_RPM=$(find "${RPMBUILD_DIR}/RPMS" -name "*.rpm" 2>/dev/null | head -n 1)
    if [ -n "${FOUND_RPM}" ] && [ -f "${FOUND_RPM}" ]; then
        BUILT_RPM="${FOUND_RPM}"
    fi
    rm -rf "${RPMBUILD_DIR}"
elif command -v cargo-generate-rpm >/dev/null 2>&1 || [ -x "${HOME}/.cargo/bin/cargo-generate-rpm" ]; then
    export PATH="${HOME}/.cargo/bin:${PATH}"
    echo "Construction avec cargo-generate-rpm..."
    (cd "${ROOT_DIR}" && cargo generate-rpm --auto-req disabled)
    if [ -f "${ROOT_DIR}/target/generate-rpm/${RPM_NAME}" ]; then
        BUILT_RPM="${ROOT_DIR}/target/generate-rpm/${RPM_NAME}"
    else
        BUILT_RPM=$(find "${ROOT_DIR}/target/generate-rpm" -name "*.rpm" 2>/dev/null | head -n 1)
    fi
else
    echo "------------------------------------------------------------------"
    echo " [TiMonde] Aucun outil de construction RPM détecté."
    echo " Pour générer le paquet RPM, installez au choix :"
    echo "   - rpmbuild : 'sudo dnf install rpm-build' (Fedora) ou 'sudo apt install rpm' (Debian/Ubuntu)"
    echo "   - cargo-generate-rpm : 'cargo install cargo-generate-rpm'"
    echo "------------------------------------------------------------------"
    exit 1
fi

# 5. Déploiement du paquet RPM généré
if [ -n "${BUILT_RPM}" ] && [ -f "${BUILT_RPM}" ]; then
    cp -f "${BUILT_RPM}" "${DIST_DIR}/${RPM_NAME}"
    cp -f "${BUILT_RPM}" "${SCRIPT_DIR}/${RPM_NAME}"
    echo "Paquet RPM généré avec succès :"
    echo "   - ${DIST_DIR}/${RPM_NAME}"
    echo "   - ${SCRIPT_DIR}/${RPM_NAME}"
else
    echo "Erreur : paquet RPM introuvable après la construction."
    exit 1
fi
