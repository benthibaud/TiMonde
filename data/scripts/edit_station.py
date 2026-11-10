#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Éditeur universel de radio pour TiMonde (GTK3) :
- Modifier une radio existante (--mode edit)
- Ajouter une nouvelle radio (--mode add)
- Conserver une radio éphémère (--mode save-ephemeral)

Dispose d'un sélecteur de pays avec recherche filtrante en direct (247 pays)
et d'une synchronisation automatique des fuseaux horaires.
"""

import sys
import os
import re
import json
import argparse
import gi

# Module d'internationalisation & socle commun TiMonde
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s

from timonde_common import (
    clean_stream_url,
    attach_country_completion,
    COUNTRIES_REGISTRY,
    DEFAULT_WORLD_TIMEZONES,
    WORLD_TIMEZONES,
    make_btn,
    update_btn_content,
    StreamPreviewPlayer,
    set_window_icon,
    show_group_naming_help_dialog,
    check_stream_url,
    ContributeStationDialog,
    normalize_lookup,
    resolve_country_code,
    infer_timezone,
    normalize_group_path,
    set_container_margins,
    apply_timonde_app_css,
)

# Sauvegarde impérative des arguments CLI avant que GTK ne supprime --name (mot-clé réservé GTK/X11)
SAVED_ARGV = list(sys.argv)

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib


class EditStationWindow(Gtk.Window):
    def __init__(self, mode="edit", current_name="", current_url="", current_country="", current_timezone="", current_group="", available_groups=None, standalone=True, on_done_callback=None, groups=None, default_group=None, station_data=None, on_save=None, parent_window=None, **kwargs):
        if station_data and isinstance(station_data, dict):
            current_name = current_name or station_data.get("name", "")
            current_url = current_url or station_data.get("url", "")
            current_country = current_country or station_data.get("country", "")
            current_timezone = current_timezone or station_data.get("timezone", "")
            current_group = current_group or station_data.get("group", "")
        if on_done_callback is None and on_save is not None:
            on_done_callback = on_save
        if available_groups is None and groups is not None:
            available_groups = groups
        if not current_group and default_group:
            current_group = default_group
        self.mode = mode
        self.standalone = standalone
        self.on_done_callback = on_done_callback
        if self.mode == "add":
            title = _("Add a station (TiMonde)")
            header_text = _("<b>Enter new station details:</b>")
            save_label = _("Add to my stations")
            save_icon = "list-add"
        elif self.mode == "save-ephemeral":
            title = _("Save station to favorites (TiMonde)")
            header_text = _("<b>Keep this randomly discovered station in your favorites:</b>")
            save_label = _("Keep in favorites")
            save_icon = "document-save"
        else:
            title = _("Edit station (TiMonde)")
            header_text = _("<b>Edit station settings:</b>")
            save_label = _("Save")
            save_icon = "document-save"
        self.save_icon = save_icon

        super().__init__(title=title)
        self.set_default_size(620, 380)
        self.set_position(Gtk.WindowPosition.CENTER)

        set_window_icon(self)
        apply_timonde_app_css()
        if parent_window:
            self.set_transient_for(parent_window)
            self.set_modal(True)

        self.saved = False
        self.result_data = None
        self.current_group_orig = current_group
        self.initial_timezone = (current_timezone or "").strip()
        self.selected_country_code = (current_country or "").strip().upper()
        self.preview_player = StreamPreviewPlayer(on_status_changed=self._on_preview_status)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        set_container_margins(vbox, margin=14)
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

        # 2. URL du flux audio + Bouton Tester / Écouter en direct
        lbl_url = Gtk.Label(label=_("Audio stream URL:"))
        lbl_url.set_halign(Gtk.Align.END)
        lbl_url.set_valign(Gtk.Align.START)
        grid.attach(lbl_url, 0, 1, 1, 1)

        url_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        url_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.entry_url = Gtk.Entry()
        self.entry_url.set_text(current_url)
        self.entry_url.set_hexpand(True)
        self.entry_url.connect("activate", self.on_save_clicked)
        url_hbox.pack_start(self.entry_url, True, True, 0)

        self.btn_test_url = make_btn(_("Test"), "media-playback-start", _("Check link validity and listen to stream preview"))
        self.btn_test_url.connect("clicked", self.on_test_url_clicked)
        url_hbox.pack_start(self.btn_test_url, False, False, 0)

        self.btn_rb = make_btn(_("Radio-Browser"), "network-server", _("Check if stream is listed or contribute to directory"))
        self.btn_rb.connect("clicked", self.on_check_radio_browser_clicked)
        url_hbox.pack_start(self.btn_rb, False, False, 0)

        url_vbox.pack_start(url_hbox, False, False, 0)

        self.lbl_url_status = Gtk.Label(label="")
        self.lbl_url_status.set_halign(Gtk.Align.START)
        self.lbl_url_status.set_no_show_all(True)
        url_vbox.pack_start(self.lbl_url_status, False, False, 0)

        # Bandeau discret en cas de divergence de nom d'antenne détecté
        self.box_air_divergence = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.box_air_divergence.set_no_show_all(True)

        self.lbl_air_name = Gtk.Label(label="")
        self.lbl_air_name.set_halign(Gtk.Align.START)
        self.lbl_air_name.set_use_markup(True)
        self.box_air_divergence.pack_start(self.lbl_air_name, False, False, 0)

        self.btn_align_air_name = make_btn(_("Align name"), "edit-copy", _("Use this on-air broadcast name for your bookmark"))
        self.btn_align_air_name.connect("clicked", self.on_align_air_name_clicked)
        self.box_air_divergence.pack_start(self.btn_align_air_name, False, False, 0)

        url_vbox.pack_start(self.box_air_divergence, False, False, 0)

        grid.attach(url_vbox, 1, 1, 1, 1)

        # 3. Groupe d'appartenance
        lbl_group = Gtk.Label(label=_("Group / Folder:"))
        lbl_group.set_halign(Gtk.Align.END)
        grid.attach(lbl_group, 0, 2, 1, 1)

        group_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.combo_group = Gtk.ComboBoxText.new_with_entry()
        root_label = _("[ / ] Root (Without group)")
        self.combo_group.append_text(root_label)
        if available_groups:
            for g in available_groups:
                if g and g not in (root_label, "[ / ] (Racine — Sans groupe)", "/"):
                    self.combo_group.append_text(g)
        if current_group and (not available_groups or current_group not in available_groups):
            if current_group not in (root_label, "[ / ] (Racine — Sans groupe)", "/"):
                self.combo_group.append_text(current_group)

        entry_group_child = self.combo_group.get_child()
        if entry_group_child:
            entry_group_child.set_placeholder_text(_("Select or type (e.g. /France/Brittany or / for root)"))
            entry_group_child.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-clear")
            entry_group_child.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _("Clear field (click to empty)"))
            entry_group_child.connect("icon-press", lambda e, pos, ev: e.set_text("") if pos == Gtk.EntryIconPosition.SECONDARY else None)
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
                for idx, row in enumerate(self.combo_group.get_model()):
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

        group_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        group_container.pack_start(group_box, False, False, 0)
        lbl_grp_hint = Gtk.Label(label="<small><i>[i] Astuce : Tapez un nom libre ou utilisez / pour sous-dossiers (ex: /Musique/Jazz ou / pour racine)</i></small>")
        lbl_grp_hint.set_use_markup(True)
        lbl_grp_hint.set_halign(Gtk.Align.START)
        group_container.pack_start(lbl_grp_hint, False, False, 0)

        grid.attach(group_container, 1, 2, 1, 1)

        # 4. Sélecteur de Pays avec recherche affinante en direct
        lbl_country = Gtk.Label(label=_("Country:"))
        lbl_country.set_halign(Gtk.Align.END)
        grid.attach(lbl_country, 0, 3, 1, 1)

        country_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.entry_country_search = Gtk.Entry()
        self.entry_country_search.set_placeholder_text("Tapez pour chercher dans n'importe quelle langue (ex: Deutschland, France, Canada...)")
        self.entry_country_search.set_hexpand(True)

        attach_country_completion(self.entry_country_search, on_selected=self.on_country_match_selected)
        self.entry_country_search.connect("changed", self.on_country_search_changed)
        self.entry_country_search.connect("activate", self.on_save_clicked)
        country_box.pack_start(self.entry_country_search, True, True, 0)

        btn_clear_country = Gtk.Button(label=_("Clear"))
        btn_clear_country.set_tooltip_text(_("Clear / Automatic mode"))
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

        if self.selected_country_code and self.selected_country_code in COUNTRIES_REGISTRY:
            cname = COUNTRIES_REGISTRY[self.selected_country_code][0]
            self.entry_country_search.set_text(f"[{self.selected_country_code}] {cname}")
        elif self.selected_country_code:
            self.entry_country_search.set_text(self.selected_country_code)

        self.populate_timezones_for_country(self.selected_country_code, preserve_tz=self.initial_timezone)

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

        self.connect("destroy", self._on_window_destroy)
        self.connect("key-press-event", self.on_key_press)
        GLib.idle_add(self.setup_focus)

    def _on_window_destroy(self, _widget):
        if hasattr(self, "preview_player") and self.preview_player:
            self.preview_player.stop(silent=True)
        if self.standalone:
            Gtk.main_quit()

    def on_test_url_clicked(self, _widget):
        import threading
        url = clean_stream_url(self.entry_url.get_text().strip())
        name = self.entry_name.get_text().strip() or "Aperçu du flux"
        if not url:
            self._on_preview_status(False, "", "[!] Veuillez saisir une URL de flux valide.", True)
            return
        self.preview_player.toggle(name, url)

        def _check_meta():
            try:
                ok, msg, meta = check_stream_url(url, timeout=3.5, fetch_meta=True)
                if ok and meta and meta.get("icy_name"):
                    raw_icy = meta["icy_name"].strip()
                    if raw_icy:
                        GLib.idle_add(self._on_air_meta_detected, raw_icy)
            except Exception:
                pass
        threading.Thread(target=_check_meta, daemon=True).start()

    def _on_air_meta_detected(self, icy_name):
        import html
        current_name = self.entry_name.get_text().strip()
        clean_icy = icy_name.strip()
        if clean_icy.startswith("/") or clean_icy.lower() in ("no name", "unnamed", "default", "stream", "live", "untitled"):
            self.box_air_divergence.hide()
            return

        if clean_icy and clean_icy.lower() != current_name.lower():
            self.detected_icy_name = clean_icy
            self.lbl_air_name.set_markup(
                f"<small><i>[i] {_('On-air broadcast name:')} <b>{html.escape(clean_icy)}</b></i></small>"
            )
            self.box_air_divergence.show_all()
        else:
            self.box_air_divergence.hide()

    def on_align_air_name_clicked(self, _widget):
        if getattr(self, "detected_icy_name", ""):
            self.entry_name.set_text(self.detected_icy_name)
            self.box_air_divergence.hide()

    def on_check_radio_browser_clicked(self, _widget):
        url = clean_stream_url(self.entry_url.get_text().strip())
        name = self.entry_name.get_text().strip()
        country = self.selected_country_code or ""

        if not url:
            d = Gtk.MessageDialog(
                transient_for=self,
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                message_format=_("Please enter a stream URL first.")
            )
            d.connect("response", lambda dialog, r: dialog.destroy())
            d.show_all()
            return

        dlg = ContributeStationDialog(
            parent=self,
            station_name=name,
            current_url=url,
            country_code=country,
        )

        def on_contribute_resp(dialog, resp):
            existing = getattr(dialog, "existing_info", None)
            dialog.destroy()
            if resp == Gtk.ResponseType.APPLY and existing:
                ex_cc = (existing.get("countrycode") or "").strip().upper()
                if ex_cc:
                    self.set_country(ex_cc)

        dlg.connect("response", on_contribute_resp)
        dlg.show_all()

    def run(self):
        self.show_all()

    def set_country(self, code):
        code = (code or "").strip().upper()
        if code and code in COUNTRIES_REGISTRY:
            cname = COUNTRIES_REGISTRY[code][0]
            self.selected_country_code = code
            self._updating_country_text = True
            self.entry_country_search.set_text(f"[{code}] {cname}")
            self._updating_country_text = False
            self.populate_timezones_for_country(code)
        elif code:
            self.selected_country_code = code
            self._updating_country_text = True
            self.entry_country_search.set_text(code)
            self._updating_country_text = False
            self.populate_timezones_for_country(code)

    def _on_preview_status(self, is_playing, _url, message, is_error):
        import html
        if is_playing:
            update_btn_content(self.btn_test_url, _("Stop"), "media-playback-stop")
        else:
            update_btn_content(self.btn_test_url, _("Test"), "media-playback-start")
        if message:
            color = "#e74c3c" if is_error else "#2ecc71"
            self.lbl_url_status.set_markup(f"<small><span foreground='{color}'><b>{html.escape(message)}</b></span></small>")
            self.lbl_url_status.show()
        else:
            self.lbl_url_status.hide()

    def setup_focus(self):
        text = self.entry_name.get_text()
        self.entry_name.set_position(len(text))
        return False

    def on_country_match_selected(self, code, display_label):
        self.selected_country_code = code
        self.populate_timezones_for_country(code)

    def on_country_search_changed(self, entry):
        if getattr(self, "_updating_country_text", False):
            return
        raw = entry.get_text().strip()
        if not raw:
            self.selected_country_code = ""
            self.populate_timezones_for_country("")
            return

        cand = resolve_country_code(raw)
        found_code = cand if (cand and cand in COUNTRIES_REGISTRY) else None
        pref_tz = infer_timezone(found_code or "", raw, raw)

        if found_code != self.selected_country_code or pref_tz:
            self.selected_country_code = found_code or ""
            self.populate_timezones_for_country(self.selected_country_code, preserve_tz=pref_tz or self.initial_timezone)

    def populate_timezones_for_country(self, country_code, preserve_tz=None):
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
            self.lbl_tz_hint.set_markup(f"<small><i>({_('{count} available timezones').format(count=len(tz_list))})</i></small>")

    def get_selected_timezone_id(self):
        code_upper = (self.selected_country_code or "").strip().upper()
        if not code_upper:
            idx = self.combo_tz.get_active()
            if 0 <= idx < len(DEFAULT_WORLD_TIMEZONES):
                return DEFAULT_WORLD_TIMEZONES[idx][0] or None
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
        current_display_name = self.entry_name.get_text().strip() or "..."
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
            type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            message_format=_("Delete « {} » from favorites?").format(current_display_name)
        )
        dialog.format_secondary_text(_("This action will permanently remove this station from your collection."))
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        btn_del_confirm = dialog.add_button(_("Delete"), Gtk.ResponseType.OK)
        btn_del_confirm.get_style_context().add_class("destructive-action")

        def on_delete_resp(dlg, response):
            dlg.destroy()
            if response == Gtk.ResponseType.OK:
                self.preview_player.stop(silent=True)
                self.result_data = {
                    "action": "delete",
                    "name": current_display_name,
                    "url": self.entry_url.get_text().strip(),
                }
                self.saved = True
                if self.on_done_callback:
                    self.on_done_callback(self.result_data)
                elif self.standalone:
                    print(json.dumps(self.result_data, ensure_ascii=False))
                self.destroy()

        dialog.connect("response", on_delete_resp)
        dialog.show_all()

    def on_cancel_clicked(self, widget):
        self.preview_player.stop(silent=True)
        self.destroy()

    def on_show_group_naming_help(self, widget):
        show_group_naming_help_dialog(self)

    def on_save_clicked(self, widget):
        self.preview_player.stop(silent=True)
        name = self.entry_name.get_text().strip()
        url = clean_stream_url(self.entry_url.get_text().strip())
        country = self.selected_country_code or resolve_country_code(self.entry_country_search.get_text().strip())
        timezone = self.get_selected_timezone_id()

        if not country and timezone:
            for c_code, tzs in WORLD_TIMEZONES.items():
                if any(tz_id == timezone for tz_id, _ in tzs):
                    country = c_code
                    break

        child_entry = self.combo_group.get_child()
        custom_grp_txt = child_entry.get_text().strip() if child_entry else ""
        raw_group = custom_grp_txt or self.combo_group.get_active_text() or self.current_group_orig or ""
        selected_group = normalize_group_path(raw_group, return_root_literal=False)

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
        if self.on_done_callback:
            self.on_done_callback(self.result_data)
        elif self.standalone:
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
