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
import os

# Neutralisation inconditionnelle d'IBus pour éviter tout gel des frappes clavier sous GTK3
# (les sessions de bureau avec socket IBus orpheline ou rompue absorbent et perdent les touches)
os.environ.pop("GTK_IM_MODULE", None)
os.environ.pop("XMODIFIERS", None)
os.environ.pop("QT_IM_MODULE", None)

# Module d internationalisation TiMonde
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s

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
    ("FR", "France", ""),
    ("GP", "Guadeloupe", ""),
    ("MQ", "Martinique", ""),
    ("GF", "Guyane", ""),
    ("RE", "La Réunion", ""),
    ("YT", "Mayotte", ""),
    ("NC", "Nouvelle-Calédonie", ""),
    ("PF", "Polynésie française", ""),
    ("PM", "Saint-Pierre-et-Miquelon", ""),
    ("BL", "Saint-Barthélemy", ""),
    ("MF", "Saint-Martin", ""),
    ("WF", "Wallis-et-Futuna", ""),
    ("BE", "Belgique", ""),
    ("CH", "Suisse", ""),
    ("CA", "Canada", ""),
    ("US", "États-Unis", ""),
    ("GB", "Royaume-Uni", ""),
    ("DE", "Allemagne", ""),
    ("IT", "Italie", ""),
    ("ES", "Espagne", ""),
    ("PT", "Portugal", ""),
    ("NL", "Pays-Bas", ""),
    ("SN", "Sénégal", ""),
    ("CI", "Côte d'Ivoire", ""),
    ("MA", "Maroc", ""),
    ("DZ", "Algérie", ""),
    ("TN", "Tunisie", ""),
    ("ML", "Mali", ""),
    ("GN", "Guinée", ""),
    ("CM", "Cameroun", ""),
    ("MG", "Madagascar", ""),
    ("HT", "Haïti", ""),
    ("LU", "Luxembourg", ""),
    ("MC", "Monaco", ""),
    ("AD", "Andorre", ""),
    ("IE", "Irlande", ""),
    ("AT", "Autriche", ""),
    ("SE", "Suède", ""),
    ("NO", "Norvège", ""),
    ("DK", "Danemark", ""),
    ("FI", "Finlande", ""),
    ("IS", "Islande", ""),
    ("GR", "Grèce", ""),
    ("PL", "Pologne", ""),
    ("CZ", "Tchéquie", ""),
    ("SK", "Slovaquie", ""),
    ("HU", "Hongrie", ""),
    ("RO", "Roumanie", ""),
    ("BG", "Bulgarie", ""),
    ("HR", "Croatie", ""),
    ("RS", "Serbie", ""),
    ("BA", "Bosnie-Herzégovine", ""),
    ("SI", "Slovénie", ""),
    ("JP", "Japon", ""),
    ("CN", "Chine", ""),
    ("KR", "Corée du Sud", ""),
    ("IN", "Inde", ""),
    ("BR", "Brésil", ""),
    ("AR", "Argentine", ""),
    ("MX", "Mexique", ""),
    ("CO", "Colombie", ""),
    ("CL", "Chili", ""),
    ("PE", "Pérou", ""),
    ("AU", "Australie", ""),
    ("NZ", "Nouvelle-Zélande", ""),
    ("ZA", "Afrique du Sud", ""),
    ("RU", "Russie", ""),
    ("UA", "Ukraine", ""),
    ("TR", "Turquie", ""),
    ("IL", "Israël", ""),
    ("LB", "Liban", ""),
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
                        d[cc] = (cc, "")
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
        ("America/New_York", "America/New_York (Heure de l'Est : Caroline du Nord [NC], NY, FL, DC, GA, VA, PA...)"),
        ("America/Chicago", "America/Chicago (Heure du Centre : Chicago, Texas, Louisiane, Tennessee, MO...)"),
        ("America/Denver", "America/Denver (Heure des Montagnes : Denver, Colorado, Utah, NM...)"),
        ("America/Phoenix", "America/Phoenix (Montagnes sans heure d'été : Arizona)"),
        ("America/Los_Angeles", "America/Los_Angeles (Heure du Pacifique : Californie, Washington, Oregon...)"),
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

