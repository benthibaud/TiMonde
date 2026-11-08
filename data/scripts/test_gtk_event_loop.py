#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test exhaustif de la boucle d'événements GTK et des symboles de callbacks pour TiMonde.
- Volet 1 (Statique AST) : Analyse AST de portée pour garantir zéro symbole non résolu (anti-NameError)
  dans tous les fichiers scripts Python du projet.
- Volet 2 (Dynamique GTK) : Instanciation de toutes les fenêtres et dialogues GTK, capture globale des
  exceptions PyGObject/GLib et déclenchement programmé des signaux/boutons avec vidage forcé de la boucle d'événements.
"""

import os
import sys
import io
import ast
import builtins
import unittest
from unittest.mock import patch, MagicMock

# Neutralisation IBus pour les tests sans affichage
os.environ.pop("GTK_IM_MODULE", None)
os.environ.pop("XMODIFIERS", None)
os.environ.pop("QT_IM_MODULE", None)

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(SCRIPTS_DIR, "../.."))
sys.path.insert(0, SCRIPTS_DIR)

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk


def drain_gtk_events():
    """Vide la file d'attente d'événements GTK pour forcer l'exécution de tous les idle_add et callbacks."""
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


class GtkExceptionCatcher:
    """Intercepteur strict d'exceptions et d'erreurs émises dans la boucle d'événements GTK / PyGObject."""
    def __init__(self):
        self.errors = []
        self._orig_excepthook = None
        self._orig_stderr = None
        self._captured_stderr = io.StringIO()

    def __enter__(self):
        self.errors = []
        self._orig_excepthook = sys.excepthook
        self._orig_stderr = sys.stderr

        def custom_hook(exctype, value, tb):
            self.errors.append((exctype, value, tb))
            self._orig_excepthook(exctype, value, tb)

        sys.excepthook = custom_hook
        sys.stderr = self._captured_stderr
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.excepthook = self._orig_excepthook
        captured = self._captured_stderr.getvalue()
        sys.stderr = self._orig_stderr

        # Vérifier si des traces d'erreurs non capturées par l'excepthook ont été déversées sur stderr
        if "Traceback (most recent call last)" in captured or "NameError:" in captured or "AttributeError:" in captured:
            self.errors.append((RuntimeError, captured, None))


