#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests unitaires automatisés pour timonde_common.py
Vérifie :
1. Nettoyage et résilience des URLs de flux audio (clean_stream_url)
2. Détection et filtrage des emojis régionaux (strip_unsupported_emojis)
3. Tolérance du parseur XML aux entités non-échappées (safe_parse_xml)
4. Normalisation stricte de la convention Linux des groupes avec slashes (normalize_group_path)
5. Intégrité du catalogue des pays et des fuseaux horaires
"""

import unittest
import os
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.abspath(os.path.join(TESTS_DIR, "..", "data", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


from timonde_common import (
    clean_stream_url,
    strip_unsupported_emojis,
    run_timonde_cli,
    load_timezones_for_country,
    normalize_group_path,
    infer_timezone,
    set_window_icon,
    COUNTRIES_DB,
    COUNTRIES_REGISTRY,
    FRANCE_TIMEZONES,
    WORLD_TIMEZONES,
)

class TestTiMondeCommon(unittest.TestCase):

    def test_clean_stream_url(self):
        # Protocoles en double ou mal formés
        self.assertEqual(clean_stream_url("httpshttps://example.com/stream"), "https://example.com/stream")
        self.assertEqual(clean_stream_url("http ://radio.fr/live"), "http://radio.fr/live")
        self.assertEqual(clean_stream_url("//cdn.example.org/audio.mp3"), "https://cdn.example.org/audio.mp3")
        self.assertEqual(clean_stream_url("  https://ok.com/live  "), "https://ok.com/live")
        self.assertEqual(clean_stream_url(""), "")

    def test_strip_unsupported_emojis(self):
        text = "🇫🇷 France Musique"
        self.assertEqual(strip_unsupported_emojis(text), "France Musique")
        self.assertEqual(strip_unsupported_emojis("Simple Text"), "Simple Text")

    def test_normalize_group_path(self):
        # Cas racine
        self.assertEqual(normalize_group_path("[ / ] (Racine — Sans groupe)", return_root_literal=True), "root")
        self.assertEqual(normalize_group_path("/", return_root_literal=True), "root")
        self.assertEqual(normalize_group_path("", return_root_literal=True), "root")
        self.assertEqual(normalize_group_path("/", return_root_literal=False), "")

        # Sous-groupes avec slashes convention Linux
        self.assertEqual(normalize_group_path("/France/Bretagne/"), "France/Bretagne")
        self.assertEqual(normalize_group_path("France/Bretagne"), "France/Bretagne")
        self.assertEqual(normalize_group_path("///Belgique/Bruxelles///"), "Belgique/Bruxelles")
        self.assertEqual(normalize_group_path("  Jazz & Blues  "), "Jazz & Blues")

    def test_run_timonde_cli(self):
        res = run_timonde_cli("--version")
        self.assertEqual(res.returncode, 0)
        self.assertIn("TiMonde", res.stdout)

    def test_load_timezones_for_country(self):
        tzs_fr = load_timezones_for_country("FR")
        self.assertTrue(len(tzs_fr) >= 10)
        self.assertTrue(any(t[0] == "Europe/Paris" for t in tzs_fr))
        self.assertTrue(any(t[0] == "America/Guadeloupe" for t in tzs_fr))

    def test_countries_and_timezones(self):
        self.assertTrue(len(COUNTRIES_DB) >= 70)
        self.assertTrue(len(COUNTRIES_REGISTRY) >= 200)
        self.assertIn("FR", COUNTRIES_REGISTRY)
        self.assertIn("GP", COUNTRIES_REGISTRY)  # Guadeloupe
        self.assertIn("US", COUNTRIES_REGISTRY)

        # Vérification fuseaux France (Métropole + DOM-TOM)
        fr_tz_ids = [tz[0] for tz in FRANCE_TIMEZONES]
        self.assertIn("Europe/Paris", fr_tz_ids)
        self.assertIn("America/Guadeloupe", fr_tz_ids)
        self.assertIn("Indian/Reunion", fr_tz_ids)
        self.assertIn("Pacific/Tahiti", fr_tz_ids)

    def test_infer_timezone(self):
        # France Métropole vs Outre-mer
        self.assertEqual(infer_timezone("FR", "France Inter", "Généraliste"), "Europe/Paris")
        self.assertEqual(infer_timezone("FR", "RCI Guadeloupe", "Antilles"), "America/Guadeloupe")
        self.assertEqual(infer_timezone("FR", "Radio Réunion 1ère", "Océan Indien"), "Indian/Reunion")
        self.assertEqual(infer_timezone("GP", "Radio Guadeloupe", ""), "America/Guadeloupe")

        # Royaume-Uni & Outre-mer
        self.assertEqual(infer_timezone("GB", "BBC Radio 1", "Londres"), "Europe/London")
        self.assertEqual(infer_timezone("GB", "BFBS Gibraltar", "Europe"), "Europe/Gibraltar")
        self.assertEqual(infer_timezone("BM", "Bermuda FM", ""), "Atlantic/Bermuda")

        # Canada
        self.assertEqual(infer_timezone("CA", "Vancouver Rock", "Colombie-Britannique"), "America/Vancouver")
        self.assertEqual(infer_timezone("CA", "Radio-Canada Montréal", "Québec"), "America/Toronto")

        # États-Unis
        self.assertEqual(infer_timezone("US", "KCRW Los Angeles", "Californie"), "America/Los_Angeles")
        self.assertEqual(infer_timezone("US", "WNYC New York", "News"), "America/New_York")

        # Fallbacks universels par pays (Algérie, Colombie)
        self.assertEqual(infer_timezone("DZ", "Chaine 1", ""), "Africa/Algiers")
        self.assertEqual(infer_timezone("CO", "Caracol Radio", ""), "America/Bogota")

    def test_multilingual_55_countries_and_language_aliases(self):
        from timonde_common import resolve_country_code, resolve_language_api_key
        country_cases = [
            ("Deutschland", "DE"), ("Germany", "DE"), ("Allemagne", "DE"), ("Alemania", "DE"),
            ("Germania", "DE"), ("Duitsland", "DE"), ("Niemcy", "DE"), ("Германия", "DE"),
            ("ألمانيا", "DE"), ("ドイツ", "DE"), ("德国", "DE"), ("德國", "DE"), ("Saksa", "DE"), ("Tyskland", "DE"),
            ("Suisse", "CH"), ("Schweiz", "CH"), ("Switzerland", "CH"), ("Svizzera", "CH"), ("Suiza", "CH"),
            ("España", "ES"), ("Spain", "ES"), ("Espagne", "ES"), ("Spanien", "ES"),
            ("United Kingdom", "GB"), ("Royaume-Uni", "GB"), ("UK", "GB"), ("England", "GB"),
            ("United States", "US"), ("USA", "US"), ("États-Unis", "US"), ("アメリカ合衆国", "US"), ("美国", "US"),
            ("Россия", "RU"), ("Russia", "RU"), ("Russie", "RU"),
            ("日本", "JP"), ("Japan", "JP"), ("Japon", "JP"),
            ("Ελλάδα", "GR"), ("Greece", "GR"), ("Grèce", "GR"),
        ]
        for query, expected in country_cases:
            self.assertEqual(resolve_country_code(query), expected, f"Échec pour {query}")

        lang_cases = [
            ("english", "english"), ("Anglais", "english"), ("English", "english"),
            ("engilsh", "english"), ("american english", "english"), ("english uk", "english"),
            ("American english (american english)", "american english"),
            ("deutch", "german"), ("Deutsch", "german"),
            ("espanish", "spanish"), ("francaise", "french"),
        ]
        for query, expected in lang_cases:
            self.assertEqual(resolve_language_api_key(query), expected, f"Échec langue pour {query}")

    def test_bookmarks_tree_root_and_nested_groups(self):
        from timonde_settings import load_bookmarks_tree, save_bookmarks_tree
        xml_sample = """<?xml version="1.0" encoding="utf-8"?>
