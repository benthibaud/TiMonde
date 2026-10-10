#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

VERSION="0.1.1"
ARCH="x86_64"
RPM_NAME="timonde-${VERSION}-1.${ARCH}.rpm"

echo "Préparation du paquet RPM (Fedora, openSUSE, RHEL) : ${RPM_NAME}"

# 1. Compilation release
echo "Compilation release..."
(cd "${ROOT_DIR}" && cargo build --release)

# 2. Génération du paquet RPM avec cargo generate-rpm
export PATH="${HOME}/.cargo/bin:${PATH}"

if ! command -v cargo-generate-rpm >/dev/null 2>&1; then
    echo "cargo-generate-rpm est requis."
    exit 1
fi

echo "Construction du RPM..."
(cd "${ROOT_DIR}" && cargo generate-rpm --auto-req disabled)

# 3. Déplacement du RPM généré
if [ -f "${ROOT_DIR}/target/generate-rpm/${RPM_NAME}" ]; then
    cp -f "${ROOT_DIR}/target/generate-rpm/${RPM_NAME}" "${ROOT_DIR}/${RPM_NAME}"
    cp -f "${ROOT_DIR}/target/generate-rpm/${RPM_NAME}" "${SCRIPT_DIR}/${RPM_NAME}"
    echo "Paquet RPM généré avec succès :"
    echo "   - ${ROOT_DIR}/${RPM_NAME}"
    echo "   - ${SCRIPT_DIR}/${RPM_NAME}"
else
    # Recherche du fichier généré si le nom diffère légèrement
    GENERATED=$(find "${ROOT_DIR}/target/generate-rpm" -name "*.rpm" | head -n 1)
    if [ -n "${GENERATED}" ]; then
        cp -f "${GENERATED}" "${ROOT_DIR}/${RPM_NAME}"
        cp -f "${GENERATED}" "${SCRIPT_DIR}/${RPM_NAME}"
        echo "Paquet RPM généré avec succès :"
        echo "   - ${ROOT_DIR}/${RPM_NAME}"
        echo "   - ${SCRIPT_DIR}/${RPM_NAME}"
    fi
fi