DEFAULT_WORLD_TIMEZONES = [
    ("", "(Déduction automatique selon le nom / groupe)"),
    ("America/New_York", "America/New_York (Heure de l'Est : Caroline du Nord [NC], NY, FL, DC, GA, VA, PA...)"),
    ("America/Chicago", "America/Chicago (Heure du Centre : Chicago, Texas, Louisiane, Tennessee, MO...)"),
    ("America/Denver", "America/Denver (Heure des Montagnes : Denver, Colorado, Utah, NM...)"),
    ("America/Phoenix", "America/Phoenix (Montagnes sans heure d'été : Arizona)"),
    ("America/Los_Angeles", "America/Los_Angeles (Heure du Pacifique : Californie, Washington, Oregon...)"),
    ("America/Anchorage", "America/Anchorage (Alaska)"),
    ("Pacific/Honolulu", "Pacific/Honolulu (Hawaï)"),
    ("Europe/Paris", "Europe/Paris (France métropolitaine, Belgique, Suisse, Europe centrale)"),
    ("Europe/London", "Europe/London (Royaume-Uni, Portugal, UTC)"),
    ("America/Toronto", "America/Toronto (Canada Est - Québec, Ontario)"),
    ("America/Vancouver", "America/Vancouver (Canada Pacifique)"),
    ("America/Guadeloupe", "America/Guadeloupe (Antilles - Guadeloupe, Martinique)"),
    ("Indian/Reunion", "Indian/Reunion (La Réunion)"),
    ("Pacific/Noumea", "Pacific/Noumea (Nouvelle-Calédonie)"),
    ("Pacific/Tahiti", "Pacific/Tahiti (Polynésie française)"),
    ("Asia/Tokyo", "Asia/Tokyo (Japon)"),
    ("Australia/Sydney", "Australia/Sydney (Australie Est)"),
]

def make_btn(label_text, icon_name=None, tooltip=None):
    btn = Gtk.Button()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    box.set_halign(Gtk.Align.CENTER)
    if icon_name:
        img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        box.pack_start(img, False, False, 0)
    lbl = Gtk.Label(label=label_text)
    box.pack_start(lbl, False, False, 0)
    btn.add(box)
    btn._label_widget = lbl
    if tooltip:
        btn.set_tooltip_text(tooltip)
    return btn