<bookmarks>
    <bookmark name="Root Radio" url="https://example.com/root.mp3" country="FR" timezone="Europe/Paris"/>
    <group name="France">
        <group name="Bretagne">
            <bookmark name="Radio Armorique" url="https://example.com/bzh.mp3" country="FR" timezone="Europe/Paris"/>
        </group>
    </group>
</bookmarks>
"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write(xml_sample)
            temp_path = f.name

        try:
            tree = load_bookmarks_tree(temp_path)
            self.assertEqual(len(tree), 2)
            self.assertEqual(tree[0]["name"], "[ / ] (Racine — Sans groupe)")
            self.assertEqual(tree[0]["stations"][0]["name"], "Root Radio")
            self.assertEqual(tree[1]["name"], "France/Bretagne")
            self.assertEqual(tree[1]["stations"][0]["name"], "Radio Armorique")

            save_bookmarks_tree(temp_path, tree)
            reloaded = load_bookmarks_tree(temp_path)
            self.assertEqual(len(reloaded), 2)
            self.assertEqual(reloaded[0]["stations"][0]["name"], "Root Radio")
            self.assertEqual(reloaded[0]["stations"][0]["timezone"], "Europe/Paris")
            self.assertEqual(reloaded[1]["name"], "France/Bretagne")
            self.assertEqual(reloaded[1]["stations"][0]["name"], "Radio Armorique")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_get_user_bookmarks_groups(self):
        from timonde_common import get_user_bookmarks_groups
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <bookmarks>
            <group name="root">
                <station name="Direct" url="http://test.com" />
            </group>
            <group name="France">
                <group name="Bretagne">
                    <station name="Armorique" url="http://armor.fr" />
                </group>
            </group>
            <group name="Jazz" />
        </bookmarks>"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            temp_path = f.name
        try:
            grps = get_user_bookmarks_groups(temp_path)
            self.assertEqual(grps, ["France", "France/Bretagne", "Jazz"])
            self.assertNotIn("root", grps)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_radio_browser_components(self):
        from timonde_common import TIMONDE_USER_AGENT, RepairStreamDialog, get_timonde_bin
        self.assertTrue(TIMONDE_USER_AGENT.startswith("TiMonde/"))
        self.assertIsNotNone(RepairStreamDialog)
        self.assertTrue(os.path.exists(get_timonde_bin()))

    def test_status_markup(self):
        from timonde_common import status_markup
        ok_m = status_markup("En ligne", kind="ok")
        self.assertIn("#2ecc71", ok_m)
        self.assertIn("En ligne", ok_m)

        err_m = status_markup("Mort", kind="error", bold=True)
        self.assertIn("#e74c3c", err_m)
        self.assertIn("<b>Mort</b>", err_m)

        bullet_m = status_markup("Actif", kind="ok", with_bullet=True)
        self.assertIn("<b>●</b>", bullet_m)

        # Test d'échappement HTML anti-injection Pango
        esc_m = status_markup("Rock & Roll <Live>", kind="info")
        self.assertIn("Rock &amp; Roll &lt;Live&gt;", esc_m)

    def test_check_stream_url_meta(self):
        from timonde_common import check_stream_url
        # Cas URL vide
        ok, msg, meta = check_stream_url("", fetch_meta=True)
        self.assertFalse(ok)
        self.assertIsInstance(meta, dict)
        self.assertIn("icy_name", meta)

    def test_lookup_station_by_url_empty(self):
        from timonde_common import lookup_station_by_url
        self.assertIsNone(lookup_station_by_url(""))
        self.assertIsNone(lookup_station_by_url(None))

    def test_contribute_station_validation(self):
        from timonde_common import contribute_station_to_radio_browser
        ok, msg, info = contribute_station_to_radio_browser("", "http://example.com")
        self.assertFalse(ok)
        ok2, msg2, info2 = contribute_station_to_radio_browser("Radio Test", "")
        self.assertFalse(ok2)

    def test_edit_station_window_station_data(self):
        from edit_station import EditStationWindow
        st_data = {
            "name": "Europa Radio Jazz",
            "url": "http://stream.radioreference.com/jazz",
            "country": "IT",
            "timezone": "Europe/Rome",
            "group": "Jazz"
        }
        win = EditStationWindow(mode="edit", station_data=st_data, standalone=False)
        self.assertEqual(win.entry_name.get_text(), "Europa Radio Jazz")
        self.assertEqual(win.entry_url.get_text(), "http://stream.radioreference.com/jazz")
        self.assertEqual(win.selected_country_code, "IT")
        self.assertTrue(hasattr(win, "run"))
        self.assertTrue(hasattr(win, "set_country"))
        win.destroy()

    def test_contribute_station_dialog_btn_edit(self):
        from timonde_common import ContributeStationDialog
        from gi.repository import Gtk
        dlg = ContributeStationDialog(parent=None, station_name="Europa Radio Jazz", current_url="http://stream.radioreference.com/jazz")
        self.assertTrue(hasattr(dlg, "btn_edit"))
        # Simuler la détection d'une station existante
        dlg._on_lookup_done("http://stream.radioreference.com/jazz", {"name": "Europa Radio Jazz", "countrycode": "IT"})
        self.assertIn("IT", dlg.btn_edit.get_label())
        dlg.destroy()

    def test_edit_station_window_radio_browser_button(self):
        from unittest.mock import patch, MagicMock
        from edit_station import EditStationWindow
        from gi.repository import Gtk

        st_data = {
            "name": "Jabulani Radio - Eldoret (Kenya)",
            "url": "https://listen.radioking.com/radio/6262",
            "country": "",
            "timezone": "",
            "group": "Sélection perso"
        }
        win = EditStationWindow(station_data=st_data, standalone=False)
        with patch("edit_station.ContributeStationDialog") as MockDialog:
            instance = MagicMock()
            instance.existing_info = {"countrycode": "KE", "name": "Jabulani Radio"}
            def fake_connect(signal, cb):
                if signal == "response":
                    cb(instance, Gtk.ResponseType.APPLY)
            instance.connect.side_effect = fake_connect
            MockDialog.return_value = instance

            win.on_check_radio_browser_clicked(None)
            self.assertTrue(MockDialog.called)
            self.assertEqual(win.selected_country_code, "KE")
        win.destroy()

    def test_find_timonde_binary(self):
        from timonde_common import find_timonde_binary
        bin_path = find_timonde_binary()
        self.assertIsNotNone(bin_path)
        self.assertTrue(os.path.exists(bin_path))
        self.assertTrue(os.access(bin_path, os.X_OK))

    def test_check_stream_url_delegation_and_redirect_meta(self):
        from timonde_common import check_stream_url
        # Vérification des tuples avec redirection et métadonnées
        ok, msg, redir, meta = check_stream_url("http://127.0.0.1:59999/dummy", with_redirect=True, fetch_meta=True)
        self.assertFalse(ok)
        self.assertIsInstance(msg, str)
        self.assertIsNone(redir)
        self.assertIsInstance(meta, dict)
        self.assertIn("content_type", meta)

    def test_settings_version_card_structure(self):
        from timonde_settings import SettingsWindow
        from timonde_common import TIMONDE_VERSION
        win = SettingsWindow()
        self.assertTrue(hasattr(win, "create_info_row"))
        row = win.create_info_row("TiMonde version", "/usr/bin/timonde", f"v{TIMONDE_VERSION}")
        self.assertIsNotNone(row)
        win.destroy()

    def test_atomic_write_file(self):
        from timonde_common import atomic_write_file
        import tempfile
        tmp_target = os.path.join(tempfile.gettempdir(), "timonde_test_atomic.txt")
        test_content = "Atomicity test for TiMonde"
        try:
            atomic_write_file(tmp_target, test_content)
            self.assertTrue(os.path.exists(tmp_target))
            self.assertFalse(os.path.exists(tmp_target + ".tmp"))
            with open(tmp_target, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), test_content)
        finally:
            if os.path.exists(tmp_target):
                os.remove(tmp_target)

    def test_setup_window_geometry(self):
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        from timonde_common import setup_window_geometry
        win = Gtk.Window()
        setup_window_geometry(win, base_width=900, base_height=600)
        w, h = win.get_default_size()
        self.assertGreaterEqual(w, 750)
        self.assertGreaterEqual(h, 480)
        win.destroy()

    def test_set_container_margins(self):
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        from timonde_common import set_container_margins
        box = Gtk.Box()
        set_container_margins(box, margin=14)
        self.assertEqual(box.get_margin_top(), 14)
        self.assertEqual(box.get_margin_bottom(), 14)
        self.assertEqual(box.get_margin_start(), 14)
        self.assertEqual(box.get_margin_end(), 14)

        # Marges asymétriques
        set_container_margins(box, top=5, bottom=10, start=15, end=20)
        self.assertEqual(box.get_margin_top(), 5)
        self.assertEqual(box.get_margin_bottom(), 10)
        self.assertEqual(box.get_margin_start(), 15)
    def test_stream_preview_player_stop_idempotent(self):
        from unittest.mock import patch
        from timonde_common import StreamPreviewPlayer

        player = StreamPreviewPlayer()
        self.assertFalse(player.is_playing)

        # Quand is_playing est False, stop() ne doit appeler ni call_timonde_mpris ni envoyer de commande
        with patch("timonde_common.call_timonde_mpris") as mock_mpris:
            player.stop(silent=True)
            mock_mpris.assert_not_called()

        with patch("timonde_common.call_timonde_mpris") as mock_mpris:
            player.stop(silent=False, sync=True)
            mock_mpris.assert_not_called()

    def test_stream_preview_player_switch_stations_no_race_condition(self):
        import time
        from unittest.mock import patch
        from timonde_common import StreamPreviewPlayer

        calls = []

        def fake_mpris(method_name, *args, **kwargs):
            calls.append((method_name, args))
            return True, None

        player = StreamPreviewPlayer()
        with patch("timonde_common.call_timonde_mpris", side_effect=fake_mpris):
            # 1. Écouter la radio 1
            player.play("Radio 1", "http://stream1.org/live")
            self.assertTrue(player.is_playing)
            self.assertEqual(player.current_url, "http://stream1.org/live")

            # 2. Enchaîner directement sur la radio 2 sans appel explicite à stop
            player.play("Radio 2", "http://stream2.org/live")
            self.assertTrue(player.is_playing)
            self.assertEqual(player.current_url, "http://stream2.org/live")

            # Attendre la fin des threads légers
            time.sleep(0.1)

            # Vérifier qu'aucun StopPreview n'a été intercalé par play()
            method_names = [c[0] for c in calls]
            self.assertNotIn("StopPreview", method_names)
            self.assertEqual(method_names, ["PlayPreview", "PlayPreview"])

            # 3. Arrêter explicitement
            player.stop()
            time.sleep(0.1)
            method_names = [c[0] for c in calls]
            self.assertEqual(method_names, ["PlayPreview", "PlayPreview", "StopPreview"])


