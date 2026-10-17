#!/bin/bash
# =============================================================================
# TiMonde — Script d'installation intelligent avec détection d'environnement
# =============================================================================
# Céline (Argon bis) : Zéro compromis, zéro dépendance parasite.
# Ce script inspecte le système en cours, identifie le bureau graphique actif
# (GNOME, XFCE, Cinnamon, KDE Plasma, MATE, IceWM/antiX, etc.) et installe
# strictement les dépendances nécessaires au bon fonctionnement de l'applet.
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}"

echo "=========================================================="
echo "    TiMonde — Déploiement et Détection d'Environnement    "
echo "=========================================================="

# 1. Vérification des droits administrateur
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo "Erreur : Ce script nécessite les droits root ou 'sudo'." >&2
        exit 1
    fi
fi

# 2. Détection de l'environnement graphique
ACTIVE_DESKTOP="${XDG_CURRENT_DESKTOP:-${DESKTOP_SESSION:-}}"
ACTIVE_DESKTOP_UPPER=$(echo "${ACTIVE_DESKTOP}" | tr '[:lower:]' '[:upper:]')
SESSION_TYPE="${XDG_SESSION_TYPE:-x11}"

echo "[1/4] Détection de l'environnement graphique :"
echo "      Bureau actif : ${ACTIVE_DESKTOP:-Inconnu} (${SESSION_TYPE})"

DETECTED_GNOME=0
DETECTED_XFCE=0
DETECTED_CINNAMON=0
DETECTED_KDE=0
DETECTED_MATE=0

if echo "${ACTIVE_DESKTOP_UPPER}" | grep -q "GNOME" || command -v gnome-shell >/dev/null 2>&1; then
    DETECTED_GNOME=1
fi
if echo "${ACTIVE_DESKTOP_UPPER}" | grep -q "XFCE" || command -v xfce4-panel >/dev/null 2>&1; then
    DETECTED_XFCE=1
fi
if echo "${ACTIVE_DESKTOP_UPPER}" | grep -q "CINNAMON" || command -v cinnamon >/dev/null 2>&1; then
    DETECTED_CINNAMON=1
fi
if echo "${ACTIVE_DESKTOP_UPPER}" | grep -q "KDE" || command -v plasmashell >/dev/null 2>&1; then
    DETECTED_KDE=1
fi
if echo "${ACTIVE_DESKTOP_UPPER}" | grep -q "MATE" || command -v mate-panel >/dev/null 2>&1; then
    DETECTED_MATE=1
fi

# 3. Détermination des paquets à installer selon le gestionnaire de paquets
echo "[2/4] Analyse des dépendances requises..."

if command -v apt-get >/dev/null 2>&1; then
    # Base Debian / Ubuntu / Linux Mint
    DEPS=(
        "libc6"
        "libgstreamer1.0-0"
        "gstreamer1.0-plugins-base"
        "gstreamer1.0-plugins-good"
        "gstreamer1.0-plugins-bad"
        "gstreamer1.0-libav"
        "glib-networking"
        "python3"
        "python3-gi"
        "python3-dbus"
        "gir1.2-gtk-3.0"
        "gir1.2-dbusmenu-gtk3-0.4"
    )

    # Dépendance contextuelle pour GNOME Shell
    # Sous GNOME Shell natif, la barre supérieure ne supporte pas les applets de notification sans extension.
    if [ "${DETECTED_GNOME}" -eq 1 ] && ! echo "${ACTIVE_DESKTOP_UPPER}" | grep -q -E "XFCE|CINNAMON|MATE|KDE"; then
        echo "      -> GNOME détecté comme environnement principal."
        if ! dpkg -s gnome-shell-extension-appindicator >/dev/null 2>&1; then
            echo "      -> Ajout de 'gnome-shell-extension-appindicator' pour l'affichage de l'icône dans GNOME."
            DEPS+=("gnome-shell-extension-appindicator")
        fi
    fi

    echo "[3/4] Installation des dépendances système ciblées..."
    ${SUDO} apt-get update -qq || true
    ${SUDO} apt-get install -y --no-install-recommends "${DEPS[@]}"

    # 4. Installation du paquet TiMonde
    echo "[4/4] Déploiement de TiMonde..."
    DEB_FILE=$(ls -t "${ROOT_DIR}"/timonde_*_amd64.deb "${ROOT_DIR}"/packaging/deb/timonde_*_amd64.deb 2>/dev/null | head -n 1 || true)
    if [ -n "${DEB_FILE}" ] && [ -f "${DEB_FILE}" ]; then
        echo "      Installation du paquet Debian : ${DEB_FILE}"
        ${SUDO} apt-get install -y --no-install-recommends "${DEB_FILE}"
    else
        echo "      Paquet .deb introuvable, compilation et installation via Makefile..."
        ${SUDO} make -C "${ROOT_DIR}" install
    fi

elif command -v dnf >/dev/null 2>&1; then
    # Fedora / RHEL
    echo "[3/4] Déploiement sur système RPM/Fedora..."
    ${SUDO} dnf install -y gstreamer1-plugins-base gstreamer1-plugins-good gstreamer1-plugins-bad-free glib-networking python3-gobject gtk3 libdbusmenu-gtk3
    ${SUDO} make -C "${ROOT_DIR}" install
elif command -v pacman >/dev/null 2>&1; then
    # Arch Linux
    echo "[3/4] Déploiement sur système Arch Linux..."
    ${SUDO} pacman -S --needed --noconfirm gst-plugins-base gst-plugins-good gst-plugins-bad glib-networking python-gobject gtk3 libdbusmenu-gtk3
    ${SUDO} make -C "${ROOT_DIR}" install
else
    echo "[3/4] Gestionnaire de paquets inconnu, installation via Makefile..."
    ${SUDO} make -C "${ROOT_DIR}" install
fi

# 5. Ajustements post-installation spécifiques à l'environnement
if [ "${DETECTED_CINNAMON}" -eq 1 ]; then
    echo "      Configuration spécifique Cinnamon (clic unifié)..."
    if [ -f "/usr/share/cinnamon/applets/xapp-status@cinnamon.org/applet.js" ] && [ -f "/usr/share/timonde/scripts/patch_cinnamon_status_applet.py" ]; then
        ${SUDO} python3 /usr/share/timonde/scripts/patch_cinnamon_status_applet.py || true
    fi
fi

if [ "${DETECTED_GNOME}" -eq 1 ] && ! echo "${ACTIVE_DESKTOP_UPPER}" | grep -q -E "XFCE|CINNAMON|MATE|KDE"; then
    echo "      Vérification de l'activation de l'extension AppIndicator GNOME..."
    if command -v gnome-extensions >/dev/null 2>&1; then
        gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com 2>/dev/null || true
        gnome-extensions enable ubuntu-appindicators@ubuntu.com 2>/dev/null || true
    fi
fi

echo "=========================================================="
echo "    Installation de TiMonde terminée avec succès !        "
echo "    Vous pouvez lancer 'timonde' depuis le terminal       "
echo "    ou via le menu des applications.                      "
echo "=========================================================="
