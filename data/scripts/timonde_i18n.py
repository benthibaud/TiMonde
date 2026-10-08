# -*- coding: utf-8 -*-
"""
Module d'internationalisation universel pour TiMonde (Python/GTK).
Clés de référence en Anglais (pivot international).
Traductions intégrées directes et support Gettext pour :
- Français (fr)
- Espagnol (es)
- Allemand (de)
- Portugais (pt)
- Anglais par défaut (en) pour toutes les autres langues.
"""

import os
import sys
import locale
import gettext

def get_current_language():
    env_lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    l = env_lang.lower()
    if l.startswith("fr"): return "fr"
    if l.startswith("es"): return "es"
    if l.startswith("de"): return "de"
    if l.startswith("pt"): return "pt"
    return "en"

TRANSLATIONS_FR = {
    # --- Éditeur de radio (edit_station.py) ---
    "➕ Add a station (TiMonde)": "➕ Ajouter une station (TiMonde)",
    "<b>Enter new station details:</b>": "<b>Entrez les informations de la nouvelle radio :</b>",
    "➕ Add to my stations": "➕ Ajouter à mes radios",
    "⭐ Save station to favorites (TiMonde)": "⭐ Enregistrer la radio dans mes favoris (TiMonde)",
    "<b>Keep this randomly discovered station in your favorites:</b>": "<b>Conserver cette radio découverte au hasard dans vos favoris :</b>",
    "⭐ Keep in favorites": "⭐ Conserver dans mes favoris",
    "✏️ Edit station (TiMonde)": "✏️ Modifier la radio (TiMonde)",
    "<b>Edit station settings:</b>": "<b>Modifier les paramètres de la station :</b>",
    "💾 Save": "💾 Enregistrer",
    "Station name:": "Nom de la radio :",
    "Audio stream URL:": "URL du flux audio :",
    "Group / Folder:": "Groupe / Dossier :",
    "Search or create group...": "Rechercher ou créer un groupe...",
    "(Root / No group)": "(Racine / Aucun groupe)",
    "Country & Timezone:": "Pays & Fuseau horaire :",
    "Search country (e.g. France, Senegal, FR, SN)...": "Rechercher un pays (ex: France, Sénégal, FR, SN)...",
    "Clear country": "Effacer le pays",
    "Timezone:": "Fuseau horaire :",
    "(Timezone not defined)": "(Fuseau non défini)",
    "(Unknown)": "(Inconnu)",
    "(Automatic deduction)": "(Déduction automatique)",
    "(Automatic from station)": "(Automatique selon la station)",
    "(Single inferred timezone)": "(Fuseau unique déduit)",
    "(Metropolitan or Overseas)": "(Métropole ou Outre-mer)",
    "available timezones": "fuseaux disponibles",
    "🗑️ Delete this station": "🗑️ Supprimer cette radio",
    "Cancel": "Annuler",
    "Delete « {} » from favorites?": "Supprimer « {} » des favoris ?",
    "This action will permanently remove this station from your collection.": "Cette action retirera définitivement cette station de votre collection.",
    "🗑️ Delete": "🗑️ Supprimer",

    # --- Réorganisation des groupes (reorder_groups.py) ---
    "↕️ Manage groups, stations and separators (TiMonde)": "↕️ Gestion des groupes, radios et séparateurs (TiMonde)",
    "Double-click a group to open it. Drag and drop or use buttons to reorder.": "Double-cliquez sur un groupe pour l'ouvrir. Glissez-déposez ou utilisez les boutons pour réordonner.",
    "⬅️ Back to groups": "⬅️ Retour aux groupes",
    "➕ Add station": "➕ Ajouter radio",
    "📂 Open": "📂 Ouvrir",
    "📁 New group": "📁 Nouveau groupe",
    "➡️ Move to...": "➡️ Déplacer vers...",
    "➕ Create new target group...": "➕ Créer un nouveau groupe cible...",
    "Group name": "Nom du groupe",
    "Contents": "Contenu",
    "Name / Header": "Nom / Intertitre",
    "Details": "Détails",
    "🔝 Top": "🔝 Premier",
    "⬆️ Move up": "⬆️ Monter",
    "⬇️ Move down": "⬇️ Descendre",
    "➕ Separator": "➕ Séparateur",
    "🔤 Sort A-Z": "🔤 Tri A-Z",
    "✏️ Edit": "✏️ Modifier",
    "💾 Save and reload": "💾 Enregistrer et recharger",

    # --- Découverte des bouquets (browse_bouquets.py) ---
    "📻 Discover & Import stations (TiMonde)": "📻 Découvrir & Importer des radios (TiMonde)",
    "⭐ Verified DAB+ Bouquets": "⭐ Bouquets vérifiés (DAB+)",
    "🔎 Radio-Browser Search": "🔎 Recherche Radio-Browser",
    "📂 Sample Files": "📂 Fichiers exemples",
    "📥 Import my files": "📥 Importer mes fichiers",
    "<b>🌍 Country:</b>": "<b>🌍 Pays :</b>",
    "<b>Language:</b>": "<b>Langue :</b>",
    "Name / Keyword:": "Nom / Mot-clé :",
    "Genre:": "Genre :",
    "<b>Sample file:</b>": "<b>Fichier exemple :</b>",
    "<i>No file selected (XML, CSV, JSON, M3U, PLS)</i>": "<i>Aucun fichier sélectionné (XML, CSV, JSON, M3U, PLS)</i>",
    "<b>Group name in your favorites:</b>": "<b>Nom du groupe dans vos favoris :</b>",
    "Searching streams...": "Recherche des flux en cours...",
    "Enter a keyword or click Search to explore the directory.": "Saisissez un mot-clé ou cliquez sur Rechercher pour explorer l'annuaire.",
    "🔧 Repair selected stream (Radio-Browser)...": "🔧 Réparer le flux sélectionné (Radio-Browser)...",
    "➕ Import into favorites": "➕ Importer dans mes favoris",
    "Close": "Fermer",
}