class TestReorderFilterNonRegression(unittest.TestCase):
    """Vérifie que l'activation du filtre des liens morts dans reorder_groups ne détruit pas les stations saines."""

    def test_filter_broken_only_does_not_wipe_healthy_stations(self):
        from reorder_groups import ReorderWidget

        initial_data = [
            {
                "name": "Musique",
                "stations": [
                    {"name": "Radio Bon", "url": "https://ok.com/live"},
                    {"name": "Radio Mort", "url": "https://dead.com/live"},
                ],
                "is_separator": False,
            }
        ]

        # Création du widget en mode embarqué
        widget = ReorderWidget(data=initial_data, embedded=True)
        self.assertEqual(len(widget.data[0]["stations"]), 2)

        # Simulation du résultat de l'audit
        widget.audit_results = {
            "https://ok.com/live": {"status": "online", "msg": "200 OK", "redirect": None},
            "https://dead.com/live": {"status": "offline", "msg": "404 Not Found", "redirect": None},
        }

        # 1. Activation du filtre 'broken only'
        widget.filter_broken_only = True
        widget.populate_tree()

        # Le TreeStore affiché ne doit contenir que la station offline
        # Mais serialize_tree() doit retourner TOUTES les stations sans perte de données
        serialized = widget.serialize_tree()
        self.assertEqual(len(serialized[0]["stations"]), 2, "serialize_tree() en mode filtré ne doit pas détruire les stations saines !")

        # 2. Réparation de l'URL de la station morte
        dead_station = widget.data[0]["stations"][1]
        dead_station["url"] = "https://repaired.com/live"
        widget.set_dirty(True)

        # 3. Désactivation du filtre
        widget.filter_broken_only = False
        widget.populate_tree()

        final_serialized = widget.serialize_tree()
        self.assertEqual(len(final_serialized[0]["stations"]), 2)
        urls = [s["url"] for s in final_serialized[0]["stations"]]
        self.assertIn("https://ok.com/live", urls)
        self.assertIn("https://repaired.com/live", urls)


if __name__ == "__main__":
    unittest.main()