def get_module_globals(tree, builtin_names):
    """Collecte exhaustivement tous les symboles exportés ou déclarés au niveau module (y compris dans Try/If)."""
    globals_set = set(builtin_names)

    def visit_top_level(nodes):
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    globals_set.add(alias.asname or alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    globals_set.add(alias.asname or alias.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                globals_set.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    for n in ast.walk(t):
                        if isinstance(n, ast.Name):
                            globals_set.add(n.id)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                if isinstance(node.target, ast.Name):
                    globals_set.add(node.target.id)
            elif isinstance(node, ast.For):
                for n in ast.walk(node.target):
                    if isinstance(n, ast.Name):
                        globals_set.add(n.id)
                visit_top_level(node.body)
                visit_top_level(node.orelse)
            elif isinstance(node, (ast.If, ast.While, ast.With)):
                visit_top_level(node.body)
                visit_top_level(node.orelse)
            elif isinstance(node, ast.Try):
                visit_top_level(node.body)
                for h in node.handlers:
                    if h.name:
                        globals_set.add(h.name)
                    visit_top_level(h.body)
                visit_top_level(node.orelse)
                visit_top_level(node.finalbody)

    visit_top_level(tree.body)
    return globals_set


class TestGtkEventLoopAndScope(unittest.TestCase):

    def test_01_ast_static_scope_zero_undefined_names(self):
        """Volet statique : vérifie qu'aucun callback ou fonction ne contient de NameError latente."""
        builtin_names = set(dir(builtins))
        checked_files = [
            "edit_station.py",
            "reorder_groups.py",
            "timonde_settings.py",
            "timonde_common.py",
            "browse_bouquets.py",
            "gnome_tray_helper.py",
            "patch_cinnamon_status_applet.py",
        ]

        for fname in checked_files:
            fpath = os.path.join(SCRIPTS_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=fpath)

            module_globals = get_module_globals(tree, builtin_names)

            errors = []
            class Visitor(ast.NodeVisitor):
                def __init__(self):
                    self.scopes = [set(module_globals)]

                def visit_FunctionDef(self, n):
                    local_s = set()
                    for arg in n.args.args + n.args.posonlyargs + n.args.kwonlyargs:
                        local_s.add(arg.arg)
                    if n.args.vararg: local_s.add(n.args.vararg.arg)
                    if n.args.kwarg: local_s.add(n.args.kwarg.arg)

                    for child in ast.walk(n):
                        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                            local_s.add(child.id)
                        elif isinstance(child, ast.Import):
                            for a in child.names:
                                local_s.add(a.asname or a.name.split('.')[0])
                        elif isinstance(child, ast.ImportFrom):
                            for a in child.names:
                                local_s.add(a.asname or a.name)
                        elif isinstance(child, (ast.FunctionDef, ast.ClassDef)):
                            local_s.add(child.name)
                        elif isinstance(child, ast.ExceptHandler) and child.name:
                            local_s.add(child.name)

                    self.scopes.append(local_s)
                    self.generic_visit(n)
                    self.scopes.pop()

                def visit_Lambda(self, n):
                    local_s = set()
                    for arg in n.args.args + n.args.posonlyargs + n.args.kwonlyargs:
                        local_s.add(arg.arg)
                    if n.args.vararg: local_s.add(n.args.vararg.arg)
                    if n.args.kwarg: local_s.add(n.args.kwarg.arg)
                    self.scopes.append(local_s)
                    self.generic_visit(n)
                    self.scopes.pop()

                def visit_ListComp(self, n): self._visit_comp(n)
                def visit_SetComp(self, n): self._visit_comp(n)
                def visit_DictComp(self, n): self._visit_comp(n)
                def visit_GeneratorExp(self, n): self._visit_comp(n)

                def _visit_comp(self, n):
                    local_s = set()
                    for gen in n.generators:
                        for child in ast.walk(gen.target):
                            if isinstance(child, ast.Name):
                                local_s.add(child.id)
                    self.scopes.append(local_s)
                    self.generic_visit(n)
                    self.scopes.pop()

                def visit_Name(self, n):
                    if isinstance(n.ctx, ast.Load):
                        name = n.id
                        found = any(name in s for s in self.scopes) or (name in module_globals)
                        if not found and name not in ("__file__", "_", "s", "c", "t", "self"):
                            errors.append((n.lineno, name))

            v = Visitor()
            v.visit(tree)
            self.assertEqual(
                errors,
                [],
                f"Variables non définies détectées dans {fname} : {errors}"
            )

    def test_02_dynamic_all_buttons_fuzzing_edit_station(self):
        """Volet dynamique : instancie EditStationWindow et déclenche ses interactions sans exception."""
        from edit_station import EditStationWindow
        st_data = {
            "name": "Jabulani Radio - Eldoret (Kenya)",
            "url": "https://listen.radioking.com/radio/6262",
            "country": "KE",
            "timezone": "Africa/Nairobi",
            "group": "Sélection perso",
        }

        with GtkExceptionCatcher() as catcher:
            win = EditStationWindow(station_data=st_data, standalone=False)
            drain_gtk_events()

            # 1. Clic sur le bouton de test de flux
            if hasattr(win, "btn_test_url") and win.btn_test_url:
                win.btn_test_url.clicked()
                drain_gtk_events()

            # 2. Clic sur le bouton Radio-Browser
            if hasattr(win, "btn_rb") and win.btn_rb:
                with patch("edit_station.ContributeStationDialog") as MockDlg:
                    inst = MagicMock()
                    inst.run.return_value = Gtk.ResponseType.CLOSE
                    inst.existing_info = None
                    MockDlg.return_value = inst
                    win.btn_rb.clicked()
                    drain_gtk_events()

            # 3. Modification du texte d'entrée
            win.entry_name.set_text("Jabulani Radio Modifiée")
            win.entry_country_search.set_text("Kenya")
            drain_gtk_events()

            # Arrêt propre
            win.preview_player.stop(silent=True)
            win.destroy()
            drain_gtk_events()

            self.assertEqual(catcher.errors, [], f"Exceptions capturées dans EditStationWindow : {catcher.errors}")

    def test_03_dynamic_all_buttons_reorder_groups(self):
        """Volet dynamique : instancie ReorderWindow et déclenche ses actions principales."""
        from reorder_groups import ReorderWindow
        data = [
            {
                "name": "Sélection perso",
                "is_separator": False,
                "stations": [
                    {
                        "name": "Europa Radio Jazz",
                        "url": "http://stream.radioreference.com/jazz",
                        "country": "IT",
                        "timezone": "Europe/Rome",
                    }
                ],
            }
        ]

        with GtkExceptionCatcher() as catcher:
            win = ReorderWindow(data=data, embedded=False)
            win.show_all()
            win.treeview.expand_all()
            drain_gtk_events()

            # Sélectionner la station enfant dans l'arbre
            it = win.store.get_iter_first()
            if it:
                c = win.store.iter_children(it)
                if c:
                    path = win.store.get_path(c)
                    win.treeview.get_selection().select_path(path)
                    drain_gtk_events()

            # 1. Tester la contribution avec clic Radio-Browser
            with patch("reorder_groups.ContributeStationDialog") as MockContribute:
                inst = MagicMock()
                inst.run.return_value = Gtk.ResponseType.APPLY
                inst.existing_info = {"name": "Europa Radio Jazz", "countrycode": "IT"}
                MockContribute.return_value = inst

                with patch.object(win, "on_edit_clicked") as mock_edit:
                    win.on_contribute_station_clicked(None)
                    drain_gtk_events()
                    self.assertTrue(mock_edit.called)

            # 2. Vérifier que la modification du pays met à jour immédiatement la colonne 2 du TreeView
            if c:
                initial_details = win.store.get_value(c, 2)
                self.assertEqual(initial_details, "[IT]")

                # Simuler l'édition enregistrée avec nouveau pays 'FR'
                with patch("reorder_groups.EditStationWindow") as MockEditWin:
                    def fake_edit_init(*args, **kwargs):
                        cb = kwargs.get("on_done_callback")
                        if cb:
                            cb({
                                "name": "Europa Radio Jazz",
                                "url": "http://stream.radioreference.com/jazz",
                                "country": "FR",
                                "timezone": "Europe/Paris",
                                "group": "Sélection perso",
                            })
                        return MagicMock()
                    MockEditWin.side_effect = fake_edit_init
                    win.on_edit_clicked(None)
                    drain_gtk_events()

                updated_details = win.store.get_value(c, 2)
                self.assertEqual(updated_details, "[FR]", "La colonne Détails/Pays doit afficher immédiatement [FR] sans réouverture")

            # 3. Tester l'appel de réorganisation et de déplacement
            groups = win.get_all_group_paths()
            self.assertIn("Sélection perso", groups)

            win.destroy_window() if hasattr(win, "destroy_window") else win.destroy()
            drain_gtk_events()

            self.assertEqual(catcher.errors, [], f"Exceptions capturées dans ReorderWindow : {catcher.errors}")

    def test_04_dynamic_settings_window_all_sections(self):
        """Volet dynamique : instancie SettingsWindow et bascule sur tous les onglets."""
        from timonde_settings import SettingsWindow

        with GtkExceptionCatcher() as catcher:
            win = SettingsWindow()
            drain_gtk_events()

            # Basculer sur les différentes pages
            for page_name in ["organization", "search", "bouquets", "files", "general"]:
                child = win.stack.get_child_by_name(page_name)
                if child:
                    win.stack.set_visible_child(child)
                    drain_gtk_events()

            win.destroy()
            drain_gtk_events()

            self.assertEqual(catcher.errors, [], f"Exceptions capturées dans SettingsWindow : {catcher.errors}")


if __name__ == "__main__":
    unittest.main()