TRANSLATIONS_ES = {
    "➕ Add a station (TiMonde)": "➕ Añadir una estación (TiMonde)",
    "<b>Enter new station details:</b>": "<b>Introduzca los datos de la nueva radio:</b>",
    "➕ Add to my stations": "➕ Añadir a mis radios",
    "⭐ Save station to favorites (TiMonde)": "⭐ Guardar radio en favoritos (TiMonde)",
    "<b>Keep this randomly discovered station in your favorites:</b>": "<b>Conservar esta radio descubierta al azar en favoritos:</b>",
    "⭐ Keep in favorites": "⭐ Conservar en favoritos",
    "✏️ Edit station (TiMonde)": "✏️ Editar radio (TiMonde)",
    "<b>Edit station settings:</b>": "<b>Modificar los ajustes de la radio:</b>",
    "💾 Save": "💾 Guardar",
    "Station name:": "Nombre de la radio:",
    "Audio stream URL:": "URL del flujo de audio:",
    "Group / Folder:": "Grupo / Carpeta:",
    "Search or create group...": "Buscar o crear grupo...",
    "(Root / No group)": "(Raíz / Sin grupo)",
    "Country & Timezone:": "País y zona horaria:",
    "Search country (e.g. France, Senegal, FR, SN)...": "Buscar país (ej. España, México, ES, MX)...",
    "Clear country": "Borrar país",
    "Timezone:": "Zona horaria:",
    "🗑️ Delete this station": "🗑️ Eliminar esta radio",
    "Cancel": "Cancelar",
    "Delete « {} » from favorites?": "¿Eliminar « {} » de favoritos?",
    "This action will permanently remove this station from your collection.": "Esta acción eliminará definitivamente esta estación de su colección.",
    "🗑️ Delete": "🗑️ Eliminar",
    "↕️ Manage groups, stations and separators (TiMonde)": "↕️ Gestión de grupos, radios y separadores (TiMonde)",
    "⬅️ Back to groups": "⬅️ Volver a los grupos",
    "➕ Add station": "➕ Añadir estación",
    "📂 Open": "📂 Abrir",
    "📁 New group": "📁 Nuevo grupo",
    "➡️ Move to...": "➡️ Mover a...",
    "🔝 Top": "🔝 Primero",
    "⬆️ Move up": "⬆️ Subir",
    "⬇️ Move down": "⬇️ Bajar",
    "➕ Separator": "➕ Separador",
    "🔤 Sort A-Z": "🔤 Ordenar A-Z",
    "✏️ Edit": "✏️ Editar",
    "💾 Save and reload": "💾 Guardar y recargar",
    "📻 Discover & Import stations (TiMonde)": "📻 Descubrir e importar radios (TiMonde)",
    "⭐ Verified DAB+ Bouquets": "⭐ Ramos verificados (DAB+)",
    "🔎 Radio-Browser Search": "🔎 Búsqueda Radio-Browser",
    "📂 Sample Files": "📂 Archivos de ejemplo",
    "📥 Import my files": "📥 Importar mis archivos",
    "<b>🌍 Country:</b>": "<b>🌍 País:</b>",
    "<b>Language:</b>": "<b>Idioma:</b>",
    "Name / Keyword:": "Nombre / Palabra clave:",
    "Genre:": "Género:",
    "Close": "Cerrar",
}

