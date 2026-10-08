# -*- coding: utf-8 -*-
"""
Module d'internationalisation pour TiMonde (Python/GTK).
Supporte Gettext avec repli dynamique transparent sur dictionnaire intégré (FR/EN).
"""

import os
import sys
import locale
import gettext

# Détection de la langue
def is_french():
    env_lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    return env_lang.lower().startswith("fr")

TRANSLATIONS_EN = {
    # --- Éditeur de station (edit_station.py) ---
    "➕ Ajouter une station (TiMonde)": "➕ Add a station (TiMonde)",
    "<b>Entrez les informations de la nouvelle radio :</b>": "<b>Enter new station details:</b>",
    "➕ Ajouter à mes radios": "➕ Add to my stations",
    "⭐ Enregistrer la radio dans mes favoris (TiMonde)": "⭐ Save station to favorites (TiMonde)",
    "<b>Conserver cette radio découverte au hasard dans vos favoris :</b>": "<b>Keep this randomly discovered station in your favorites:</b>",
    "⭐ Conserver dans mes favoris": "⭐ Keep in favorites",
    "✏️ Modifier la radio (TiMonde)": "✏️ Edit station (TiMonde)",
    "<b>Modifier les paramètres de la station :</b>": "<b>Edit station settings:</b>",
    "💾 Enregistrer": "💾 Save",
    "Nom de la radio :": "Station name:",
    "URL du flux audio :": "Audio stream URL:",
    "Groupe / Dossier :": "Group / Folder:",
    "Rechercher ou créer un groupe...": "Search or create group...",
    "(Racine / Aucun groupe)": "(Root / No group)",
    "Pays & Fuseau horaire :": "Country & Timezone:",
    "Rechercher un pays (ex: France, Sénégal, FR, SN)...": "Search country (e.g. France, Senegal, FR, SN)...",
    "Effacer le pays": "Clear country",
    "Aide pays et fuseaux": "Country and timezone help",
    "Fuseau horaire :": "Timezone:",
    "(Fuseau non défini)": "(Timezone not defined)",
    "(Inconnu)": "(Unknown)",
    "(Déduction automatique)": "(Automatic deduction)",
    "(Automatique selon la station)": "(Automatic from station)",
    "(Fuseau unique déduit)": "(Single inferred timezone)",
    "(Métropole ou Outre-mer)": "(Metropolitan or Overseas)",
    "fuseaux disponibles": "available timezones",
    "🗑️ Supprimer cette radio": "🗑️ Delete this station",
    "Annuler": "Cancel",
    "Supprimer « {} » des favoris ?": "Delete « {} » from favorites?",
    "Cette action retirera définitivement cette station de votre collection.": "This action will permanently remove this station from your collection.",
    "🗑️ Supprimer": "🗑️ Delete",
    "Confirmation de suppression": "Confirm deletion",

    # --- Gestionnaire de groupes & réordonnancement (reorder_groups.py) ---
    "↕️ Gestion des groupes, radios et séparateurs (TiMonde)": "↕️ Manage groups, stations and separators (TiMonde)",
        "📁 Nouveau groupe": "📁 New group",
    "➡️ Déplacer vers...": "➡️ Move to...",
    "➕ Créer un nouveau groupe cible...": "➕ Create new target group...",
    "Nom du groupe": "Group name",
    "Contenu": "Contents",
    "Nom / Intertitre": "Name / Header",
    "Détails": "Details",
    "✏️ Modifier": "✏️ Edit",
    "Double-cliquez sur un groupe pour l'ouvrir. Glissez-déposez ou utilisez les boutons pour réordonner.": "Double-click a group to open it. Drag and drop or use buttons to reorder.",
    "⬅️ Retour aux groupes": "⬅️ Back to groups",
    "➕ Ajouter radio": "➕ Add station",
    "📂 Ouvrir": "📂 Open",
    "🔝 Premier": "🔝 Top",
    "⬆️ Monter": "⬆️ Move up",
    "⬇️ Descendre": "⬇️ Move down",
    "➕ Séparateur": "➕ Separator",
    "🔤 Tri A-Z": "🔤 Sort A-Z",
    "✏️ Éditer": "✏️ Edit",
    "💾 Enregistrer et recharger": "💾 Save and reload",
    "Supprimer le groupe « {} » et son contenu ?": "Delete group « {} » and its contents?",
    "Supprimer l'élément sélectionné ?": "Delete selected item?",
    "Nouvelle station": "New station",
    "Nouveau groupe": "New group",
    "Séparateur": "Separator",

    # --- Découverte & Bouquets (browse_bouquets.py) ---
    "📻 Découvrir & Importer des radios (TiMonde)": "📻 Discover & Import stations (TiMonde)",
    "🔎 Recherche Radio-Browser": "🔎 Radio-Browser Search",
    "📂 Fichiers exemples": "📂 Sample Files",
    "<b>🌍 Pays :</b>": "<b>🌍 Country:</b>",
    "<b>Langue :</b>": "<b>Language:</b>",
    "Nom / Mot-clé :": "Name / Keyword:",
    "Genre :": "Genre:",
    "<b>Fichier exemple :</b>": "<b>Sample file:</b>",
    "<i>Aucun fichier sélectionné (XML, CSV, JSON, M3U, PLS)</i>": "<i>No file selected (XML, CSV, JSON, M3U, PLS)</i>",
    "<b>Nom du groupe dans vos favoris :</b>": "<b>Group name in your favorites:</b>",
    "Recherche des flux en cours...": "Searching streams...",
    "Saisissez un mot-clé ou cliquez sur Rechercher pour explorer l'annuaire.": "Enter a keyword or click Search to explore the directory.",
    "🔧 Réparer le flux sélectionné (Radio-Browser)...": "🔧 Repair selected stream (Radio-Browser)...",
    "➕ Importer dans mes favoris": "➕ Import into favorites",
    "Fermer": "Close",

    "⭐ Bouquets vérifiés (DAB+)": "⭐ Verified DAB+ Bouquets",
    "🔎 Annuaire mondial (Radio-Browser)": "🔎 World Directory (Radio-Browser)",
    "📥 Importer mes fichiers": "📥 Import my files",
    "🌍 Pays :": "🌍 Country:",
    "Langue :": "Language:",
    "📂 Ouvrir un XML externe...": "📂 Open external XML...",
    "⭐ Bouquet National": "⭐ National Bouquet",
    "📍 Régions & Locales :": "📍 Regions & Local:",
    "Rechercher une radio par nom, tag ou pays...": "Search station by name, tag or country...",
    "Rechercher": "Search",
    "Genre / Style :": "Genre / Style:",
    "Trier par :": "Sort by:",
    "Votes": "Votes",
    "Clics": "Clicks",
    "Nom": "Name",
    "Débit binaire": "Bitrate",
    "Tout cocher": "Select all",
    "Tout décocher": "Deselect all",
    "➕ Importer la sélection": "➕ Import selection",
    "En ligne": "Online",
    "Lien inactif": "Inactive link",
    "Vérification en cours...": "Checking in progress...",
    "Nom du groupe dans vos favoris :": "Group name in your favorites:",
    "Fermer": "Close",
    "Station": "Station",
    "Genre": "Genre",
    "État": "Status",
    "Présence": "Presence",
    "Nouveau": "New",
    "⚠️ Présent": "⚠️ Already present",
    "🟢 En direct": "🟢 Live",
    "🔴 Inactif": "🔴 Inactive",
    "⚪ Non testé": "⚪ Untested",
}

def get_text(msg):
    if not is_french():
        return TRANSLATIONS_EN.get(msg, msg)
    return msg

# Raccourci _ conventionnel
_ = get_text