class EditStationWindow(Gtk.Window):
    def __init__(self, mode="edit", current_name="", current_url="", current_country="", current_timezone="", current_group="", available_groups=None):
        self.mode = mode
        if self.mode == "add":
            title = _("Ajouter une radio (TiMonde)")
            header_text = _("<b>Enter new station details:</b>")
            save_label = _("Ajouter à mes radios")
            save_icon = "list-add"
        elif self.mode == "save-ephemeral":
            title = _("Conserver la radio dans les favoris (TiMonde)")
            header_text = _("<b>Keep this randomly discovered station in your favorites:</b>")
            save_label = _("Conserver dans mes favoris")
            save_icon = "document-save"
        else:
            title = _("Modifier la radio (TiMonde)")
            header_text = _("<b>Edit station settings:</b>")
            save_label = _("Enregistrer")
            save_icon = "document-save"
        self.save_icon = save_icon

        super().__init__(title=title)
        self.set_default_size(580, 360)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(14)
        
        # Icône PNG native
        for icon_path in [
            "/usr/share/icons/hicolor/48x48/apps/timonde_on.png",
            "/usr/share/icons/hicolor/32x32/apps/timonde_on.png",
            "/usr/share/icons/hicolor/24x24/apps/timonde_on.png",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "../icons/hicolor/48x48/apps/timonde_on.png"),
        ]:
            if os.path.exists(icon_path):
                try:
                    self.set_icon_from_file(icon_path)
                    break
                except Exception:
                    pass
        else:
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
        lbl_name = Gtk.Label(label=_("Station name:"))
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

        group_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.combo_group = Gtk.ComboBoxText.new_with_entry()
        self.combo_group.append_text("[ / ] (Racine — Sans groupe)")
        if available_groups:
            for g in available_groups:
                if g and g not in ("[ / ] (Racine — Sans groupe)", "/"):
                    self.combo_group.append_text(g)
        if current_group and (not available_groups or current_group not in available_groups):
            if current_group not in ("[ / ] (Racine — Sans groupe)", "/"):
                self.combo_group.append_text(current_group)

        entry_group_child = self.combo_group.get_child()
        if entry_group_child:
            entry_group_child.set_placeholder_text("Sélectionnez ou tapez (ex: /France/Bretagne ou / pour racine)")
            entry_group_child.connect("activate", self.on_save_clicked)

        if current_group:
            clean_cur = current_group.strip()
            if clean_cur in ("", "/", "root"):
                if entry_group_child:
                    entry_group_child.set_text("/")
                self.combo_group.set_active(0)
            else:
                if entry_group_child:
                    entry_group_child.set_text(clean_cur)
                model = self.combo_group.get_model()
                for idx, row in enumerate(model):
                    if row[0] == clean_cur:
                        self.combo_group.set_active(idx)
                        break
        elif available_groups:
            self.combo_group.set_active(1 if len(available_groups) > 0 else 0)

        self.combo_group.set_hexpand(True)
        group_box.pack_start(self.combo_group, True, True, 0)

        btn_group_help = make_btn("?", "help-browser", "Comment nommer les groupes et sous-groupes (convention Linux /)")
        btn_group_help.connect("clicked", self.on_show_group_naming_help)
        group_box.pack_start(btn_group_help, False, False, 0)

        grid.attach(group_box, 1, 2, 1, 1)

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
        self.country_store.append(["", "(Déduction automatique selon le groupe)", ""])
        
        # 2. Liste des pays
        for code, (cname, cflag) in sorted(COUNTRIES_REGISTRY.items(), key=lambda x: (x[1][0] != "France", x[1][0])):
            search_key = f"{cname} {code}".lower()
            display_label = f"[{code}] {cname}"
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
        btn_clear_country = Gtk.Button(label="Effacer")
        btn_clear_country.set_tooltip_text("Effacer / Mode automatique")
        btn_clear_country.connect("clicked", lambda b: self.entry_country_search.set_text(""))
        country_box.pack_start(btn_clear_country, False, False, 0)

        grid.attach(country_box, 1, 3, 1, 1)

        # 5. Fuseau horaire
        lbl_tz = Gtk.Label(label=_("Timezone:"))
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
            cname, _dummy = COUNTRIES_REGISTRY[self.selected_country_code]
            self.entry_country_search.set_text(f"[{self.selected_country_code}] {cname}")
        elif self.selected_country_code:
            self.entry_country_search.set_text(self.selected_country_code)

        # Initialiser la liste des fuseaux horaires
        self.populate_timezones_for_country(self.selected_country_code, preserve_tz=self.initial_timezone)

        # Boutons d'action
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.pack_start(btn_box, False, False, 0)

        if self.mode == "edit":
            btn_delete = make_btn(_("Delete this station"), "edit-delete")
            btn_delete.get_style_context().add_class("destructive-action")
            btn_delete.connect("clicked", self.on_delete_clicked)
            btn_box.pack_start(btn_delete, False, False, 0)

        btn_cancel = make_btn(_("Cancel"), "process-stop")
        btn_cancel.connect("clicked", self.on_cancel_clicked)
        btn_box.pack_start(btn_cancel, False, False, 0)

        spacer = Gtk.Box()
        btn_box.pack_start(spacer, True, True, 0)

        self.btn_save = make_btn(save_label, self.save_icon)
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
        display_label = model[tree_iter][1]
        self.selected_country_code = code
        self._updating_country_text = True
        self.entry_country_search.set_text(display_label)
        self._updating_country_text = False
        self.populate_timezones_for_country(code)
        return True

    def on_country_search_changed(self, entry):
        if getattr(self, "_updating_country_text", False):
            return
        raw = entry.get_text().strip()
        if not raw:
            self.selected_country_code = ""
            self.populate_timezones_for_country("")
            return

        found_code = None
        # 1. Format crochets [US] ou parenthèses (US)
        if "[" in raw and "]" in raw:
            cand = raw.split("[")[-1].split("]")[0].strip().upper()
            if cand in COUNTRIES_REGISTRY:
                found_code = cand
        elif "(" in raw and ")" in raw:
            cand = raw.split("(") [-1].split(")")[0].strip().upper()
            if cand in COUNTRIES_REGISTRY:
                found_code = cand
        elif raw.upper() in COUNTRIES_REGISTRY:
            found_code = raw.upper()
        else:
            # 2. Alias et noms usuels insensibles à la casse / aux accents
            norm = raw.lower().replace("é", "e").replace("è", "e").replace("-", " ")
            aliases = {
                "usa": "US",
                "etats unis": "US",
                "united states": "US",
                "north carolina": "US",
                "caroline du nord": "US",
                "south carolina": "US",
                "caroline du sud": "US",
                "california": "US",
                "californie": "US",
                "florida": "US",
                "floride": "US",
                "texas": "US",
                "new york": "US",
                "georgia": "US",
                "georgie": "US",
                "virginia": "US",
                "virginie": "US",
                "tennessee": "US",
                "uk": "GB",
                "royaume uni": "GB",
                "angleterre": "GB",
            }
            if norm in aliases:
                found_code = aliases[norm]
            else:
                for code, (cname, _flag) in COUNTRIES_REGISTRY.items():
                    c_norm = cname.lower().replace("é", "e").replace("è", "e").replace("-", " ")
                    if c_norm == norm or c_norm.startswith(norm):
                        found_code = code
                        break

        # Si l'utilisateur a tapé une région ou un état spécifique, présélectionner le bon fuseau
        pref_tz = None
        lower_raw = raw.lower()
        if any(w in lower_raw for w in ["north carolina", "caroline du nord", "nc", "florida", "floride", "georgia", "georgie", "new york", "dc", "virginia", "virginie"]):
            pref_tz = "America/New_York"
        elif any(w in lower_raw for w in ["california", "californie", "los angeles", "san francisco", "seattle"]):
            pref_tz = "America/Los_Angeles"
        elif any(w in lower_raw for w in ["texas", "chicago", "louisiana", "louisiane", "tennessee"]):
            pref_tz = "America/Chicago"
        elif any(w in lower_raw for w in ["denver", "colorado", "utah", "montana"]):
            pref_tz = "America/Denver"

        if found_code != self.selected_country_code or pref_tz:
            self.selected_country_code = found_code or ""
            self.populate_timezones_for_country(self.selected_country_code, preserve_tz=pref_tz or self.initial_timezone)

    def populate_timezones_for_country(self, country_code, preserve_tz=None):
        """
        Génère la liste déroulante des fuseaux horaires selon le pays choisi :
        - Sans pays : sélection libre parmi les principaux fuseaux mondiaux
        - Mono-fuseau : pré-sélectionné (modifiable)
        - Multi-fuseaux : liste complète ouverte avec détails clairs (USA, Canada, etc.)
        - France (FR) : Europe/Paris par défaut avec accès direct aux Outre-mer
        """
        code_upper = (country_code or "").strip().upper()
        self.combo_tz.remove_all()

        if not code_upper:
            for tz_id, label in DEFAULT_WORLD_TIMEZONES:
                self.combo_tz.append_text(label)

            target_tz = preserve_tz or self.initial_timezone or ""
            active_index = 0
            if target_tz:
                for idx, (tz_id, _lbl) in enumerate(DEFAULT_WORLD_TIMEZONES):
                    if tz_id.lower() == target_tz.lower():
                        active_index = idx
                        break

            self.combo_tz.set_active(active_index)
            self.combo_tz.set_sensitive(True)
            self.lbl_tz_hint.set_markup("<small><i>(Déduction automatique ou choix libre)</i></small>")
            return

        tz_list = WORLD_TIMEZONES.get(code_upper, [])
        if not tz_list:
            self.combo_tz.append_text(_("(Timezone not defined)"))
            self.combo_tz.set_active(0)
            self.combo_tz.set_sensitive(True)
            self.lbl_tz_hint.set_markup("<small><i>" + _("(Unknown)") + "</i></small>")
            return

        for tz_id, label in tz_list:
            self.combo_tz.append_text(label)

        active_index = 0
        target_tz = preserve_tz or self.initial_timezone or ""
        if target_tz:
            for idx, (tz_id, _tzname) in enumerate(tz_list):
                if tz_id.lower() == target_tz.lower():
                    active_index = idx
                    break

        self.combo_tz.set_active(active_index)
        self.combo_tz.set_sensitive(True)

        if len(tz_list) == 1:
            self.lbl_tz_hint.set_markup("<small><i>" + _("(Single inferred timezone)") + "</i></small>")
        elif code_upper == "FR":
            self.lbl_tz_hint.set_markup("<small><i>" + _("(Metropolitan or Overseas)") + "</i></small>")
        else:
            self.lbl_tz_hint.set_markup(f"<small><i>({len(tz_list)} fuseaux disponibles)</i></small>")

    def get_selected_timezone_id(self):
        code_upper = (self.selected_country_code or "").strip().upper()
        if not code_upper:
            idx = self.combo_tz.get_active()
            if 0 <= idx < len(DEFAULT_WORLD_TIMEZONES):
                tz_id = DEFAULT_WORLD_TIMEZONES[idx][0]
                return tz_id if tz_id else None
            return None
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
            message_format=_("Delete « {} » from favorites?").format(current_display_name)
        )
        dialog.format_secondary_text(_("This action will permanently remove this station from your collection."))
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        btn_del_confirm = dialog.add_button(_("Supprimer"), Gtk.ResponseType.OK)
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

    def on_show_group_naming_help(self, widget):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            message_format="Organisation des groupes et sous-groupes (Convention Linux)"
        )
        dialog.format_secondary_markup(
            "TiMonde utilise la convention des chemins avec le séparateur <b>/</b> :\n\n"
            "• <b>/</b> ou <b>(Racine)</b> : Place la radio à la racine du menu (sans aucun groupe).\n"
            "• <b>/Gabon</b> ou <b>Gabon</b> : Place la radio dans le groupe « Gabon ».\n"
            "• <b>/France/Bretagne</b> : Place la radio dans le sous-groupe « Bretagne » sous « France ».\n"
            "• <b>/Belgique/NL</b> : Place la radio dans le sous-groupe « NL » sous « Belgique ».\n"
            "• <b>France/Radios locales ICI</b> : Sous-groupe à espaces sous « France ».\n\n"
            "<i>Les groupes et sous-groupes sont créés automatiquement s'ils n'existent pas encore.</i>"
        )
        dialog.run()
        dialog.destroy()

    def on_save_clicked(self, widget):
        name = self.entry_name.get_text().strip()
        url = clean_stream_url(self.entry_url.get_text().strip())
        country = self.selected_country_code or None
        timezone = self.get_selected_timezone_id()

        # Si le code pays n'a pas été fixé via sélection mais est présent dans l'entrée texte
        if not country:
            raw_c = self.entry_country_search.get_text().strip()
            if "[" in raw_c and "]" in raw_c:
                cand = raw_c.split("[")[-1].split("]")[0].strip().upper()
                if cand in COUNTRIES_REGISTRY:
                    country = cand
            elif "(" in raw_c and ")" in raw_c:
                cand = raw_c.split("(") [-1].split(")")[0].strip().upper()
                if cand in COUNTRIES_REGISTRY:
                    country = cand
            elif raw_c.upper() in COUNTRIES_REGISTRY:
                country = raw_c.upper()

        # Inférence automatique du pays si un fuseau bien défini a été choisi
        if not country and timezone:
            if timezone.startswith("America/New_York") or timezone.startswith("America/Chicago") or timezone.startswith("America/Denver") or timezone.startswith("America/Los_Angeles") or timezone.startswith("America/Phoenix") or timezone.startswith("America/Anchorage") or timezone.startswith("Pacific/Honolulu"):
                country = "US"
            elif timezone.startswith("Europe/Paris"):
                country = "FR"
            elif timezone.startswith("Europe/London"):
                country = "GB"
            elif timezone.startswith("America/Toronto") or timezone.startswith("America/Vancouver") or timezone.startswith("America/Montreal"):
                country = "CA"

        child_entry = self.combo_group.get_child()
        custom_grp_txt = child_entry.get_text().strip() if child_entry else ""
        raw_group = custom_grp_txt or self.combo_group.get_active_text() or self.current_group_orig or ""

        # Normalisation selon la convention Linux avec /
        clean_grp = raw_group.strip()
        if clean_grp in ("[ / ] (Racine — Sans groupe)", "/", "root", "(Racine)"):
            selected_group = ""
        else:
            # Enlever les slashes surnuméraires au début et à la fin (ex: "/France/Bretagne/" -> "France/Bretagne")
            selected_group = clean_grp.strip("/").strip()

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