TRANSLATIONS_DE = {
    "➕ Add a station (TiMonde)": "➕ Sender hinzufügen (TiMonde)",
    "<b>Enter new station details:</b>": "<b>Geben Sie die Daten des neuen Senders ein:</b>",
    "➕ Add to my stations": "➕ Zu meinen Sendern hinzufügen",
    "⭐ Save station to favorites (TiMonde)": "⭐ Sender in Favoriten speichern (TiMonde)",
    "<b>Keep this randomly discovered station in your favorites:</b>": "<b>Diesen zufällig entdeckten Sender in Favoriten behalten:</b>",
    "⭐ Keep in favorites": "⭐ In Favoriten behalten",
    "✏️ Edit station (TiMonde)": "✏️ Sender bearbeiten (TiMonde)",
    "<b>Edit station settings:</b>": "<b>Sendereinstellungen bearbeiten:</b>",
    "💾 Save": "💾 Speichern",
    "Station name:": "Sendername:",
    "Audio stream URL:": "Audiostream-URL:",
    "Group / Folder:": "Gruppe / Ordner:",
    "Search or create group...": "Gruppe suchen oder erstellen...",
    "(Root / No group)": "(Stamm / Keine Gruppe)",
    "Country & Timezone:": "Land & Zeitzone:",
    "Search country (e.g. France, Senegal, FR, SN)...": "Land suchen (z. B. Deutschland, Österreich, DE, AT)...",
    "Clear country": "Land löschen",
    "Timezone:": "Zeitzone:",
    "🗑️ Delete this station": "🗑️ Diesen Sender löschen",
    "Cancel": "Abbrechen",
    "Delete « {} » from favorites?": "« {} » aus Favoriten löschen?",
    "This action will permanently remove this station from your collection.": "Diese Aktion entfernt diesen Sender dauerhaft aus Ihrer Sammlung.",
    "🗑️ Delete": "🗑️ Löschen",
    "↕️ Manage groups, stations and separators (TiMonde)": "↕️ Verwaltung von Gruppen, Sendern und Trennlinien (TiMonde)",
    "⬅️ Back to groups": "⬅️ Zurück zu den Gruppen",
    "➕ Add station": "➕ Sender hinzufügen",
    "📂 Open": "📂 Öffnen",
    "📁 New group": "📁 Neue Gruppe",
    "➡️ Move to...": "➡️ Verschieben nach...",
    "🔝 Top": "🔝 Ganz oben",
    "⬆️ Move up": "⬆️ Nach oben",
    "⬇️ Move down": "⬇️ Nach unten",
    "➕ Separator": "➕ Trennlinie",
    "🔤 Sort A-Z": "🔤 Sortieren A-Z",
    "✏️ Edit": "✏️ Bearbeiten",
    "💾 Save and reload": "💾 Speichern und neu laden",
    "📻 Discover & Import stations (TiMonde)": "📻 Sender entdecken & importieren (TiMonde)",
    "⭐ Verified DAB+ Bouquets": "⭐ Verifizierte DAB+-Bouquets",
    "🔎 Radio-Browser Search": "🔎 Radio-Browser-Suche",
    "📂 Sample Files": "📂 Beispieldateien",
    "📥 Import my files": "📥 Meine Dateien importieren",
    "<b>🌍 Country:</b>": "<b>🌍 Land:</b>",
    "<b>Language:</b>": "<b>Sprache:</b>",
    "Name / Keyword:": "Name / Suchbegriff:",
    "Genre:": "Genre:",
    "Close": "Schließen",
}

