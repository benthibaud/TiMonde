#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Explorateur modulaire de bouquets de radios (TiMonde)
Charge dynamiquement les bouquets depuis des fichiers XML par pays (data/bouquets/*.xml) :
- Modèle analogue aux fichiers de langue .po : chaque pays a son fichier XML dédié.
- Découverte automatique des pays disponibles.
- Prise en charge des pays multilingues (Belgique, Suisse, Canada).
- Bouquets nationaux (grandes radios phares) et régionaux (expatriés, régions spécifiques).
- Prévention automatique des doublons avec les favoris existants.
"""

import sys
import os
import glob
import json
import xml.etree.ElementTree as ET
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango


def find_bouquets_dir():
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "bouquets"),
        os.path.join(os.path.expanduser("~"), ".local", "share", "timonde", "bouquets"),
        "/usr/local/share/timonde/bouquets",
        "/usr/share/timonde/bouquets",
    ]
    for c in candidates:
        if os.path.isdir(c) and glob.glob(os.path.join(c, "*.xml")):
            return os.path.abspath(c)
    return None


def parse_bouquets_xml():
    b_dir = find_bouquets_dir()
    db = {}
    if not b_dir:
        sys.stderr.write("Avertissement : Répertoire des bouquets XML introuvable.\n")
        return db

    for xml_file in sorted(glob.glob(os.path.join(b_dir, "*.xml"))):
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            code = root.attrib.get("country", os.path.splitext(os.path.basename(xml_file))[0].upper())
            name = root.attrib.get("name", code)
            flag = root.attrib.get("flag", "")
            display_name = f"{name} {flag}".strip()
            multilingual = root.attrib.get("multilingual", "false").lower() == "true"

            country_data = {
                "name": display_name,
                "multilingual": multilingual,
                "languages": [],
                "sub_bouquets": {},
                "national": [],
                "regions": {},
            }

            if multilingual:
                for comm in root.findall("community"):
                    c_id = comm.attrib.get("id", "GEN")
                    c_name = comm.attrib.get("name", c_id)
                    country_data["languages"].append((c_id, c_name))
                    sub_data = {"national": [], "regions": {}}

                    nat = comm.find("national")
                    if nat is not None:
                        for st in nat.findall("station"):
                            sub_data["national"].append((
                                st.attrib.get("name", ""),
                                st.attrib.get("url", ""),
                                st.attrib.get("genre", "")
                            ))

                    regs = comm.find("regions")
                    if regs is not None:
                        for reg in regs.findall("region"):
                            r_name = reg.attrib.get("name", "Région")
                            st_list = []
                            for st in reg.findall("station"):
                                st_list.append((
                                    st.attrib.get("name", ""),
                                    st.attrib.get("url", ""),
                                    st.attrib.get("genre", "")
                                ))
                            sub_data["regions"][r_name] = st_list

                    country_data["sub_bouquets"][c_id] = sub_data
            else:
                nat = root.find("national")
                if nat is not None:
                    for st in nat.findall("station"):
                        country_data["national"].append((
                            st.attrib.get("name", ""),
                            st.attrib.get("url", ""),
                            st.attrib.get("genre", "")
                        ))

                regs = root.find("regions")
                if regs is not None:
                    for reg in regs.findall("region"):
                        r_name = reg.attrib.get("name", "Région")
                        st_list = []
                        for st in reg.findall("station"):
                            st_list.append((
                                st.attrib.get("name", ""),
                                st.attrib.get("url", ""),
                                st.attrib.get("genre", "")
                            ))
                        country_data["regions"][r_name] = st_list

            db[code] = country_data
        except Exception as e:
            sys.stderr.write(f"Erreur chargement bouquet {xml_file} : {e}\n")

    return db


class BrowseBouquetsWindow(Gtk.Window):
    def __init__(self, existing_stations, bouquets_db):
        super().__init__(title="📻 Découvrir les bouquets de radios (TiMonde)")
        self.set_default_size(750, 560)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)
        self.set_icon_name("audio-x-generic")

        self.bouquets_db = bouquets_db
        self.existing_stations = existing_stations
        self.existing_urls = {s.get("url", "").strip() for s in existing_stations if s.get("url")}
        self.existing_names = {s.get("name", "").strip().lower() for s in existing_stations if s.get("name")}

        self.selected_stations = []
        self.chosen_group_name = ""
        self.saved = False

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(vbox)

        # 1. En-tête explicatif
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.pack_start(header_box, False, False, 0)

        lbl_title = Gtk.Label()
        lbl_title.set_markup("<b><big>📻 Sélections & Bouquets de Webradios</big></b>")
        lbl_title.set_halign(Gtk.Align.START)
        header_box.pack_start(lbl_title, False, False, 0)

        lbl_desc = Gtk.Label(
            label="Sélectionnez un pays et un bouquet pour importer les stations majeures dans vos favoris.\n"
                  "Les radios déjà présentes dans votre liste sont automatiquement identifiées pour éviter les doublons."
        )
        lbl_desc.set_halign(Gtk.Align.START)
        header_box.pack_start(lbl_desc, False, False, 0)

        # 2. Zone de filtres (Pays, Langue, Bouquet)
        filter_frame = Gtk.Frame(label=" 1. Choix du bouquet ")
        filter_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        filter_box.set_border_width(8)
        filter_frame.add(filter_box)
        vbox.pack_start(filter_frame, False, False, 0)

        row_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        filter_box.pack_start(row_top, False, False, 0)

        # Choix du pays
        lbl_country = Gtk.Label(label="<b>Pays :</b>")
        lbl_country.set_use_markup(True)
        row_top.pack_start(lbl_country, False, False, 0)

        self.combo_country = Gtk.ComboBoxText()
        # Priorité aux pays francophones, puis alphabétique
        priority_codes = ["FR", "BE", "CH", "CA"]
        sorted_codes = [c for c in priority_codes if c in self.bouquets_db]
        other_codes = sorted([c for c in self.bouquets_db.keys() if c not in priority_codes],
                             key=lambda c: self.bouquets_db[c]["name"])
        all_ordered_codes = sorted_codes + other_codes

        for code in all_ordered_codes:
            info = self.bouquets_db[code]
            self.combo_country.append(code, info["name"])

        if all_ordered_codes:
            self.combo_country.set_active_id(all_ordered_codes[0])
        self.combo_country.connect("changed", self.on_country_changed)
        row_top.pack_start(self.combo_country, False, False, 0)

        # Choix de la langue (pour Belgique, Suisse, Canada)
        self.lbl_lang = Gtk.Label(label="<b>Langue / Communauté :</b>")
        self.lbl_lang.set_use_markup(True)
        row_top.pack_start(self.lbl_lang, False, False, 0)

        self.combo_lang = Gtk.ComboBoxText()
        self.combo_lang.connect("changed", self.on_lang_changed)
        row_top.pack_start(self.combo_lang, False, False, 0)

        # Choix du niveau : National vs Régional
        row_scope = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        filter_box.pack_start(row_scope, False, False, 0)

        self.radio_national = Gtk.RadioButton.new_with_label(None, "⭐ Bouquet National (Grandes stations incontournables)")
        self.radio_national.connect("toggled", self.on_scope_changed)
        row_scope.pack_start(self.radio_national, False, False, 0)

        self.radio_region = Gtk.RadioButton.new_with_label_from_widget(self.radio_national, "📍 Régions & Locales (Expatriés, régions spécifiques)")
        self.radio_region.connect("toggled", self.on_scope_changed)
        row_scope.pack_start(self.radio_region, False, False, 0)

        self.combo_region = Gtk.ComboBoxText()
        self.combo_region.connect("changed", self.on_region_changed)
        row_scope.pack_start(self.combo_region, True, True, 0)

        # 3. Zone de la liste des stations
        list_frame = Gtk.Frame(label=" 2. Stations à ajouter ")
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        list_box.set_border_width(8)
        list_frame.add(list_box)
        vbox.pack_start(list_frame, True, True, 0)

        # Modèle : [checked (bool), name (str), genre (str), status_note (str), url (str), is_duplicate (bool)]
        self.store = Gtk.ListStore(bool, str, str, str, str, bool)
        self.treeview = Gtk.TreeView(model=self.store)
        self.treeview.set_rules_hint(True)

        renderer_toggle = Gtk.CellRendererToggle()
        renderer_toggle.connect("toggled", self.on_cell_toggled)
        col_check = Gtk.TreeViewColumn("Ajouter", renderer_toggle, active=0)
        self.treeview.append_column(col_check)

        renderer_text = Gtk.CellRendererText()
        col_name = Gtk.TreeViewColumn("Nom de la station", renderer_text, text=1)
        col_name.set_min_width(200)
        self.treeview.append_column(col_name)

        renderer_genre = Gtk.CellRendererText()
        col_genre = Gtk.TreeViewColumn("Genre / Style", renderer_genre, text=2)
        col_genre.set_min_width(180)
        self.treeview.append_column(col_genre)

        renderer_note = Gtk.CellRendererText()
        col_note = Gtk.TreeViewColumn("Statut", renderer_note, markup=3)
        self.treeview.append_column(col_note)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.treeview)
        list_box.pack_start(scroll, True, True, 0)

        sel_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        list_box.pack_start(sel_buttons_box, False, False, 0)

        btn_select_all = Gtk.Button(label=" Tout cocher ")
        btn_select_all.connect("clicked", lambda w: self.set_all_checks(True))
        sel_buttons_box.pack_start(btn_select_all, False, False, 0)

        btn_unselect_all = Gtk.Button(label=" Tout décocher ")
        btn_unselect_all.connect("clicked", lambda w: self.set_all_checks(False))
        sel_buttons_box.pack_start(btn_unselect_all, False, False, 0)

        self.lbl_count = Gtk.Label()
        self.lbl_count.set_halign(Gtk.Align.END)
        sel_buttons_box.pack_end(self.lbl_count, False, False, 0)

        # 4. Pied de page
        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.pack_start(bottom_box, False, False, 0)

        lbl_target = Gtk.Label(label="<b>Nom du groupe dans vos favoris :</b>")
        lbl_target.set_use_markup(True)
        bottom_box.pack_start(lbl_target, False, False, 0)

        self.entry_group = Gtk.Entry()
        self.entry_group.set_width_chars(28)
        bottom_box.pack_start(self.entry_group, True, True, 0)

        btn_cancel = Gtk.Button(label=" Annuler ")
        btn_cancel.connect("clicked", lambda w: self.destroy())
        bottom_box.pack_start(btn_cancel, False, False, 0)

        self.btn_import = Gtk.Button(label=" ➕ Importer dans TiMonde ")
        self.btn_import.get_style_context().add_class("suggested-action")
        self.btn_import.connect("clicked", self.on_import_clicked)
        bottom_box.pack_start(self.btn_import, False, False, 0)

        self.update_languages()
        self.load_current_bouquet()

    def on_cell_toggled(self, widget, path):
        it = self.store.get_iter(path)
        cur = self.store.get_value(it, 0)
        self.store.set_value(it, 0, not cur)
        self.update_selection_count()

    def set_all_checks(self, val):
        it = self.store.get_iter_first()
        while it:
            is_dup = self.store.get_value(it, 5)
            if val and is_dup:
                self.store.set_value(it, 0, False)
            else:
                self.store.set_value(it, 0, val)
            it = self.store.iter_next(it)
        self.update_selection_count()

    def on_country_changed(self, widget):
        self.update_languages()
        self.load_current_bouquet()

    def on_lang_changed(self, widget):
        self.load_current_bouquet()

    def on_scope_changed(self, widget):
        if widget.get_active():
            is_region = self.radio_region.get_active()
            self.combo_region.set_sensitive(is_region)
            self.load_current_bouquet()

    def on_region_changed(self, widget):
        if self.radio_region.get_active():
            self.load_current_bouquet()

    def update_languages(self):
        country_id = self.combo_country.get_active_id()
        info = self.bouquets_db.get(country_id, {})
        is_multi = info.get("multilingual", False)

        self.lbl_lang.set_visible(is_multi)
        self.combo_lang.set_visible(is_multi)
        self.combo_lang.remove_all()

        if is_multi:
            for l_code, l_label in info.get("languages", []):
                self.combo_lang.append(l_code, l_label)
            if info.get("languages"):
                self.combo_lang.set_active(0)

    def get_current_data(self):
        country_id = self.combo_country.get_active_id()
        info = self.bouquets_db.get(country_id, {})

        if info.get("multilingual", False):
            lang_id = self.combo_lang.get_active_id() or (info["languages"][0][0] if info.get("languages") else "FR")
            sub = info.get("sub_bouquets", {}).get(lang_id, {})
            national = sub.get("national", [])
            regions = sub.get("regions", {})
        else:
            national = info.get("national", [])
            regions = info.get("regions", {})

        return country_id, info, national, regions

    def load_current_bouquet(self):
        country_id, info, national, regions = self.get_current_data()

        self.combo_region.disconnect_by_func(self.on_region_changed)
        self.combo_region.remove_all()
        for reg_name in regions.keys():
            self.combo_region.append_text(reg_name)
        if regions:
            self.combo_region.set_active(0)
            self.radio_region.set_sensitive(True)
        else:
            self.radio_region.set_sensitive(False)
            if self.radio_region.get_active():
                self.radio_national.set_active(True)
        self.combo_region.connect("changed", self.on_region_changed)

        is_region = self.radio_region.get_active()
        self.combo_region.set_sensitive(is_region and bool(regions))

        stations = []
        default_group = ""

        country_name = info.get("name", "").split()[0]
        if is_region and regions:
            reg_name = self.combo_region.get_active_text() or list(regions.keys())[0]
            stations = regions.get(reg_name, [])
            default_group = f"Radios {reg_name}"
        else:
            stations = national
            if info.get("multilingual", False):
                lang_text = self.combo_lang.get_active_text() or ""
                lang_short = lang_text.split()[0] if lang_text else ""
                default_group = f"Radios Nationales ({country_name} - {lang_short})"
            else:
                default_group = f"Radios Nationales ({country_name})"

        self.entry_group.set_text(default_group)

        self.store.clear()
        for name, url, genre in stations:
            clean_url = url.strip()
            clean_name = name.strip().lower()

            is_dup = (clean_url in self.existing_urls) or (clean_name in self.existing_names)
            checked = not is_dup
            status_note = "<span color='#888888'><i>(Déjà dans vos favoris)</i></span>" if is_dup else "<span color='#2e7d32'><b>Nouveau</b></span>"

            self.store.append([checked, name, genre, status_note, url, is_dup])

        self.update_selection_count()

    def update_selection_count(self):
        total = 0
        checked = 0
        it = self.store.get_iter_first()
        while it:
            total += 1
            if self.store.get_value(it, 0):
                checked += 1
            it = self.store.iter_next(it)
        self.lbl_count.set_text(f"{checked} / {total} station(s) sélectionnée(s)")
        self.btn_import.set_sensitive(checked > 0)

    def on_import_clicked(self, widget):
        group_name = self.entry_group.get_text().strip()
        if not group_name:
            group_name = "Bouquets Radio"

        selected = []
        it = self.store.get_iter_first()
        while it:
            if self.store.get_value(it, 0):
                name = self.store.get_value(it, 1)
                url = self.store.get_value(it, 4)
                selected.append({"name": name, "url": url})
            it = self.store.iter_next(it)

        if not selected:
            return

        self.chosen_group_name = group_name
        self.selected_stations = selected
        self.saved = True

        result = {
            "group_name": self.chosen_group_name,
            "stations": self.selected_stations
        }
        print(json.dumps(result, ensure_ascii=False))
        self.destroy()


def main():
    existing_stations = []
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        try:
            with open(sys.argv[1], "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    existing_stations = data
        except Exception as e:
            sys.stderr.write(f"Avertissement lecture favoris : {e}\n")
    elif not sys.stdin.isatty():
        try:
            raw = sys.stdin.read().strip()
            if raw:
                data = json.loads(raw)
                if isinstance(data, list):
                    existing_stations = data
        except Exception:
            pass

    bouquets_db = parse_bouquets_xml()
    if not bouquets_db:
        sys.stderr.write("Aucun bouquet disponible.\n")
        sys.exit(1)

    win = BrowseBouquetsWindow(existing_stations, bouquets_db)
    win.show_all()
    Gtk.main()

    if win.saved:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
