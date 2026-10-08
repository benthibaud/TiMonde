#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Éditeur universel de radio pour TiMonde (GTK3) :
- Modifier une radio existante (--mode edit)
- Ajouter une nouvelle radio (--mode add)
- Conserver une radio éphémère (--mode save-ephemeral)

Dispose d'un sélecteur de pays avec recherche filtrante en direct (247 pays)
et d'une synchronisation automatique des fuseaux horaires (mono-fuseau déduit/grisé,
multi-fuseaux ouvert, France par défaut sur Paris avec accès direct aux Outre-mer).
"""

import sys
# Sauvegarde impérative des arguments CLI avant que GTK ne supprime --name (mot-clé réservé GTK/X11)
SAVED_ARGV = list(sys.argv)
import os
import json
import argparse
import collections
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib


def clean_stream_url(url: str) -> str:
    """Nettoie préventivement une URL de flux audio."""
    if not url:
        return ""
    u = url.strip()
    if u.startswith("http ://"):
        u = "http://" + u[8:]
    elif u.startswith("https ://"):
        u = "https://" + u[9:]
    elif u.startswith("//"):
        u = "https://" + u[2:]

    while True:
        if u.startswith("httpshttps://"):
            u = "https://" + u[13:]
            continue
        if u.startswith("httphttp://"):
            u = "http://" + u[11:]
            continue
        if u.startswith("http://https://"):
            u = "https://" + u[15:]
            continue
        if u.startswith("https://http://"):
            u = "http://" + u[15:]
            continue
        if u.startswith("https://https://"):
            u = "https://" + u[16:]
            continue
        if u.startswith("http://http://"):
            u = "http://" + u[14:]
            continue
        break
    return u


# Registre exhaustif des pays avec drapeaux et noms en français
COUNTRIES_DB = [
    ("FR", "France", "🇫🇷"),
    ("GP", "Guadeloupe", "🇬🇵"),
    ("MQ", "Martinique", "🇲🇶"),
    ("GF", "Guyane", "🇬🇫"),
    ("RE", "La Réunion", "🇷🇪"),
    ("YT", "Mayotte", "🇾🇹"),
    ("NC", "Nouvelle-Calédonie", "🇳🇨"),
    ("PF", "Polynésie française", "🇵🇫"),
    ("PM", "Saint-Pierre-et-Miquelon", "🇵🇲"),
    ("BL", "Saint-Barthélemy", "🇧🇱"),
    ("MF", "Saint-Martin", "🇲🇫"),
    ("WF", "Wallis-et-Futuna", "🇼🇫"),
    ("BE", "Belgique", "🇧🇪"),
    ("CH", "Suisse", "🇨🇭"),
    ("CA", "Canada", "🇨🇦"),
    ("US", "États-Unis", "🇺🇸"),
    ("GB", "Royaume-Uni", "🇬🇧"),
    ("DE", "Allemagne", "🇩🇪"),
    ("IT", "Italie", "🇮🇹"),
    ("ES", "Espagne", "🇪🇸"),
    ("PT", "Portugal", "🇵🇹"),
    ("NL", "Pays-Bas", "🇳🇱"),
    ("SN", "Sénégal", "🇸🇳"),
    ("CI", "Côte d'Ivoire", "🇨🇮"),
    ("MA", "Maroc", "🇲🇦"),
    ("DZ", "Algérie", "🇩🇿"),
    ("TN", "Tunisie", "🇹🇳"),
    ("ML", "Mali", "🇲🇱"),
    ("GN", "Guinée", "🇬🇳"),
    ("CM", "Cameroun", "🇨🇲"),
    ("MG", "Madagascar", "🇲🇬"),
    ("HT", "Haïti", "🇭🇹"),
    ("LU", "Luxembourg", "🇱🇺"),
    ("MC", "Monaco", "🇲🇨"),
    ("AD", "Andorre", "🇦🇩"),
    ("IE", "Irlande", "🇮🇪"),
    ("AT", "Autriche", "🇦🇹"),
    ("SE", "Suède", "🇸🇪"),
    ("NO", "Norvège", "🇳🇴"),
    ("DK", "Danemark", "🇩🇰"),
    ("FI", "Finlande", "🇫🇮"),
    ("IS", "Islande", "🇮🇸"),
    ("GR", "Grèce", "🇬🇷"),
    ("PL", "Pologne", "🇵🇱"),
    ("CZ", "Tchéquie", "🇨🇿"),
    ("SK", "Slovaquie", "🇸🇰"),
    ("HU", "Hongrie", "🇭🇺"),
    ("RO", "Roumanie", "🇷🇴"),
    ("BG", "Bulgarie", "🇧🇬"),
    ("HR", "Croatie", "🇭🇷"),
    ("RS", "Serbie", "🇷🇸"),
    ("BA", "Bosnie-Herzégovine", "🇧🇦"),
    ("SI", "Slovénie", "🇸🇮"),
    ("JP", "Japon", "🇯🇵"),
    ("CN", "Chine", "🇨🇳"),
    ("KR", "Corée du Sud", "🇰🇷"),
    ("IN", "Inde", "🇮🇳"),
    ("BR", "Brésil", "🇧🇷"),
    ("AR", "Argentine", "🇦🇷"),
    ("MX", "Mexique", "🇲🇽"),
    ("CO", "Colombie", "🇨🇴"),
    ("CL", "Chili", "🇨🇱"),
    ("PE", "Pérou", "🇵🇪"),
    ("AU", "Australie", "🇦🇺"),
    ("NZ", "Nouvelle-Zélande", "🇳🇿"),
    ("ZA", "Afrique du Sud", "🇿🇦"),
    ("RU", "Russie", "🇷🇺"),
    ("UA", "Ukraine", "🇺🇦"),
    ("TR", "Turquie", "🇹🇷"),
    ("IL", "Israël", "🇮🇱"),
    ("LB", "Liban", "🇱🇧"),
]

# Enrichissement avec tous les pays du monde depuis zone.tab
def build_countries_registry():
    d = {code: (name, flag) for code, name, flag in COUNTRIES_DB}
    zone_tab = "/usr/share/zoneinfo/zone.tab"
    if os.path.exists(zone_tab):
        try:
            with open(zone_tab, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    cc = parts[0].strip().upper()
                    if cc not in d:
                        d[cc] = (cc, "🌐")
        except Exception:
            pass
    return d

COUNTRIES_REGISTRY = build_countries_registry()

# Fuseaux horaires complets pour la France (Métropole + Outre-mer)
FRANCE_TIMEZONES = [
    ("Europe/Paris", "Europe/Paris (France métropolitaine)"),
    ("America/Guadeloupe", "America/Guadeloupe (Guadeloupe - Antilles)"),
    ("America/Martinique", "America/Martinique (Martinique - Antilles)"),
    ("America/Cayenne", "America/Cayenne (Guyane française)"),
    ("Indian/Reunion", "Indian/Reunion (La Réunion - Océan Indien)"),
    ("Indian/Mayotte", "Indian/Mayotte (Mayotte - Océan Indien)"),
    ("America/Miquelon", "America/Miquelon (Saint-Pierre-et-Miquelon)"),
    ("America/St_Barthelemy", "America/St_Barthelemy (Saint-Barthélemy)"),
    ("America/Marigot", "America/Marigot (Saint-Martin)"),
    ("Pacific/Noumea", "Pacific/Noumea (Nouvelle-Calédonie)"),
    ("Pacific/Tahiti", "Pacific/Tahiti (Polynésie française - Tahiti)"),
    ("Pacific/Marquesas", "Pacific/Marquesas (Polynésie - Îles Marquises)"),
    ("Pacific/Gambier", "Pacific/Gambier (Polynésie - Îles Gambier)"),
    ("Pacific/Wallis", "Pacific/Wallis (Wallis-et-Futuna)"),
]

# Libellés clairs pour les pays multi-fuseaux majeurs
CUSTOM_MULTI_TZ = {
    "CA": [
        ("America/Toronto", "America/Toronto (Est - Québec, Ontario)"),
        ("America/Moncton", "America/Moncton (Atlantique - Nouveau-Brunswick, Acadie)"),
        ("America/Halifax", "America/Halifax (Atlantique - Nouvelle-Écosse)"),
        ("America/St_Johns", "America/St_Johns (Terre-Neuve)"),
        ("America/Winnipeg", "America/Winnipeg (Centre - Manitoba)"),
        ("America/Regina", "America/Regina (Centre - Saskatchewan)"),
        ("America/Edmonton", "America/Edmonton (Rocheuses - Alberta)"),
        ("America/Vancouver", "America/Vancouver (Pacifique - Colombie-Britannique)"),
        ("America/Whitehorse", "America/Whitehorse (Yukon)"),
    ],
    "US": [
        ("America/New_York", "America/New_York (Est - New York, Floride, DC)"),
        ("America/Chicago", "America/Chicago (Centre - Chicago, Texas, Louisiane)"),
        ("America/Denver", "America/Denver (Montagnes - Denver, Colorado)"),
        ("America/Phoenix", "America/Phoenix (Montagnes - Arizona sans heure d'été)"),
        ("America/Los_Angeles", "America/Los_Angeles (Pacifique - Californie, Washington)"),
        ("America/Anchorage", "America/Anchorage (Alaska)"),
        ("Pacific/Honolulu", "Pacific/Honolulu (Hawaï)"),
    ],
    "BR": [
        ("America/Sao_Paulo", "America/Sao_Paulo (Brasília, São Paulo, Rio)"),
        ("America/Manaus", "America/Manaus (Amazonie)"),
        ("America/Cuiaba", "America/Cuiaba (Centre-Ouest)"),
        ("America/Rio_Branco", "America/Rio_Branco (Acre)"),
        ("America/Noronha", "America/Noronha (Fernando de Noronha)"),
    ],
    "AU": [
        ("Australia/Sydney", "Australia/Sydney (Est - Sydney, Melbourne)"),
        ("Australia/Brisbane", "Australia/Brisbane (Est - Queensland sans heure d'été)"),
        ("Australia/Adelaide", "Australia/Adelaide (Centre - Adélaïde)"),
        ("Australia/Darwin", "Australia/Darwin (Centre - Territoire du Nord)"),
        ("Australia/Perth", "Australia/Perth (Ouest - Perth)"),
    ],
    "RU": [
        ("Europe/Moscow", "Europe/Moscow (Moscou, Saint-Pétersbourg - UTC+3)"),
        ("Europe/Kaliningrad", "Europe/Kaliningrad (Kaliningrad - UTC+2)"),
        ("Europe/Samara", "Europe/Samara (Samara - UTC+4)"),
        ("Asia/Yekaterinburg", "Asia/Yekaterinburg (Oural - UTC+5)"),
        ("Asia/Omsk", "Asia/Omsk (Omsk - UTC+6)"),
        ("Asia/Novosibirsk", "Asia/Novosibirsk (Novossibirsk - UTC+7)"),
        ("Asia/Krasnoyarsk", "Asia/Krasnoyarsk (Krasnoïarsk - UTC+7)"),
        ("Asia/Irkutsk", "Asia/Irkutsk (Irkoutsk - UTC+8)"),
        ("Asia/Yakutsk", "Asia/Yakutsk (Iakoutsk - UTC+9)"),
        ("Asia/Vladivostok", "Asia/Vladivostok (Vladivostok - UTC+10)"),
        ("Asia/Magadan", "Asia/Magadan (Magadan - UTC+11)"),
        ("Asia/Kamchatka", "Asia/Kamchatka (Kamtchatka - UTC+12)"),
    ],
    "ES": [
        ("Europe/Madrid", "Europe/Madrid (Péninsule ibérique et Baléares)"),
        ("Atlantic/Canary", "Atlantic/Canary (Îles Canaries)"),
        ("Africa/Ceuta", "Africa/Ceuta (Ceuta et Melilla)"),
    ],
    "PT": [
        ("Europe/Lisbon", "Europe/Lisbon (Portugal continental et Madère)"),
        ("Atlantic/Azores", "Atlantic/Azores (Açores)"),
    ],
}


def load_world_timezones() -> dict:
    catalogue = collections.defaultdict(list)
    zone_tab_path = "/usr/share/zoneinfo/zone.tab"
    if os.path.exists(zone_tab_path):
        try:
            with open(zone_tab_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        cc = parts[0].strip().upper()
                        tz = parts[2].strip()
                        comment = parts[3].strip() if len(parts) > 3 else ""
                        desc = f"{tz} ({comment})" if comment else tz
                        catalogue[cc].append((tz, desc))
        except Exception:
            pass

    catalogue["FR"] = list(FRANCE_TIMEZONES)
    for cc, tz_list in CUSTOM_MULTI_TZ.items():
        catalogue[cc] = list(tz_list)

    overseas_direct = {
        "GP": [("America/Guadeloupe", "America/Guadeloupe (Guadeloupe)")],
        "MQ": [("America/Martinique", "America/Martinique (Martinique)")],
        "GF": [("America/Cayenne", "America/Cayenne (Guyane)")],
        "RE": [("Indian/Reunion", "Indian/Reunion (La Réunion)")],
        "YT": [("Indian/Mayotte", "Indian/Mayotte (Mayotte)")],
        "NC": [("Pacific/Noumea", "Pacific/Noumea (Nouvelle-Calédonie)")],
        "PF": [("Pacific/Tahiti", "Pacific/Tahiti (Polynésie française)")],
        "PM": [("America/Miquelon", "America/Miquelon (Saint-Pierre-et-Miquelon)")],
        "BL": [("America/St_Barthelemy", "America/St_Barthelemy (Saint-Barthélemy)")],
        "MF": [("America/Marigot", "America/Marigot (Saint-Martin)")],
        "WF": [("Pacific/Wallis", "Pacific/Wallis (Wallis-et-Futuna)")],
    }
    for cc, tzs in overseas_direct.items():
        catalogue[cc] = tzs

    return catalogue


WORLD_TIMEZONES = load_world_timezones()


class EditStationWindow(Gtk.Window):
    def __init__(self, mode="edit", current_name="", current_url="", current_country="", current_timezone="", current_group="", available_groups=None):
        self.mode = mode
        if self.mode == "add":
            title = "➕ Ajouter une station (TiMonde)"
            header_text = "<b>Entrez les informations de la nouvelle radio :</b>"
            save_label = "➕ Ajouter à mes radios"
        elif self.mode == "save-ephemeral":
            title = "⭐ Enregistrer la radio dans mes favoris (TiMonde)"
            header_text = "<b>Conserver cette radio découverte au hasard dans vos favoris :</b>"
            save_label = "⭐ Conserver dans mes favoris"
        else:
            title = "✏️ Modifier la radio (TiMonde)"
            header_text = "<b>Modifier les paramètres de la station :</b>"
            save_label = "💾 Enregistrer"

        super().__init__(title=title)
        self.set_default_size(580, 360)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(14)
        self.set_icon_name("audio-x-generic")

        self.saved = False
        self.result_data = None
        self.current_group_orig = current_group
        self.initial_timezone = (current_timezone or "").strip()
        self.selected_country_code = (current_country or "").strip().upper()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(vbox)

        # En-tête informatif
        header = Gtk.Label()
        header.set_markup(header_text)
        header.set_halign(Gtk.Align.START)
        vbox.pack_start(header, False, False, 0)

        # Grille pour les champs
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(10)
        vbox.pack_start(grid, True, True, 0)

        # 1. Nom de la station
        lbl_name = Gtk.Label(label="Nom de la radio :")
        lbl_name.set_halign(Gtk.Align.END)
        grid.attach(lbl_name, 0, 0, 1, 1)

        self.entry_name = Gtk.Entry()
        self.entry_name.set_text(current_name)
        self.entry_name.set_hexpand(True)
        self.entry_name.connect("activate", self.on_save_clicked)
        grid.attach(self.entry_name, 1, 0, 1, 1)

        # 2. URL du flux audio
        lbl_url = Gtk.Label(label="URL du flux :")
        lbl_url.set_halign(Gtk.Align.END)
        grid.attach(lbl_url, 0, 1, 1, 1)

        self.entry_url = Gtk.Entry()
        self.entry_url.set_text(current_url)
        self.entry_url.set_hexpand(True)
        self.entry_url.connect("activate", self.on_save_clicked)
        grid.attach(self.entry_url, 1, 1, 1, 1)

        # 3. Groupe d'appartenance
        lbl_group = Gtk.Label(label="Groupe :")
        lbl_group.set_halign(Gtk.Align.END)
        grid.attach(lbl_group, 0, 2, 1, 1)

        self.combo_group = Gtk.ComboBoxText()
        if available_groups:
            for g in available_groups:
                self.combo_group.append_text(g)
        if current_group and (not available_groups or current_group not in available_groups):
            self.combo_group.append_text(current_group)

        if current_group:
            model = self.combo_group.get_model()
            for idx, row in enumerate(model):
                if row[0] == current_group:
                    self.combo_group.set_active(idx)
                    break
        elif available_groups:
            self.combo_group.set_active(0)

        self.combo_group.set_hexpand(True)
        grid.attach(self.combo_group, 1, 2, 1, 1)

        # 4. Sélecteur de Pays avec recherche affinante en direct
        lbl_country = Gtk.Label(label="Pays :")
        lbl_country.set_halign(Gtk.Align.END)
        grid.attach(lbl_country, 0, 3, 1, 1)

        country_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        # Champ de saisie / filtre de recherche avec auto-complétion
        self.entry_country_search = Gtk.Entry()
        self.entry_country_search.set_placeholder_text("Tapez pour chercher (ex: France, Canada, Guadeloupe...)")
        self.entry_country_search.set_hexpand(True)

        # Modèle de complétion : [Recherche, Libellé affiché, Code ISO]
        self.country_store = Gtk.ListStore(str, str, str)
        # 1. Option automatique / non spécifié
        self.country_store.append(["", "🌐 (Déduction automatique selon le groupe)", ""])
        
        # 2. Liste des pays
        for code, (cname, cflag) in sorted(COUNTRIES_REGISTRY.items(), key=lambda x: (x[1][0] != "France", x[1][0])):
            search_key = f"{cname} {code}".lower()
            display_label = f"{cflag} {cname} ({code})"
            self.country_store.append([search_key, display_label, code])

        completion = Gtk.EntryCompletion()
        completion.set_model(self.country_store)
        completion.set_text_column(1)
        completion.set_match_func(self.match_country_completion)
        completion.connect("match-selected", self.on_country_match_selected)
        self.entry_country_search.set_completion(completion)
        self.entry_country_search.connect("changed", self.on_country_search_changed)
        self.entry_country_search.connect("activate", self.on_save_clicked)
        country_box.pack_start(self.entry_country_search, True, True, 0)

        # Bouton pour effacer le pays ou réinitialiser
        btn_clear_country = Gtk.Button(label="✕")
        btn_clear_country.set_tooltip_text("Effacer / Mode automatique")
        btn_clear_country.connect("clicked", lambda b: self.entry_country_search.set_text(""))
        country_box.pack_start(btn_clear_country, False, False, 0)

        grid.attach(country_box, 1, 3, 1, 1)

        # 5. Fuseau horaire
        lbl_tz = Gtk.Label(label="Fuseau horaire :")
        lbl_tz.set_halign(Gtk.Align.END)
        grid.attach(lbl_tz, 0, 4, 1, 1)

        tz_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.combo_tz = Gtk.ComboBoxText()
        self.combo_tz.set_hexpand(True)
        tz_box.pack_start(self.combo_tz, True, True, 0)

        self.lbl_tz_hint = Gtk.Label()
        self.lbl_tz_hint.set_halign(Gtk.Align.START)
        tz_box.pack_start(self.lbl_tz_hint, False, False, 0)

        grid.attach(tz_box, 1, 4, 1, 1)

        # Initialiser le champ de recherche pays avec le pays de départ
        if self.selected_country_code and self.selected_country_code in COUNTRIES_REGISTRY:
            cname, cflag = COUNTRIES_REGISTRY[self.selected_country_code]
            self.entry_country_search.set_text(f"{cflag} {cname} ({self.selected_country_code})")
        elif self.selected_country_code:
            self.entry_country_search.set_text(self.selected_country_code)

        # Initialiser la liste des fuseaux horaires
        self.populate_timezones_for_country(self.selected_country_code, preserve_tz=self.initial_timezone)

        # Boutons d'action
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.pack_start(btn_box, False, False, 0)

        if self.mode == "edit":
            btn_delete = Gtk.Button(label="🗑️ Supprimer cette radio")
            btn_delete.get_style_context().add_class("destructive-action")
            btn_delete.connect("clicked", self.on_delete_clicked)
            btn_box.pack_start(btn_delete, False, False, 0)

        btn_cancel = Gtk.Button(label="Annuler")
        btn_cancel.connect("clicked", self.on_cancel_clicked)
        btn_box.pack_start(btn_cancel, False, False, 0)

        spacer = Gtk.Box()
        btn_box.pack_start(spacer, True, True, 0)

        self.btn_save = Gtk.Button(label=save_label)
        self.btn_save.get_style_context().add_class("suggested-action")
        self.btn_save.connect("clicked", self.on_save_clicked)
        btn_box.pack_start(self.btn_save, False, False, 0)

        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_key_press)

        # Placer le curseur à la fin du nom sans sélection destructrice
        GLib.idle_add(self.setup_focus)

    def setup_focus(self):
        text = self.entry_name.get_text()
        self.entry_name.set_position(len(text))
        return False

    def match_country_completion(self, completion, key, tree_iter):
        model = completion.get_model()
        search_key = model[tree_iter][0]
        display_label = model[tree_iter][1].lower()
        query = key.strip().lower()
        if not query:
            return True
        return query in search_key or query in display_label

    def on_country_match_selected(self, completion, model, tree_iter):
        code = model[tree_iter][2]
        self.selected_country_code = code
        self.populate_timezones_for_country(code)
        return False

    def on_country_search_changed(self, entry):
        raw = entry.get_text().strip()
        # Détection si l'utilisateur a tapé directement un code ISO ou sélectionné un pays
        found_code = None
        if "(" in raw and raw.endswith(")"):
            possible = raw.split("(") [-1].rstrip(")").strip().upper()
            if possible in COUNTRIES_REGISTRY:
                found_code = possible
        elif raw.upper() in COUNTRIES_REGISTRY:
            found_code = raw.upper()
        else:
            # Recherche par correspondance de préfixe
            r_lower = raw.lower()
            for code, (cname, _) in COUNTRIES_REGISTRY.items():
                if cname.lower() == r_lower:
                    found_code = code
                    break

        if found_code != self.selected_country_code:
            self.selected_country_code = found_code or ""
            self.populate_timezones_for_country(self.selected_country_code)

    def populate_timezones_for_country(self, country_code, preserve_tz=None):
        """
        Génère la liste déroulante des fuseaux horaires selon le pays choisi :
        - Mono-fuseau : affiché et grisé (sensitive=False)
        - Multi-fuseaux : ouvert (sensitive=True)
        - France (FR) : Europe/Paris par défaut avec sélection directe des territoires d'Outre-mer
        """
        code_upper = (country_code or "").strip().upper()
        tz_list = WORLD_TIMEZONES.get(code_upper, [])

        self.combo_tz.remove_all()

        if not tz_list:
            if code_upper:
                self.combo_tz.append_text("(Fuseau non défini)")
                self.combo_tz.set_active(0)
                self.combo_tz.set_sensitive(False)
                self.lbl_tz_hint.set_markup("<small><i>(Inconnu)</i></small>")
            else:
                self.combo_tz.append_text("(Déduction automatique)")
                self.combo_tz.set_active(0)
                self.combo_tz.set_sensitive(False)
                self.lbl_tz_hint.set_markup("<small><i>(Automatique selon la station)</i></small>")
            return

        for tz_id, label in tz_list:
            self.combo_tz.append_text(label)

        # Pré-sélection
        active_index = 0
        target_tz = preserve_tz or self.initial_timezone or ""
        if target_tz:
            for idx, (tz_id, _) in enumerate(tz_list):
                if tz_id.lower() == target_tz.lower():
                    active_index = idx
                    break

        self.combo_tz.set_active(active_index)

        # Application de la règle mono-fuseau vs multi-fuseaux
        if len(tz_list) == 1:
            self.combo_tz.set_sensitive(False)
            self.lbl_tz_hint.set_markup("<small><i>(Fuseau unique déduit)</i></small>")
        else:
            self.combo_tz.set_sensitive(True)
            if code_upper == "FR":
                self.lbl_tz_hint.set_markup("<small><i>(Métropole ou Outre-mer)</i></small>")
            else:
                self.lbl_tz_hint.set_markup(f"<small><i>({len(tz_list)} fuseaux disponibles)</i></small>")

    def get_selected_timezone_id(self):
        code_upper = (self.selected_country_code or "").strip().upper()
        tz_list = WORLD_TIMEZONES.get(code_upper, [])
        idx = self.combo_tz.get_active()
        if 0 <= idx < len(tz_list):
            return tz_list[idx][0]
        return None

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def on_delete_clicked(self, widget):
        current_display_name = self.entry_name.get_text().strip() or "cette radio"
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            message_format=f"Supprimer « {current_display_name} » des favoris ?"
        )
        dialog.format_secondary_text("Cette action retirera définitivement cette station de votre collection.")
        dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
        btn_del_confirm = dialog.add_button("🗑️ Supprimer", Gtk.ResponseType.OK)
        btn_del_confirm.get_style_context().add_class("destructive-action")

        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.result_data = {
                "action": "delete",
                "name": current_display_name,
                "url": self.entry_url.get_text().strip(),
            }
            self.saved = True
            print(json.dumps(self.result_data, ensure_ascii=False))
            self.destroy()

    def on_cancel_clicked(self, widget):
        self.destroy()

    def on_save_clicked(self, widget):
        name = self.entry_name.get_text().strip()
        url = clean_stream_url(self.entry_url.get_text().strip())
        country = self.selected_country_code or None
        timezone = self.get_selected_timezone_id()
        selected_group = self.combo_group.get_active_text() or self.current_group_orig or ""

        if not name or not url:
            return

        self.result_data = {
            "name": name,
            "url": url,
            "country": country,
            "timezone": timezone,
            "group": selected_group if selected_group else None,
        }
        self.saved = True
        print(json.dumps(self.result_data, ensure_ascii=False))
        self.destroy()


def main():

    try:
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-entry-select-on-focus", False)
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Éditeur de station TiMonde")
    parser.add_argument("--mode", default="edit", choices=["edit", "add", "save-ephemeral"], help="Mode d'ouverture")
    parser.add_argument("--station-name", "--name", dest="name", default="", help="Nom actuel de la station")
    parser.add_argument("--url", default="", help="URL actuelle du flux")
    parser.add_argument("--country", default="", help="Code pays ISO de la station")
    parser.add_argument("--timezone", default="", help="Fuseau horaire IANA actuel de la station")
    parser.add_argument("--group", default="", help="Groupe d'appartenance actuel")
    parser.add_argument("--groups-json", default="[]", help="Liste JSON de tous les groupes disponibles")
    args = parser.parse_args(SAVED_ARGV[1:])

    available_groups = []
    try:
        available_groups = json.loads(args.groups_json)
    except Exception:
        pass

    win = EditStationWindow(
        mode=args.mode,
        current_name=args.name,
        current_url=args.url,
        current_country=args.country,
        current_timezone=args.timezone,
        current_group=args.group,
        available_groups=available_groups,
    )
    win.show_all()
    Gtk.main()

    if win.saved and win.result_data:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