TRANSLATIONS_PT = {
    "➕ Add a station (TiMonde)": "➕ Adicionar uma estação (TiMonde)",
    "<b>Enter new station details:</b>": "<b>Introduza os dados da nova rádio:</b>",
    "➕ Add to my stations": "➕ Adicionar às minhas estações",
    "⭐ Save station to favorites (TiMonde)": "⭐ Guardar rádio nos favoritos (TiMonde)",
    "<b>Keep this randomly discovered station in your favorites:</b>": "<b>Guardar esta estação descoberta ao acaso nos favoritos:</b>",
    "⭐ Keep in favorites": "⭐ Manter nos favoritos",
    "✏️ Edit station (TiMonde)": "✏️ Editar rádio (TiMonde)",
    "<b>Edit station settings:</b>": "<b>Modificar as definições da estação:</b>",
    "💾 Save": "💾 Guardar",
    "Station name:": "Nome da rádio:",
    "Audio stream URL:": "URL do fluxo de áudio:",
    "Group / Folder:": "Grupo / Pasta:",
    "Search or create group...": "Procurar ou criar grupo...",
    "(Root / No group)": "(Raiz / Sem grupo)",
    "Country & Timezone:": "País e fuso horário:",
    "Search country (e.g. France, Senegal, FR, SN)...": "Procurar país (ex. Portugal, Brasil, PT, BR)...",
    "Clear country": "Limpar país",
    "Timezone:": "Fuso horário:",
    "🗑️ Delete this station": "🗑️ Eliminar esta rádio",
    "Cancel": "Cancelar",
    "Delete « {} » from favorites?": "Eliminar « {} » dos favoritos?",
    "This action will permanently remove this station from your collection.": "Esta ação removerá permanentemente esta estação da sua coleção.",
    "🗑️ Delete": "🗑️ Eliminar",
    "↕️ Manage groups, stations and separators (TiMonde)": "↕️ Gestão de grupos, estações e separadores (TiMonde)",
    "⬅️ Back to groups": "⬅️ Voltar aos grupos",
    "➕ Add station": "➕ Adicionar estação",
    "📂 Open": "📂 Abrir",
    "📁 New group": "📁 Novo grupo",
    "➡️ Move to...": "➡️ Mover para...",
    "🔝 Top": "🔝 Topo",
    "⬆️ Move up": "⬆️ Subir",
    "⬇️ Move down": "⬇️ Descer",
    "➕ Separator": "➕ Separador",
    "🔤 Sort A-Z": "🔤 Ordenar A-Z",
    "✏️ Edit": "✏️ Editar",
    "💾 Save and reload": "💾 Guardar e recarregar",
    "📻 Discover & Import stations (TiMonde)": "📻 Descobrir e importar estações (TiMonde)",
    "⭐ Verified DAB+ Bouquets": "⭐ Pacotes verificados (DAB+)",
    "🔎 Radio-Browser Search": "🔎 Pesquisa Radio-Browser",
    "📂 Sample Files": "📂 Ficheiros de exemplo",
    "📥 Import my files": "📥 Importar os meus ficheiros",
    "<b>🌍 Country:</b>": "<b>🌍 País:</b>",
    "<b>Language:</b>": "<b>Idioma:</b>",
    "Name / Keyword:": "Nome / Palavra-chave:",
    "Genre:": "Género:",
    "Close": "Fechar",
}

def get_text(msg):
    lang = get_current_language()
    if lang == "fr":
        return TRANSLATIONS_FR.get(msg, msg)
    elif lang == "es":
        return TRANSLATIONS_ES.get(msg, msg)
    elif lang == "de":
        return TRANSLATIONS_DE.get(msg, msg)
    elif lang == "pt":
        return TRANSLATIONS_PT.get(msg, msg)
    return msg

# Raccourci _ conventionnel
_ = get_text
