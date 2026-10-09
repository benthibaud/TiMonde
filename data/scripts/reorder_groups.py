#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface GTK3 interactive pour ordonner, modifier et supprimer les groupes, les radios et les séparateurs de TiMonde.
- Niveau 1 : Liste des groupes (réordonnancement, renommage, suppression, création, déplacement/fusion, double-clic ou Ouvrir pour explorer)
- Niveau 2 : Radios & Séparateurs du groupe (réordonnancement, modification nom/URL/intertitre, ajout séparateur, suppression, déplacement vers un autre groupe, tri A-Z)
- Clic droit contextuel : Déplacer vers... / Nouveau groupe / Modifier / Insérer séparateur / Supprimer sur chaque élément.
- Raccourcis clavier : Ctrl+M (Déplacer vers), Ctrl+N (Nouveau groupe), Suppr (Supprimer), F2 (Modifier), Échap/Retour (Retour aux groupes).
"""

import sys
import os

# Neutralisation inconditionnelle d'IBus pour éviter tout gel des frappes clavier sous GTK3
# (les sessions de bureau avec socket IBus orpheline ou rompue absorbent et perdent les touches)
os.environ.pop("GTK_IM_MODULE", None)
os.environ.pop("XMODIFIERS", None)
os.environ.pop("QT_IM_MODULE", None)
import json
import subprocess

# Module d'internationalisation & socle commun TiMonde
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from timonde_i18n import _
except ImportError:
    def _(s): return s

from timonde_common import clean_stream_url, strip_unsupported_emojis, make_btn, normalize_group_path

import urllib.request
import urllib.parse
import urllib.error
import re
import threading
from concurrent.futures import ThreadPoolExecutor

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def check_stream_url(url, timeout=3.5):
    if not url or not url.strip():
        return False, "URL vide", None
    clean = url.strip()
    try:
        req = urllib.request.Request(
            clean,
            headers={
                "User-Agent": USER_AGENT,
                "Icy-MetaData": "1",
                "Range": "bytes=0-1024"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            final_url = resp.geturl()
            redir = final_url if final_url != clean else None
            if 200 <= code < 400:
                return True, f"HTTP {code}", redir
            return False, f"HTTP {code}", None
    except urllib.error.HTTPError as e:
        if e.code in (403, 451):
            return "GEO", f"Géo-restreint ({e.code})", None
        return False, f"Erreur {e.code}", None
    except urllib.error.URLError as e:
        return False, "Inaccessible", None
    except Exception as e:
        return False, "Délai dépassé", None

def search_radio_browser_replacement(station_name):
    clean = re.sub(r'\s*-\s*[A-Za-z0-9\s,]+$', '', station_name).strip()
    clean = re.sub(r'\(.*?\)', '', clean).strip()
    clean = re.sub(r'\b(FM|AM|Radio|Webradio|Live)\b', '', clean, flags=re.IGNORECASE).strip()

    candidates = []
    queries = [clean]
    if len(clean.split()) > 1 and len(clean.split()[0]) >= 4:
        queries.append(clean.split()[0])

    norm_target = re.sub(r'[^a-z0-9]', '', clean.lower())

    for q in queries:
        if len(q) < 3:
            continue
        for endpoint in ["https://de1.api.radio-browser.info", "https://all.api.radio-browser.info"]:
            try:
                api_url = f"{endpoint}/json/stations/byname/{urllib.parse.quote(q)}?limit=8"
                req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.getcode() == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        for s in data:
                            s_name = s.get("name", "")
                            norm_s = re.sub(r'[^a-z0-9]', '', s_name.lower())
                            if norm_target in norm_s or norm_s in norm_target:
                                u = (s.get("url_resolved") or s.get("url") or "").strip()
                                bitrate = s.get("bitrate", 0)
                                country = s.get("countrycode", "")
                                if u and u.startswith("http"):
                                    candidates.append((s_name, u, bitrate, country))
                        break
            except Exception:
                continue

    valid_candidates = []
    for c_name, c_url, bitrate, country in candidates[:5]:
        ok, msg, final_u = check_stream_url(c_url, timeout=3.0)
        if ok is True:
            valid_candidates.append({
                "name": c_name,
                "url": final_u or c_url,
                "bitrate": bitrate,
                "country": country,
                "status": msg
            })

    return valid_candidates

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib

class ReorderWindow(Gtk.Window):
    def __init__(self, data, auto_check=False):
        super().__init__(title=_("Organiser les groupes et radios (TiMonde)"))
        self.set_default_size(760, 550)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)
        
        # Icône PNG native multi-résolutions
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

        self.data = data
        self.auto_check = auto_check
        self.current_group_idx = None  # None = vue Groupes, int = vue Radios du groupe data[idx]
        self.saved = False
        self.audit_results = {}  # url -> {"status": "online"|"offline"|"geo"|"redirect", "msg": str, "redirect": str|None}
        self.filter_broken_only = False

        self.connect("key-press-event", self.on_key_press_event)

        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(self.vbox)

        # 1. En-tête de navigation
        self.nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.vbox.pack_start(self.nav_box, False, False, 0)

        self.btn_back = make_btn(_("Back to groups"), "go-previous", "Revenir à la liste principale des groupes (Échap)")
        self.btn_back.connect("clicked", self.on_back_clicked)
        self.nav_box.pack_start(self.btn_back, False, False, 0)

        self.header_title = Gtk.Label()
        self.header_title.set_halign(Gtk.Align.START)
        self.nav_box.pack_start(self.header_title, True, True, 0)

        # Outils d'audit et vérification de santé des flux
        self.btn_check_streams = make_btn(_("Check streams"), "view-refresh", _("Test stream availability and locate broken links"))
        self.btn_check_streams.connect("clicked", self.on_check_streams_clicked)
        self.nav_box.pack_start(self.btn_check_streams, False, False, 0)

        self.chk_broken_only = Gtk.CheckButton(label=_("Dead links only"))
        self.chk_broken_only.set_tooltip_text(_("Display offline radio streams only"))
        self.chk_broken_only.connect("toggled", self.on_filter_broken_toggled)
        self.nav_box.pack_start(self.chk_broken_only, False, False, 0)

        self.btn_apply_redirects = make_btn(_("Apply redirects"), "system-run", _("Automatically update redirected streams to direct URL"))
        self.btn_apply_redirects.connect("clicked", self.on_apply_redirects_clicked)
        self.nav_box.pack_start(self.btn_apply_redirects, False, False, 0)

        self.help_label = Gtk.Label()
        self.help_label.set_halign(Gtk.Align.START)
        self.help_label.set_line_wrap(True)
        self.vbox.pack_start(self.help_label, False, False, 0)

        # 2. Zone centrale : Liste + Boutons
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.vbox.pack_start(content_box, True, True, 0)

        # Modèle de données : [index_reel, ordre_affiche, nom, info_supp]
        self.store = Gtk.ListStore(int, str, str, str)
        self.treeview = Gtk.TreeView(model=self.store)
        self.treeview.set_rules_hint(True)
        self.treeview.connect("row-activated", self.on_row_activated)
        self.treeview.connect("button-press-event", self.on_treeview_button_press)
        self.treeview.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)

        # Colonne 1 : Ordre (#)
        renderer_order = Gtk.CellRendererText()
        renderer_order.set_property("editable", True)
        renderer_order.connect("edited", self.on_order_edited)
        self.col_order = Gtk.TreeViewColumn("#", renderer_order, text=1)
        self.col_order.set_fixed_width(45)
        self.treeview.append_column(self.col_order)

        # Colonne 2 : Nom
        self.renderer_name = Gtk.CellRendererText()
        self.renderer_name.set_property("ellipsize", Pango.EllipsizeMode.END)
        self.col_name = Gtk.TreeViewColumn("Nom", self.renderer_name, text=2)
        self.col_name.set_expand(True)
        self.treeview.append_column(self.col_name)

        # Colonne 3 : Info (Radios / URL / Séparateur / État du flux)
        renderer_info = Gtk.CellRendererText()
        renderer_info.set_property("xalign", 1.0)
        renderer_info.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
        self.col_info = Gtk.TreeViewColumn("Détails", renderer_info, markup=3)
        self.col_info.set_fixed_width(180)
        self.treeview.append_column(self.col_info)

        # Défilement
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        scrolled.add(self.treeview)
        content_box.pack_start(scrolled, True, True, 0)

        # Boutons latéraux
        side_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content_box.pack_start(side_box, False, False, 0)

        self.btn_open = make_btn(_("Open"), "document-open", "Classer les radios de ce groupe (Entrée ou double-clic)")
        self.btn_open.connect("clicked", self.on_open_clicked)
        side_box.pack_start(self.btn_open, False, False, 0)

        self.btn_new_group = make_btn(_("New group"), "folder-new", "Créer un nouveau groupe de radios (Ctrl+N)")
        self.btn_new_group.connect("clicked", self.on_create_group_clicked)
        side_box.pack_start(self.btn_new_group, False, False, 0)

        self.btn_move_to = make_btn(_("Move to..."), "go-jump", "Déplacer la sélection vers un autre groupe (Ctrl+M)")
        self.btn_move_to.connect("clicked", self.on_move_to_clicked)
        side_box.pack_start(self.btn_move_to, False, False, 0)

        sep0 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(sep0, False, False, 2)

        btn_top = make_btn(_("Top"), "go-top", "Placer l'élément sélectionné en tout premier")
        btn_top.connect("clicked", self.on_move_top_clicked)
        side_box.pack_start(btn_top, False, False, 0)

        btn_up = make_btn(_("Move up"), "go-up", "Monter d'un rang")
        btn_up.connect("clicked", self.on_move_up_clicked)
        side_box.pack_start(btn_up, False, False, 0)

        btn_down = make_btn(_("Move down"), "go-down", "Descendre d'un rang")
        btn_down.connect("clicked", self.on_move_down_clicked)
        side_box.pack_start(btn_down, False, False, 0)

        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(sep1, False, False, 2)

        self.btn_add_station = make_btn(_("Add station"), "list-add", "Ajouter une nouvelle radio dans ce groupe")
        self.btn_add_station.connect("clicked", self.on_add_station_clicked)
        side_box.pack_start(self.btn_add_station, False, False, 0)

        self.btn_add_sep = make_btn(_("Separator"), "format-line-spacing", "Insérer un séparateur ou un intertitre dans ce groupe")
        self.btn_add_sep.connect("clicked", self.on_add_separator_clicked)
        side_box.pack_start(self.btn_add_sep, False, False, 0)

        btn_sort = make_btn(_("Sort A-Z"), "view-sort-ascending", "Trier automatiquement cette liste par ordre alphabétique")
        btn_sort.connect("clicked", self.on_sort_az_clicked)
        side_box.pack_start(btn_sort, False, False, 0)

        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        side_box.pack_start(sep2, False, False, 2)

        btn_edit = make_btn(_("Edit"), "document-edit", "Modifier le nom, l'URL ou l'intertitre sélectionné (F2)")
        btn_edit.connect("clicked", self.on_edit_clicked)
        side_box.pack_start(btn_edit, False, False, 0)

        self.btn_repair = make_btn(_("Repair stream..."), "system-search", _("Search Radio-Browser for a working replacement stream"))
        self.btn_repair.connect("clicked", self.on_repair_stream_clicked)
        side_box.pack_start(self.btn_repair, False, False, 0)

        btn_del = make_btn(_("Delete"), "edit-delete", "Supprimer l'élément ou le groupe sélectionné (Suppr)")
        btn_del.connect("clicked", self.on_delete_clicked)
        side_box.pack_start(btn_del, False, False, 0)

        # 3. Zone de notification / feedback visuel
        self.lbl_feedback = Gtk.Label(label="")
        self.lbl_feedback.set_halign(Gtk.Align.START)
        self.vbox.pack_start(self.lbl_feedback, False, False, 0)

        # 4. Barre d'actions inférieure
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.vbox.pack_start(btn_box, False, False, 0)

        btn_cancel = make_btn(_("Cancel"), "process-stop")
        btn_cancel.connect("clicked", self.on_cancel_clicked)
        btn_box.pack_start(btn_cancel, False, False, 0)

        self.btn_export_csv = make_btn(_("Export to CSV"), "document-save-as", _("Export all stations to CSV spreadsheet format"))
        self.btn_export_csv.connect("clicked", lambda w: self.on_export_csv_clicked())
        btn_box.pack_start(self.btn_export_csv, False, False, 0)

        spacer = Gtk.Box()
        btn_box.pack_start(spacer, True, True, 0)

        btn_save = make_btn(_("Save and reload"), "document-save")
        btn_save.get_style_context().add_class("suggested-action")
        btn_save.connect("clicked", self.on_save_clicked)
        btn_box.pack_start(btn_save, False, False, 0)

        self.connect("destroy", Gtk.main_quit)

        # Affichage initial
        self.update_view()

    def on_key_press_event(self, widget, event):
        # Vérifier si l'utilisateur appuie sur des raccourcis claviers globaux
        keyname = Gdk.keyval_name(event.keyval)
        state = event.state

        ctrl_pressed = bool(state & Gdk.ModifierType.CONTROL_MASK)

        if keyname == "Delete":
            self.on_delete_clicked(None)
            return True
        elif keyname == "F2":
            self.on_edit_clicked(None)
            return True
        elif (ctrl_pressed and keyname in ("n", "N")) or (keyname in ("n", "N") and not ctrl_pressed and not self.treeview.is_focus()):
            self.on_create_group_clicked(None)
            return True
        elif (ctrl_pressed and keyname in ("m", "M")) or (keyname in ("m", "M") and not ctrl_pressed and not self.treeview.is_focus()):
            self.on_move_to_clicked(None)
            return True
        elif keyname in ("Escape", "BackSpace") and self.current_group_idx is not None:
            self.on_back_clicked(None)
            return True

        return False

    def get_current_list(self):
        if self.current_group_idx is None:
            return self.data
        else:
            return self.data[self.current_group_idx].get("stations", [])

    def is_item_separator(self, item):
        if item.get("is_separator"):
            return True
        if "stations" in item and not item.get("is_separator"):
            return False
        url = item.get("url", "")
        name = item.get("name", "")
        if url == "" or url == "---":
            return True
        if name.startswith("[separator") or name == "---" or name == "separator - - -":
            return True
        return False

    def update_view(self, select_idx=None):
        self.store.clear()
        if self.current_group_idx is None:
            # Mode Groupes
            self.btn_back.hide()
            self.btn_open.show()
            self.btn_add_sep.show()
            self.btn_add_station.hide()
            if hasattr(self.btn_move_to, "_label_widget"):
                self.btn_move_to._label_widget.set_text("Transférer...")
            else:
                self.btn_move_to.set_label("Transférer...")
            self.btn_move_to.set_tooltip_text("Transférer le contenu de ce groupe vers un autre groupe (Ctrl+M)")
            self.btn_new_group.set_tooltip_text("Créer un nouveau groupe de radios (Ctrl+N)")
            self.header_title.set_markup("<b>Groupes de radios</b>")
            self.help_label.set_markup(
                "<small>• Modifiez le <b>#</b> ou utilisez <b>Monter / Descendre</b> pour ordonner les groupes.\n"
                "• <b>Double-cliquez sur un groupe</b> (ou Ouvrir) pour classer ses radios et séparateurs.\n"
                "• Utilisez <b>Transférer...</b> pour fusionner ou déplacer le contenu vers un autre groupe.\n"
                "• Utilisez <b>Nouveau groupe</b> pour ajouter un dossier de radios.</small>"
            )
            self.col_name.set_title(_("Group name"))
            self.col_info.set_title(_("Contents"))

            for i, g in enumerate(self.data):
                if self.is_item_separator(g):
                    title = g.get("name", "").strip()
                    clean = title.strip("-").strip() if title.startswith("---") else title
                    display_title = f"─── {clean} ───" if clean else "───────────────"
                    self.store.append([i, str(i + 1), display_title, "— Séparateur —"])
                else:
                    stations = g.get("stations", [])
                    nb_radios = sum(1 for s in stations if not self.is_item_separator(s))
                    nb_seps = sum(1 for s in stations if self.is_item_separator(s))
                    nb_dead = sum(1 for s in stations if self.audit_results.get(s.get("url", ""), {}).get("status") == "offline")
                    nb_redir = sum(1 for s in stations if self.audit_results.get(s.get("url", ""), {}).get("status") == "redirect")

                    info_parts = [f"{nb_radios} radio{'s' if nb_radios > 1 else ''}"]
                    if nb_seps > 0:
                        info_parts.append(f"{nb_seps} sép.")
                    if nb_dead > 0:
                        info_parts.append(f"<span foreground='#e74c3c'><b>[!] {nb_dead} lien{'s' if nb_dead > 1 else ''} mort{'s' if nb_dead > 1 else ''}</b></span>")
                    elif nb_redir > 0:
                        info_parts.append(f"<span foreground='#e67e22'>[~] {nb_redir} redir.</span>")
                    elif self.audit_results and nb_radios > 0:
                        info_parts.append("<span foreground='#2ecc71'>[OK] Tout est en ligne</span>")

                    clean_name = strip_unsupported_emojis(g["name"]) or g["name"]
                    disp_group_name = clean_name
                    if "/" in clean_name:
                        parts = [p.strip() for p in clean_name.split("/")]
                        depth = len(parts) - 1
                        indent = "    " * depth
                        disp_group_name = f"{indent}↳ {parts[-1]}  ({ ' / '.join(parts[:-1]) })"
                    self.store.append([i, str(i + 1), disp_group_name, " · ".join(info_parts)])
        else:
            # Mode Radios du groupe
            grp = self.data[self.current_group_idx]
            self.btn_back.show()
            self.btn_open.hide()
            self.btn_add_sep.show()
            self.btn_add_station.show()
            if hasattr(self.btn_move_to, "_label_widget"):
                self.btn_move_to._label_widget.set_text("Déplacer vers...")
            else:
                self.btn_move_to.set_label("Déplacer vers...")
            self.btn_move_to.set_tooltip_text("Déplacer la ou les radios sélectionnées vers un autre groupe (Ctrl+M)")
            self.btn_new_group.set_tooltip_text("Créer un nouveau groupe et y déplacer les radios sélectionnées (Ctrl+N)")
            clean_grp_title = strip_unsupported_emojis(grp['name']) or grp['name']
            if "/" in clean_grp_title:
                clean_grp_title = clean_grp_title.replace("/", " / ")
            self.header_title.set_markup(f"<b>Radios du groupe : {clean_grp_title}</b>")
            self.help_label.set_markup(
                "<small>• Modifiez le <b>#</b> ou utilisez <b>Monter / Descendre</b> pour classer les radios.\n"
                "• Cliquez sur <b>Vérifier les flux</b> pour repérer les liens morts (rouge) et les réparer.\n"
                "• Cliquez sur <b>Réparer flux...</b> pour chercher un flux actif de remplacement sur Radio-Browser.\n"
                "• Cliquez sur <b>Séparateur</b> pour insérer un intertitre de section.</small>"
            )
            self.col_name.set_title(_("Name / Header"))
            self.col_info.set_title(_("Details"))

            for i, s in enumerate(grp.get("stations", [])):
                if self.is_item_separator(s):
                    if self.filter_broken_only:
                        continue
                    s["is_separator"] = True
                    s["url"] = ""
                    title = s.get("name", "").strip()
                    if title.startswith("[separator") or title == "---" or title == "separator - - -":
                        title = ""
                        s["name"] = ""
                    if title:
                        disp_name = f"─── {title} ───"
                        info_str = "Intertitre"
                    else:
                        disp_name = "────────────────────────"
                        info_str = "Séparateur"
                    self.store.append([i, str(i + 1), disp_name, info_str])
                else:
                    s["is_separator"] = False
                    url = s.get("url", "")
                    audit = self.audit_results.get(url)

                    if self.filter_broken_only and (not audit or audit.get("status") != "offline"):
                        continue

                    if audit:
                        st_val = audit.get("status")
                        st_msg = audit.get("msg", "")
                        if st_val == "online":
                            info_str = "<span foreground='#2ecc71'>[OK] En direct</span>"
                        elif st_val == "offline":
                            info_str = f"<span foreground='#e74c3c'><b>[!] Lien mort</b> ({st_msg})</span>"
                        elif st_val == "redirect":
                            info_str = "<span foreground='#e67e22'>[~] Redirigé</span>"
                        elif st_val == "geo":
                            info_str = "<span foreground='#f1c40f'>[?] Géo-restreint</span>"
                        else:
                            info_str = st_msg
                    else:
                        country_tag = s.get("country", "")
                        if country_tag:
                            info_str = f"[{country_tag}]"
                        elif len(url) > 28:
                            info_str = url[:25] + "..."
                        else:
                            info_str = url

                    clean_st_name = strip_unsupported_emojis(s.get("name", "")) or s.get("name", "")
                    self.store.append([i, str(i + 1), clean_st_name, info_str])

        if select_idx is not None:
            items = self.get_current_list()
            if 0 <= select_idx < len(items):
                path = Gtk.TreePath.new_from_string(str(select_idx))
                self.treeview.get_selection().select_path(path)
                self.treeview.scroll_to_cell(path, None, False, 0.0, 0.0)

    def get_selected_index(self):
        model, paths = self.treeview.get_selection().get_selected_rows()
        if paths:
            tree_iter = model.get_iter(paths[0])
            return model[tree_iter][0]
        return None

    def get_selected_indices(self):
        model, paths = self.treeview.get_selection().get_selected_rows()
        indices = []
        for p in paths:
            tree_iter = model.get_iter(p)
            indices.append(model[tree_iter][0])
        return sorted(indices)

    def on_row_activated(self, treeview, path, column):
        if self.current_group_idx is None and column != self.col_order:
            idx = int(path.to_string())
            if idx < len(self.data) and self.is_item_separator(self.data[idx]):
                self.on_edit_clicked(None)
            else:
                self.on_open_clicked(None)
        elif self.current_group_idx is not None and column != self.col_order:
            self.on_edit_clicked(None)

    def on_treeview_button_press(self, treeview, event):
        if event.button == 3:  # Clic droit
            pth = treeview.get_path_at_pos(int(event.x), int(event.y))
            if pth:
                path, col, _x, _y = pth
                sel = treeview.get_selection()
                model, paths = sel.get_selected_rows()
                if path not in paths:
                    sel.unselect_all()
                    sel.select_path(path)
                self.show_context_menu(event)
                return True
        return False

    def show_context_menu(self, event):
        menu = Gtk.Menu()
        idx = self.get_selected_index()
        items = self.get_current_list()

        if self.current_group_idx is None:
            item_open = Gtk.MenuItem(label="Ouvrir les radios")
            item_open.connect("activate", self.on_open_clicked)
            menu.append(item_open)

            item_new_g = Gtk.MenuItem(label="Nouveau groupe...")
            item_new_g.connect("activate", self.on_create_group_clicked)
            menu.append(item_new_g)

            item_move_g = Gtk.MenuItem(label="Transférer le contenu vers un autre groupe...")
            item_move_g.connect("activate", self.on_move_to_clicked)
            menu.append(item_move_g)

            item_edit = Gtk.MenuItem(label="Renommer le groupe...")
            item_edit.connect("activate", self.on_edit_clicked)
            menu.append(item_edit)

            item_del = Gtk.MenuItem(label="Supprimer le groupe...")
            item_del.connect("activate", self.on_delete_clicked)
            menu.append(item_del)
        else:
            target = items[idx] if idx is not None and idx < len(items) else None
            is_sep = target and self.is_item_separator(target)

            if is_sep:
                item_edit = Gtk.MenuItem(label="Modifier l'intertitre...")
                item_edit.connect("activate", self.on_edit_clicked)
                menu.append(item_edit)
            else:
                item_edit = Gtk.MenuItem(label="Modifier la radio...")
                item_edit.connect("activate", self.on_edit_clicked)
                menu.append(item_edit)

            item_move_st = Gtk.MenuItem(label="Déplacer vers un autre groupe...")
            item_move_st.connect("activate", self.on_move_to_clicked)
            menu.append(item_move_st)

            item_new_g_here = Gtk.MenuItem(label="Nouveau groupe...")
            item_new_g_here.connect("activate", self.on_create_group_clicked)
            menu.append(item_new_g_here)

            item_add_st = Gtk.MenuItem(label="Ajouter une radio...")
            item_add_st.connect("activate", self.on_add_station_clicked)
            menu.append(item_add_st)

            item_add_sep = Gtk.MenuItem(label="Insérer un séparateur ici...")
            item_add_sep.connect("activate", self.on_add_separator_clicked)
            menu.append(item_add_sep)

            item_top = Gtk.MenuItem(label="Placer en premier")
            item_top.connect("activate", self.on_move_top_clicked)
            menu.append(item_top)

            if is_sep:
                item_del = Gtk.MenuItem(label="Supprimer ce séparateur")
            else:
                item_del = Gtk.MenuItem(label="Supprimer cette radio...")
            item_del.connect("activate", self.on_delete_clicked)
            menu.append(item_del)

        menu.show_all()
        menu.popup(None, None, None, None, event.button, event.time)

    def show_feedback(self, text, is_success=True):
        color = "#27ae60" if is_success else "#e67e22"
        self.lbl_feedback.set_markup(f"<span foreground='{color}'><b>{text}</b></span>")

    def on_create_group_clicked(self, widget):
        dialog = Gtk.Dialog(
            title="Créer un nouveau groupe",
            transient_for=self,
            flags=0
        )
        dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
        dialog.add_button("Créer", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(12)

        lbl = Gtk.Label(label="<b>Nom du nouveau groupe de favoris :</b>")
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        box.pack_start(lbl, False, False, 0)

        entry = Gtk.Entry()
        entry.set_width_chars(35)
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 0)

        # Si l'utilisateur est dans un groupe et a sélectionné des radios :
        # Proposer de déplacer directement ces radios vers le nouveau groupe
        chk_move_radios = None
        selected_indices = []
        if self.current_group_idx is not None:
            selected_indices = self.get_selected_indices()
            if selected_indices:
                nb = len(selected_indices)
                chk_move_radios = Gtk.CheckButton(
                    label=f"Déplacer immédiatement la ou les {nb} radio(s) sélectionnée(s) dans ce nouveau groupe"
                )
                chk_move_radios.set_active(True)
                box.pack_start(chk_move_radios, False, False, 0)

        dialog.show_all()
        response = dialog.run()
        name = entry.get_text().strip()
        should_move = chk_move_radios.get_active() if chk_move_radios else False
        dialog.destroy()

        if response == Gtk.ResponseType.OK and name:
            for g in self.data:
                if g["name"].strip().lower() == name.lower():
                    md = Gtk.MessageDialog(
                        transient_for=self,
                        flags=0,
                        message_type=Gtk.MessageType.WARNING,
                        buttons=Gtk.ButtonsType.OK,
                        text="Groupe déjà existant"
                    )
                    md.format_secondary_text(f"Un groupe nommé « {name} » existe déjà.")
                    md.run()
                    md.destroy()
                    return

            new_grp = {"name": name, "stations": []}
            self.data.append(new_grp)

            if should_move and selected_indices and self.current_group_idx is not None:
                src_stations = self.data[self.current_group_idx].get("stations", [])
                moved = []
                for i in reversed(selected_indices):
                    if i < len(src_stations):
                        moved.append(src_stations.pop(i))
                moved.reverse()
                new_grp["stations"].extend(moved)
                self.update_view()
                self.show_feedback(f"Groupe « {name} » créé avec {len(moved)} radio(s) transférée(s)")
            else:
                if self.current_group_idx is None:
                    self.update_view(select_idx=len(self.data) - 1)
                else:
                    self.update_view()
                self.show_feedback(f"Nouveau groupe « {name} » créé")

    def on_move_to_clicked(self, widget):
        indices = self.get_selected_indices()
        if not indices:
            md = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Aucune sélection"
            )
            md.format_secondary_text("Veuillez d'abord sélectionner au moins un élément à déplacer.")
            md.run()
            md.destroy()
            return

        # =============================================================
        # CAS 1 : Déplacement de Radios depuis un groupe
        # =============================================================
        if self.current_group_idx is not None:
            current_grp = self.data[self.current_group_idx]
            current_stations = current_grp.get("stations", [])
            selected_stations = [current_stations[i] for i in indices if i < len(current_stations)]
            if not selected_stations:
                return

            available_targets = [(i, g["name"]) for i, g in enumerate(self.data) if i != self.current_group_idx]
            if not available_targets:
                self.on_create_group_clicked(None)
                available_targets = [(i, g["name"]) for i, g in enumerate(self.data) if i != self.current_group_idx]
                if not available_targets:
                    return

            dialog = Gtk.Dialog(
                title="Déplacer vers un autre groupe",
                transient_for=self,
                flags=0
            )
            dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
            dialog.add_button("Déplacer", Gtk.ResponseType.OK)
            dialog.set_default_response(Gtk.ResponseType.OK)

            box = dialog.get_content_area()
            box.set_spacing(10)
            box.set_border_width(12)

            nb_sel = len(selected_stations)
            if nb_sel == 1:
                st_name = selected_stations[0].get("name", "Station")
                lbl_text = f"Déplacer la radio : <b>« {st_name} »</b> vers :"
            elif nb_sel <= 3:
                names = ", ".join([f"« {s.get('name', 'Station')} »" for s in selected_stations])
                lbl_text = f"Déplacer les {nb_sel} radios ({names}) vers :"
            else:
                lbl_text = f"Déplacer les <b>{nb_sel} radios</b> sélectionnées vers :"

            lbl = Gtk.Label(label=lbl_text)
            lbl.set_use_markup(True)
            lbl.set_halign(Gtk.Align.START)
            box.pack_start(lbl, False, False, 0)

            combo = Gtk.ComboBoxText()
            for idx_g, g_name in available_targets:
                if "/" in g_name:
                    parts = [p.strip() for p in g_name.split("/")]
                    disp_g = f"↳ {parts[-1]}  ({ ' / '.join(parts[:-1]) })"
                else:
                    disp_g = g_name
                combo.append(str(idx_g), disp_g)
            combo.set_active(0)
            box.pack_start(combo, False, False, 0)

            # Option d'insertion (Début ou Fin)
            pos_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.pack_start(pos_box, False, False, 0)
            lbl_pos = Gtk.Label(label="Position dans le groupe cible :")
            pos_box.pack_start(lbl_pos, False, False, 0)
            combo_pos = Gtk.ComboBoxText()
            combo_pos.append("end", "À la fin (par défaut)")
            combo_pos.append("start", "Au tout début")
            combo_pos.set_active(0)
            pos_box.pack_start(combo_pos, True, True, 0)

            # Bouton de création instantanée d'un nouveau groupe
            btn_new = make_btn("Créer un nouveau groupe cible...", "folder-new")
            def on_quick_create(b):
                ed = Gtk.Dialog(title="Nouveau groupe cible", transient_for=dialog, flags=0)
                ed.add_button("Annuler", Gtk.ResponseType.CANCEL)
                ed.add_button("Créer", Gtk.ResponseType.OK)
                ed.set_default_response(Gtk.ResponseType.OK)
                ebox = ed.get_content_area()
                ebox.set_spacing(6)
                ebox.set_border_width(10)
                elbl = Gtk.Label(label="Nom du nouveau groupe :")
                ebox.pack_start(elbl, False, False, 0)
                eentry = Gtk.Entry()
                eentry.set_activates_default(True)
                ebox.pack_start(eentry, False, False, 0)
                ed.show_all()
                res = ed.run()
                n = eentry.get_text().strip()
                ed.destroy()
                if res == Gtk.ResponseType.OK and n:
                    new_idx = len(self.data)
                    self.data.append({"name": n, "stations": []})
                    combo.append(str(new_idx), n)
                    combo.set_active_id(str(new_idx))
            btn_new.connect("clicked", on_quick_create)
            box.pack_start(btn_new, False, False, 0)

            dialog.show_all()
            response = dialog.run()
            target_id_str = combo.get_active_id()
            insert_pos = combo_pos.get_active_id() or "end"
            dialog.destroy()

            if response == Gtk.ResponseType.OK and target_id_str is not None:
                target_idx = int(target_id_str)
                target_name = self.data[target_idx]["name"]
                target_stations = self.data[target_idx].setdefault("stations", [])

                moved_items = []
                for i in reversed(indices):
                    if i < len(current_stations):
                        st = current_stations.pop(i)
                        moved_items.append(st)

                # Conserver l'ordre initial des éléments sélectionnés
                moved_items.reverse()
                if insert_pos == "start":
                    for st in reversed(moved_items):
                        target_stations.insert(0, st)
                else:
                    target_stations.extend(moved_items)

                self.update_view()
                self.show_feedback(f"{len(moved_items)} élément(s) déplacé(s) vers « {target_name} »")

        # =============================================================
        # CAS 2 : Déplacement / Fusion depuis la vue Groupes
        # =============================================================
        else:
            if len(indices) == 1:
                src_idx = indices[0]
                src_grp = self.data[src_idx]
                available_targets = [(i, g["name"]) for i, g in enumerate(self.data) if i != src_idx]

                if not available_targets:
                    md = Gtk.MessageDialog(
                        transient_for=self,
                        flags=0,
                        message_type=Gtk.MessageType.INFO,
                        buttons=Gtk.ButtonsType.OK,
                        text="Aucun autre groupe"
                    )
                    md.format_secondary_text("Il n'y a aucun autre groupe vers lequel transférer les radios.")
                    md.run()
                    md.destroy()
                    return

                dialog = Gtk.Dialog(
                    title="Déplacer ou fusionner le groupe",
                    transient_for=self,
                    flags=0
                )
                dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
                dialog.add_button("Valider", Gtk.ResponseType.OK)
                dialog.set_default_response(Gtk.ResponseType.OK)

                box = dialog.get_content_area()
                box.set_spacing(10)
                box.set_border_width(12)

                nb_st = len(src_grp.get("stations", []))
                msg_lbl = f"Groupe source : <b>« {src_grp['name']} »</b> ({nb_st} radio(s))\nChoisissez le groupe de destination et l'action :"
                lbl = Gtk.Label(label=msg_lbl)
                lbl.set_use_markup(True)
                lbl.set_halign(Gtk.Align.START)
                box.pack_start(lbl, False, False, 0)

                combo = Gtk.ComboBoxText()
                for idx_g, g_name in available_targets:
                    if "/" in g_name:
                        parts = [p.strip() for p in g_name.split("/")]
                        disp_g = f"↳ {parts[-1]}  ({ ' / '.join(parts[:-1]) })"
                    else:
                        disp_g = g_name
                    combo.append(str(idx_g), disp_g)
                combo.set_active(0)
                box.pack_start(combo, False, False, 0)

                # Bouton de création instantanée d'un nouveau groupe cible
                btn_new = make_btn("Créer un nouveau groupe cible...", "folder-new")
                def on_quick_create_group(b):
                    ed = Gtk.Dialog(title="Nouveau groupe cible", transient_for=dialog, flags=0)
                    ed.add_button("Annuler", Gtk.ResponseType.CANCEL)
                    ed.add_button("Créer", Gtk.ResponseType.OK)
                    ed.set_default_response(Gtk.ResponseType.OK)
                    ebox = ed.get_content_area()
                    ebox.set_spacing(6)
                    ebox.set_border_width(10)
                    elbl = Gtk.Label(label="Nom du nouveau groupe :")
                    ebox.pack_start(elbl, False, False, 0)
                    eentry = Gtk.Entry()
                    eentry.set_activates_default(True)
                    ebox.pack_start(eentry, False, False, 0)
                    ed.show_all()
                    res = ed.run()
                    n = eentry.get_text().strip()
                    ed.destroy()
                    if res == Gtk.ResponseType.OK and n:
                        new_idx = len(self.data)
                        self.data.append({"name": n, "stations": []})
                        combo.append(str(new_idx), n)
                        combo.set_active_id(str(new_idx))
                btn_new.connect("clicked", on_quick_create_group)
                box.pack_start(btn_new, False, False, 0)

                radio_merge = Gtk.RadioButton.new_with_label(None, "Fusionner : transférer toutes les radios dans le groupe cible")
                radio_subgrp = Gtk.RadioButton.new_with_label_from_widget(radio_merge, "Placer comme sous-groupe du groupe cible")
                box.pack_start(radio_merge, False, False, 0)
                box.pack_start(radio_subgrp, False, False, 0)

                chk_delete_src = Gtk.CheckButton(label="Supprimer le dossier d'origine une fois vidé (si fusion)")
                chk_delete_src.set_active(True)
                box.pack_start(chk_delete_src, False, False, 0)

                dialog.show_all()
                response = dialog.run()
                target_id_str = combo.get_active_id()
                is_subgrp = radio_subgrp.get_active()
                should_del = chk_delete_src.get_active()
                dialog.destroy()

                if response == Gtk.ResponseType.OK and target_id_str is not None:
                    target_idx = int(target_id_str)
                    target_name = self.data[target_idx]["name"]

                    if is_subgrp:
                        # Placer en sous-groupe (extraire le nom de base sans l'ancien parent)
                        base_name = src_grp['name'].split('/')[-1].strip()
                        src_grp["name"] = f"{target_name}/{base_name}"
                        self.update_view(select_idx=src_idx)
                        self.show_feedback(f"Groupe placé comme sous-groupe : « {src_grp['name']} »")
                    else:
                        # Fusion des radios
                        src_stations = src_grp.get("stations", [])
                        self.data[target_idx].setdefault("stations", []).extend(src_stations)

                        if should_del:
                            self.data.pop(src_idx)
                            self.update_view()
                        else:
                            src_grp["stations"] = []
                            self.update_view(select_idx=src_idx)

                        self.show_feedback(f"{len(src_stations)} radio(s) transférée(s) dans « {target_name} »")

            else:
                # Plusieurs groupes sélectionnés : fusion groupée
                available_targets = [(i, g["name"]) for i, g in enumerate(self.data) if i not in indices]

                dialog = Gtk.Dialog(
                    title="Transférer les groupes sélectionnés",
                    transient_for=self,
                    flags=0
                )
                dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
                dialog.add_button("Fusionner", Gtk.ResponseType.OK)
                dialog.set_default_response(Gtk.ResponseType.OK)

                box = dialog.get_content_area()
                box.set_spacing(10)
                box.set_border_width(12)

                total_radios = sum(len(self.data[i].get("stations", [])) for i in indices)
                msg_lbl = f"<b>{len(indices)} groupes sélectionnés</b> ({total_radios} radio(s) au total)\nTransférer tout le contenu vers le groupe cible :"
                lbl = Gtk.Label(label=msg_lbl)
                lbl.set_use_markup(True)
                lbl.set_halign(Gtk.Align.START)
                box.pack_start(lbl, False, False, 0)

                combo = Gtk.ComboBoxText()
                for idx_g, g_name in available_targets:
                    if "/" in g_name:
                        parts = [p.strip() for p in g_name.split("/")]
                        disp_g = f"↳ {parts[-1]}  ({ ' / '.join(parts[:-1]) })"
                    else:
                        disp_g = g_name
                    combo.append(str(idx_g), disp_g)
                if available_targets:
                    combo.set_active(0)
                box.pack_start(combo, False, False, 0)

                btn_new = make_btn("Créer un nouveau groupe cible...", "folder-new")
                def on_quick_create_group_multi(b):
                    ed = Gtk.Dialog(title="Nouveau groupe cible", transient_for=dialog, flags=0)
                    ed.add_button("Annuler", Gtk.ResponseType.CANCEL)
                    ed.add_button("Créer", Gtk.ResponseType.OK)
                    ed.set_default_response(Gtk.ResponseType.OK)
                    ebox = ed.get_content_area()
                    ebox.set_spacing(6)
                    ebox.set_border_width(10)
                    elbl = Gtk.Label(label="Nom du nouveau groupe :")
                    ebox.pack_start(elbl, False, False, 0)
                    eentry = Gtk.Entry()
                    eentry.set_activates_default(True)
                    ebox.pack_start(eentry, False, False, 0)
                    ed.show_all()
                    res = ed.run()
                    n = eentry.get_text().strip()
                    ed.destroy()
                    if res == Gtk.ResponseType.OK and n:
                        new_idx = len(self.data)
                        self.data.append({"name": n, "stations": []})
                        combo.append(str(new_idx), n)
                        combo.set_active_id(str(new_idx))
                btn_new.connect("clicked", on_quick_create_group_multi)
                box.pack_start(btn_new, False, False, 0)

                chk_delete = Gtk.CheckButton(label="Supprimer les groupes d'origine une fois vidés")
                chk_delete.set_active(True)
                box.pack_start(chk_delete, False, False, 0)

                dialog.show_all()
                response = dialog.run()
                target_id_str = combo.get_active_id()
                should_del = chk_delete.get_active()
                dialog.destroy()

                if response == Gtk.ResponseType.OK and target_id_str is not None:
                    target_idx = int(target_id_str)
                    target_grp = self.data[target_idx]
                    target_stations = target_grp.setdefault("stations", [])

                    total_transferred = 0
                    for i in indices:
                        if i < len(self.data):
                            sts = self.data[i].get("stations", [])
                            total_transferred += len(sts)
                            target_stations.extend(sts)
                            self.data[i]["stations"] = []

                    if should_del:
                        for i in reversed(indices):
                            if i != target_idx and i < len(self.data):
                                self.data.pop(i)

                    self.update_view()
                    self.show_feedback(f"{total_transferred} radio(s) transférée(s) dans « {target_grp['name']} »")

    def on_open_clicked(self, widget):
        idx = self.get_selected_index()
        if idx is not None:
            if idx < len(self.data) and self.is_item_separator(self.data[idx]):
                return
            self.current_group_idx = idx
            self.update_view()

    def on_back_clicked(self, widget):
        prev_idx = self.current_group_idx
        self.current_group_idx = None
        self.update_view(select_idx=prev_idx)

    def on_order_edited(self, renderer, path_str, new_text):
        try:
            new_order = int(new_text.strip())
        except ValueError:
            return

        old_idx = int(path_str)
        items = self.get_current_list()
        n = len(items)

        if new_order < 1:
            new_idx = 0
        elif new_order > n:
            new_idx = n - 1
        else:
            new_idx = new_order - 1

        if old_idx != new_idx:
            item = items.pop(old_idx)
            items.insert(new_idx, item)
            self.update_view(select_idx=new_idx)

    def on_move_top_clicked(self, widget):
        idx = self.get_selected_index()
        items = self.get_current_list()
        if idx is not None and idx > 0:
            item = items.pop(idx)
            items.insert(0, item)
            self.update_view(select_idx=0)

    def on_move_up_clicked(self, widget):
        idx = self.get_selected_index()
        items = self.get_current_list()
        if idx is not None and idx > 0:
            items[idx], items[idx - 1] = items[idx - 1], items[idx]
            self.update_view(select_idx=idx - 1)

    def on_move_down_clicked(self, widget):
        idx = self.get_selected_index()
        items = self.get_current_list()
        if idx is not None and idx < len(items) - 1:
            items[idx], items[idx + 1] = items[idx + 1], items[idx]
            self.update_view(select_idx=idx + 1)

    def on_sort_az_clicked(self, widget):
        items = self.get_current_list()
        # On trie en conservant un ordre alphabétique par nom
        items.sort(key=lambda x: x["name"].lower())
        self.update_view(select_idx=0)

    def on_add_station_clicked(self, widget):
        if self.current_group_idx is None:
            return

        grp = self.data[self.current_group_idx]
        current_grp_name = grp["name"]
        all_groups = [g["name"] for g in self.data]

        script_dir = os.path.dirname(os.path.abspath(__file__))
        edit_script = os.path.join(script_dir, "edit_station.py")
        if not os.path.exists(edit_script):
            for cand in ["/usr/share/timonde/scripts/edit_station.py", os.path.expanduser("~/.local/share/timonde/scripts/edit_station.py")]:
                if os.path.exists(cand):
                    edit_script = cand
                    break

        cmd = [
            sys.executable, edit_script,
            "--mode", "add",
            "--group", current_grp_name,
            "--groups-json", json.dumps(all_groups)
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                val = json.loads(res.stdout.strip())
                new_st = {
                    "name": val["name"],
                    "url": val["url"],
                    "country": val.get("country"),
                    "timezone": val.get("timezone"),
                }
                target_grp_name = val.get("group") or current_grp_name
                target_grp = next((g for g in self.data if g["name"] == target_grp_name), grp)
                target_grp.setdefault("stations", []).append(new_st)
                self.show_feedback(f"Radio « {val['name']} » ajoutée")
                self.update_view(select_idx=len(target_grp.get("stations", [])) - 1 if target_grp == grp else None)
        except Exception as e:
            sys.stderr.write(f"Erreur ajout station: {e}\n")

    def on_add_separator_clicked(self, widget):
        dialog = Gtk.Dialog(
            title="Insérer un séparateur",
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            buttons=("Annuler", Gtk.ResponseType.CANCEL, "Insérer", Gtk.ResponseType.OK),
        )
        dialog.set_default_size(380, 150)
        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(12)

        lbl = Gtk.Label(
            label="Titre d'intertitre optionnel :\n"
            "<small>(Laissez vide pour un simple trait de séparation)</small>"
        )
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        box.add(lbl)

        entry = Gtk.Entry()
        entry.set_placeholder_text("Ex : Jazz & Blues (ou laissez vide)")
        box.add(entry)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            title = entry.get_text().strip()
            items = self.get_current_list()
            cur_idx = self.get_selected_index()
            insert_pos = cur_idx + 1 if cur_idx is not None else len(items)

            new_sep = {
                "name": title,
                "url": "",
                "is_separator": True,
            }
            if self.current_group_idx is None:
                new_sep["stations"] = []
            items.insert(insert_pos, new_sep)
            self.update_view(select_idx=insert_pos)
        dialog.destroy()

    def on_edit_clicked(self, widget):
        idx = self.get_selected_index()
        if idx is None:
            return

        items = self.get_current_list()
        target = items[idx]

        if self.is_item_separator(target):
            # Éditer le titre du séparateur (intertitre)
            dialog = Gtk.Dialog(
                title="Modifier le titre du séparateur",
                parent=self,
                flags=Gtk.DialogFlags.MODAL,
                buttons=("Annuler", Gtk.ResponseType.CANCEL, "Enregistrer", Gtk.ResponseType.OK),
            )
            dialog.set_default_size(380, 140)
            box = dialog.get_content_area()
            box.set_spacing(10)
            box.set_border_width(12)

            lbl = Gtk.Label(
                label="Titre d'intertitre :\n<small>(Effacez tout pour un trait simple)</small>"
            )
            lbl.set_use_markup(True)
            lbl.set_halign(Gtk.Align.START)
            box.add(lbl)

            entry = Gtk.Entry()
            raw_title = target.get("name", "")
            clean_title = raw_title.strip("-").strip() if raw_title.startswith("---") else raw_title
            entry.set_text(clean_title)
            box.add(entry)
            dialog.show_all()

            if dialog.run() == Gtk.ResponseType.OK:
                new_title = entry.get_text().strip()
                target["name"] = new_title
                target["url"] = ""
                target["is_separator"] = True
                self.update_view(select_idx=idx)
            dialog.destroy()
        elif self.current_group_idx is None:
            # Éditer le nom du groupe
            dialog = Gtk.Dialog(
                title="Renommer le groupe",
                parent=self,
                flags=Gtk.DialogFlags.MODAL,
                buttons=("Annuler", Gtk.ResponseType.CANCEL, "Enregistrer", Gtk.ResponseType.OK),
            )
            dialog.set_default_size(380, 140)
            box = dialog.get_content_area()
            box.set_spacing(10)
            box.set_border_width(12)

            lbl = Gtk.Label(label="Nouveau nom du groupe :")
            lbl.set_halign(Gtk.Align.START)
            box.add(lbl)

            entry = Gtk.Entry()
            entry.set_text(target["name"])
            box.add(entry)
            dialog.show_all()

            if dialog.run() == Gtk.ResponseType.OK:
                new_name = entry.get_text().strip()
                if new_name and new_name != target["name"]:
                    old_name = target["name"]
                    target["name"] = new_name
                    # Synchroniser tous les sous-groupes enfants si c'était un groupe parent
                    for g in self.data:
                        if g.get("name", "").startswith(old_name + "/"):
                            suffix = g["name"][len(old_name):]
                            g["name"] = f"{new_name}{suffix}"
                    self.update_view(select_idx=idx)
            dialog.destroy()
        elif self.is_item_separator(target):
            # Éditer le titre du séparateur
            dialog = Gtk.Dialog(
                title="Modifier le titre du séparateur",
                parent=self,
                flags=Gtk.DialogFlags.MODAL,
                buttons=("Annuler", Gtk.ResponseType.CANCEL, "Enregistrer", Gtk.ResponseType.OK),
            )
            dialog.set_default_size(380, 140)
            box = dialog.get_content_area()
            box.set_spacing(10)
            box.set_border_width(12)

            lbl = Gtk.Label(
                label="Titre d'intertitre :\n<small>(Effacez tout pour un trait simple)</small>"
            )
            lbl.set_use_markup(True)
            lbl.set_halign(Gtk.Align.START)
            box.add(lbl)

            entry = Gtk.Entry()
            entry.set_text(target.get("name", ""))
            box.add(entry)
            dialog.show_all()

            if dialog.run() == Gtk.ResponseType.OK:
                new_title = entry.get_text().strip()
                target["name"] = new_title
                target["url"] = ""
                target["is_separator"] = True
                self.update_view(select_idx=idx)
            dialog.destroy()
        else:
            # Éditer la radio via le composant unifié edit_station.py
            script_dir = os.path.dirname(os.path.abspath(__file__))
            edit_script = os.path.join(script_dir, "edit_station.py")
            if not os.path.exists(edit_script):
                for cand in ["/usr/share/timonde/scripts/edit_station.py", os.path.expanduser("~/.local/share/timonde/scripts/edit_station.py")]:
                    if os.path.exists(cand):
                        edit_script = cand
                        break

            current_grp_name = self.data[self.current_group_idx]["name"] if self.current_group_idx is not None else ""
            all_groups = [g["name"] for g in self.data]

            cmd = [
                sys.executable, edit_script,
                "--mode", "edit",
                "--station-name", target.get("name", ""),
                "--url", target.get("url", ""),
                "--country", target.get("country", "") or "",
                "--timezone", target.get("timezone", "") or "",
                "--group", current_grp_name,
                "--groups-json", json.dumps(all_groups)
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    val = json.loads(res.stdout.strip())
                    if val.get("action") == "delete":
                        items.pop(idx)
                        self.show_feedback("Radio supprimée")
                        self.update_view()
                        return
                    target["name"] = val["name"]
                    target["url"] = val["url"]
                    target["country"] = val.get("country")
                    target["timezone"] = val.get("timezone")

                    new_grp_name = val.get("group")
                    if self.current_group_idx is not None and new_grp_name and new_grp_name != current_grp_name:
                        target_grp = next((g for g in self.data if g["name"] == new_grp_name), None)
                        if target_grp:
                            items.pop(idx)
                            target_grp.setdefault("stations", []).append(target)
                            self.show_feedback(f"Radio déplacée vers « {new_grp_name} »")
                    self.update_view(select_idx=idx if self.current_group_idx is not None else None)
            except Exception as e:
                pass

    def on_delete_clicked(self, widget):
        indices = self.get_selected_indices()
        if not indices:
            return

        items = self.get_current_list()

        if len(indices) == 1:
            target = items[indices[0]]
            name = target["name"]
            if self.is_item_separator(target):
                clean_title = name.strip("-").strip() if name.startswith("---") else name
                sep_desc = f"l'intertitre « {clean_title} »" if clean_title else "ce séparateur"
                msg = f"Voulez-vous supprimer {sep_desc} ?"
            elif self.current_group_idx is None:
                sub_count = sum(1 for g in self.data if g.get("name", "").startswith(name + "/"))
                if sub_count > 0:
                    msg = f"Voulez-vous vraiment supprimer le groupe « {name} », ses {sub_count} sous-groupe(s) et tout leur contenu ?"
                else:
                    msg = f"Voulez-vous vraiment supprimer le groupe « {name} » et tout son contenu ?"
            else:
                msg = f"Voulez-vous vraiment supprimer la radio « {name} » ?"
        else:
            nb = len(indices)
            if self.current_group_idx is None:
                msg = f"Voulez-vous vraiment supprimer ces {nb} groupes et tout leur contenu ?"
            else:
                msg = f"Voulez-vous vraiment supprimer ces {nb} éléments ?"

        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            message_format=msg,
        )
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            if self.current_group_idx is None:
                del_names = [items[i]["name"] for i in indices if i < len(items)]
                for i in reversed(indices):
                    if i < len(items):
                        items.pop(i)
                # Supprimer également tous les sous-groupes enfants rattachés
                self.data = [g for g in self.data if not any(g.get("name", "").startswith(dn + "/") for dn in del_names)]
            else:
                for i in reversed(indices):
                    if i < len(items):
                        items.pop(i)
            next_idx = min(indices[0], max(0, len(items) - 1)) if items else None
            self.update_view(select_idx=next_idx)

    def on_cancel_clicked(self, widget):
        self.saved = False
        self.destroy()

    def on_save_clicked(self, widget):
        self.saved = True
        self.destroy()



    # -------------------------------------------------------------------------
    # Vérification de santé des flux et réparation des liens morts
    # -------------------------------------------------------------------------

    def on_filter_broken_toggled(self, widget):
        self.filter_broken_only = widget.get_active()
        self.update_view()

    def on_apply_redirects_clicked(self, widget):
        count = 0
        for g in self.data:
            for s in g.get("stations", []):
                u = s.get("url", "")
                if u in self.audit_results and self.audit_results[u].get("redirect"):
                    s["url"] = self.audit_results[u]["redirect"]
                    count += 1
        self.btn_apply_redirects.hide()
        self.show_feedback(f"{count} flux redirigés mis à jour vers leur adresse directe !")
        self.update_view()

    def on_check_streams_clicked(self, widget):
        # 1. Rassembler les stations à vérifier
        stations_to_check = []
        if self.current_group_idx is not None:
            grp = self.data[self.current_group_idx]
            for s in grp.get("stations", []):
                if not self.is_item_separator(s) and s.get("url"):
                    stations_to_check.append(s)
        else:
            for g in self.data:
                for s in g.get("stations", []):
                    if not self.is_item_separator(s) and s.get("url"):
                        stations_to_check.append(s)

        if not stations_to_check:
            self.show_feedback("Aucune radio à vérifier.")
            return

        total = len(stations_to_check)

        # Dialogue de progression modal
        dialog = Gtk.Dialog(
            title="Vérification de vos radios",
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            buttons=("Arrêter", Gtk.ResponseType.CANCEL)
        )
        dialog.set_default_size(440, 140)
        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(14)

        lbl = Gtk.Label(label="<b>Vérification en direct de vos flux de radios...</b>")
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        box.add(lbl)

        pbar = Gtk.ProgressBar()
        box.add(pbar)

        lbl_status = Gtk.Label(label=f"0 / {total} radios vérifiées...")
        lbl_status.set_halign(Gtk.Align.START)
        box.add(lbl_status)
        dialog.show_all()

        cancel_event = threading.Event()

        def run_checks():
            done = 0
            for s in stations_to_check:
                if cancel_event.is_set():
                    break
                url = s.get("url", "")
                ok, msg, redir = check_stream_url(url, timeout=3.0)
                if ok is True:
                    status = "redirect" if redir else "online"
                elif ok == "GEO":
                    status = "geo"
                else:
                    status = "offline"

                self.audit_results[url] = {
                    "status": status,
                    "msg": msg,
                    "redirect": redir,
                }
                done += 1

                fraction = done / float(total)
                text = f"{done} / {total} radios vérifiées : {s.get('name', '')[:25]}"
                GLib.idle_add(pbar.set_fraction, fraction)
                GLib.idle_add(lbl_status.set_text, text)

            GLib.idle_add(on_finished)

        def on_finished():
            dialog.destroy()
            nb_online = sum(1 for r in self.audit_results.values() if r["status"] == "online")
            nb_dead = sum(1 for r in self.audit_results.values() if r["status"] == "offline")
            nb_redir = sum(1 for r in self.audit_results.values() if r["status"] == "redirect")

            self.show_feedback(f"Audit terminé : {nb_online} en ligne · {nb_dead} liens morts · {nb_redir} redirigés")

            if nb_dead > 0:
                self.chk_broken_only.show()
                self.chk_broken_only.set_label(f"Liens morts uniquement ({nb_dead})" )
                self.chk_broken_only.set_active(True)
            else:
                self.chk_broken_only.hide()
                self.chk_broken_only.set_active(False)

            if nb_redir > 0:
                self.btn_apply_redirects.show()
                if hasattr(self.btn_apply_redirects, "_label_widget"):
                    self.btn_apply_redirects._label_widget.set_text(f"Appliquer redirections ({nb_redir})")
                else:
                    self.btn_apply_redirects.set_label(f"Appliquer redirections ({nb_redir})")
            else:
                self.btn_apply_redirects.hide()

            self.update_view()

        thread = threading.Thread(target=run_checks, daemon=True)
        thread.start()

        res = dialog.run()
        if res == Gtk.ResponseType.CANCEL:
            cancel_event.set()
        dialog.destroy()

    def on_repair_stream_clicked(self, widget):
        idx = self.get_selected_index()
        if idx is None:
            self.show_feedback("Veuillez sélectionner une radio à réparer.")
            return

        items = self.get_current_list()
        st = items[idx]
        if self.is_item_separator(st):
            self.show_feedback("Cet élément est un séparateur.")
            return

        st_name = st.get("name", "")
        old_url = st.get("url", "")

        # Dialogue de recherche
        dialog = Gtk.Dialog(
            title=f"Réparation de « {st_name} »",
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            buttons=("Annuler", Gtk.ResponseType.CANCEL, "Remplacer l'URL", Gtk.ResponseType.OK)
        )
        dialog.set_default_size(520, 260)
        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(12)

        lbl_info = Gtk.Label(label=f"<b>Ancienne URL :</b> <small>{old_url}</small>")
        lbl_info.set_use_markup(True)
        lbl_info.set_halign(Gtk.Align.START)
        lbl_info.set_ellipsize(Pango.EllipsizeMode.END)
        box.add(lbl_info)

        lbl_searching = Gtk.Label(label="Recherche d'un flux en direct sur Radio-Browser...")
        box.add(lbl_searching)

        radio_group = None
        cands_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(140)
        scrolled.add(cands_box)
        box.add(scrolled)

        cands = search_radio_browser_replacement(st_name)
        lbl_searching.hide()

        selected_candidate = [None]

        if cands:
            lbl_title = Gtk.Label(label=f"<b>{len(cands)} flux actif{'s' if len(cands) > 1 else ''} trouvé{'s' if len(cands) > 1 else ''} :</b>")
            lbl_title.set_use_markup(True)
            lbl_title.set_halign(Gtk.Align.START)
            cands_box.add(lbl_title)

            for i, c in enumerate(cands):
                label_txt = f"{c['name']} [{c.get('country','')}] · {c.get('bitrate', 0)} kbps\n<small>{c['url']}</small>"
                rb = Gtk.RadioButton.new_with_label_from_widget(radio_group, label_txt)
                rb.get_child().set_use_markup(True)
                if radio_group is None:
                    radio_group = rb
                    selected_candidate[0] = c['url']
                rb.connect("toggled", lambda w, u=c['url']: selected_candidate.__setitem__(0, u))
                cands_box.add(rb)
        else:
            lbl_none = Gtk.Label(label="Aucun flux alternatif actif n'a pu être trouvé automatiquement.\nVous pouvez modifier l'URL manuellement avec le bouton Modifier.")
            lbl_none.set_use_markup(True)
            cands_box.add(lbl_none)
            dialog.set_response_sensitive(Gtk.ResponseType.OK, False)

        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK and selected_candidate[0]:
            new_u = selected_candidate[0]
            st["url"] = new_u
            self.audit_results[new_u] = {"status": "online", "msg": "En direct (réparé)", "redirect": None}
            self.show_feedback(f"Lien réparé avec succès pour « {st_name} » !")
            self.update_view(select_idx=idx)

        dialog.destroy()

    def write_csv_export(self, filepath):
        import csv
        count = 0
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            f.write("# Export des radios TiMonde\n")
            writer.writerow(["Groupe", "Nom", "URL", "Pays"])
            for grp in self.data:
                if self.is_item_separator(grp):
                    continue
                grp_name = grp.get("name", "")
                for st in grp.get("stations", []):
                    if self.is_item_separator(st):
                        continue
                    st_name = st.get("name", "")
                    st_url = st.get("url", "")
                    st_country = st.get("country", "") or ""
                    if st_name and st_url:
                        writer.writerow([grp_name, st_name, st_url, st_country])
                        count += 1
        return count

    def on_export_csv_clicked(self, widget=None):
        dialog = Gtk.FileChooserDialog(
            title=_("Export my stations to CSV"),
            parent=self,
            action=Gtk.FileChooserAction.SAVE,
            buttons=(_("Cancel"), Gtk.ResponseType.CANCEL, _("Export"), Gtk.ResponseType.OK),
        )
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_current_name("radios_timonde.csv")
        dialog.set_do_overwrite_confirmation(True)

        filter_csv = Gtk.FileFilter()
        filter_csv.set_name(_("CSV files (*.csv)"))
        filter_csv.add_pattern("*.csv")
        dialog.add_filter(filter_csv)

        filter_all = Gtk.FileFilter()
        filter_all.set_name(_("All files (*.*)"))
        filter_all.add_pattern("*")
        dialog.add_filter(filter_all)

        res = dialog.run()
        chosen_path = dialog.get_filename()
        dialog.destroy()

        if res == Gtk.ResponseType.OK and chosen_path:
            if not chosen_path.lower().endswith(".csv"):
                chosen_path += ".csv"
            try:
                count = self.write_csv_export(chosen_path)
                self.show_feedback(f"{count} radio(s) exportée(s) dans {os.path.basename(chosen_path)}")
                msg_diag = Gtk.MessageDialog(
                    parent=self,
                    flags=Gtk.DialogFlags.MODAL,
                    type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    message_format=f"{_('Export successful!')}\n\n{count} {_('station(s) saved to:')}\n{chosen_path}",
                )
                msg_diag.run()
                msg_diag.destroy()
            except Exception as e:
                err_diag = Gtk.MessageDialog(
                    parent=self,
                    flags=Gtk.DialogFlags.MODAL,
                    type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    message_format=f"{_('Error during CSV export:')}\n{e}",
                )
                err_diag.run()
                err_diag.destroy()

def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            sys.exit(1)
        data = json.loads(raw_input)
    except Exception as e:
        sys.stderr.write(f"Erreur lecture stdin : {e}\n")
        sys.exit(1)

    auto_check = "--check" in sys.argv or "--audit" in sys.argv
    auto_export = "--export" in sys.argv or "--export-csv" in sys.argv
    win = ReorderWindow(data, auto_check=auto_check)
    win.show_all()
    win.btn_back.hide()
    win.btn_add_sep.show()
    win.btn_add_station.hide()
    if auto_check:
        GLib.idle_add(win.on_check_streams_clicked, None)
    if auto_export:
        GLib.idle_add(win.on_export_csv_clicked, None)
    Gtk.main()

    if win.saved:
        json.dump(win.data, sys.stdout, ensure_ascii=False)
        sys.stdout.flush()
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
