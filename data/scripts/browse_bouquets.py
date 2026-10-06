#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Explorateur de bouquets de radios (TiMonde)
Permet de découvrir et d'importer en un clic les bouquets nationaux et régionaux :
- France, Belgique, Suisse, Canada, Royaume-Uni, etc.
- Sélection par langue pour les pays multilingues (Belgique, Suisse, Canada).
- Bouquets nationaux (grandes radios phares) et régionaux (expatriés, régions spécifiques).
- Prévention automatique des doublons avec les favoris existants.
"""

import sys
import json
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango

# Base de données intégrée des bouquets majeurs en haute qualité
BOUQUETS_DB = {
    "FR": {
        "name": "France 🇫🇷",
        "multilingual": False,
        "languages": [],
        "national": [
            ("France Inter", "https://stream.radiofrance.fr/franceinter/franceinter_hifi.aac", "Généraliste / Culture"),
            ("France Info", "https://stream.radiofrance.fr/franceinfo/franceinfo_hifi.aac", "Actualités en continu"),
            ("France Culture", "https://stream.radiofrance.fr/franceculture/franceculture_hifi.aac", "Culture & Débats"),
            ("France Musique", "https://stream.radiofrance.fr/francemusique/francemusique_hifi.aac", "Classique & Jazz"),
            ("FIP", "https://stream.radiofrance.fr/fip/fip_hifi.aac", "Musicale éclectique"),
            ("RTL", "https://icecast.rtl.fr/rtl-1-44-128?listen=web", "Généraliste"),
            ("RTL2", "https://icecast.rtl2.fr/rtl2-1-44-128?listen=web", "Pop Rock"),
            ("Fun Radio", "https://icecast.funradio.fr/fun-1-44-128?listen=web", "Dance / Électro"),
            ("Europe 1", "https://stream.europe1.fr/europe1.mp3", "Généraliste"),
            ("Europe 2", "https://europe2.stream.lanmedia.fr/europe2.mp3", "Pop / Hits"),
            ("NRJ", "https://scdn.nrjaudio.fm/audio1/fr/30001/mp3_128.mp3", "Hits"),
            ("Nostalgie", "https://scdn.nrjaudio.fm/audio1/fr/30601/mp3_128.mp3", "Légendes & 80s"),
            ("Chérie FM", "https://scdn.nrjaudio.fm/audio1/fr/30201/mp3_128.mp3", "Pop & Variété"),
            ("Rire et Chansons", "https://scdn.nrjaudio.fm/audio1/fr/30401/mp3_128.mp3", "Humour & Rock"),
            ("Skyrock", "https://icecast.skyrock.net/s/natio_mp3_128k", "Rap & R'n'B"),
            ("RMC", "https://audio.bfmtv.com/rmcradio_128.mp3", "Info & Sport"),
            ("BFM Radio", "https://audio.bfmtv.com/bfmradio_128.mp3", "Économie & Info"),
            ("BFM Business", "https://audio.bfmtv.com/bfmbusiness_128.mp3", "Économie"),
            ("Radio Classique", "https://radioclassique.ice.infomaniak.ch/radioclassique-high.mp3", "Classique & Info"),
            ("M Radio", "https://mradio.ice.infomaniak.ch/mradio-mp3-128.mp3", "Chanson française"),
            ("Latina", "https://start-latina.ice.infomaniak.ch/start-latina-high.mp3", "Musique latine"),
            ("Radio Nova", "https://radionova.ice.infomaniak.ch/radionova-256.mp3", "Musiques actuelles"),
            ("TSF Jazz", "https://tsfjazz.ice.infomaniak.ch/tsfjazz-high.mp3", "Jazz"),
            ("Radio FG", "https://radiofg.impek.com/fg", "Électro & House"),
            ("OUI FM", "https://ouifm.ice.infomaniak.ch/ouifm-high.mp3", "Rock"),
            ("Jazz Radio", "https://jazzradio.ice.infomaniak.ch/jazz-radio-high.mp3", "Jazz & Soul"),
            ("AirZen Radio", "https://stream.airzen.fr/airzen-128.mp3", "Bien-être & Positif"),
        ],
        "regions": {
            "Île-de-France (Paris)": [
                ("Générations", "https://generations.ice.infomaniak.ch/generations-high.mp3", "Hip-Hop & Soul"),
                ("Voltage", "https://voltage.ice.infomaniak.ch/voltage-high.mp3", "Hits franciliens"),
                ("Aligre FM", "https://aligrefm.org/aligrefm-128.mp3", "Associative parisienne"),
                ("Tropiques FM", "https://stream.tropiquesfm.net/tropiquesfm-128.mp3", "Musiques tropicales"),
                ("Crooner Radio", "https://croonerradio.ice.infomaniak.ch/croonerradio-high.mp3", "Grands crooners"),
            ],
            "Bretagne": [
                ("Radio Bonheur", "https://radiobonheur.ice.infomaniak.ch/radiobonheur-128.mp3", "Chansons d'hier & d'aujourd'hui"),
                ("Hit West", "https://hitwest.ice.infomaniak.ch/hitwest-high.mp3", "Hits de l'Ouest"),
                ("Bretagne 5", "https://stream.bretagne5.fr/stream", "Info & Région"),
                ("Radio Laser", "https://stream.radiolaser.fr/direct", "Éclectique & Découvertes"),
                ("Radio Balises", "https://streaming.radiobalises.com/direct", "Associative lorientaise"),
            ],
            "Auvergne-Rhône-Alpes (Lyon)": [
                ("Radio Scoop", "https://radioscoop.ice.infomaniak.ch/radioscoop-high.mp3", "Hits & Info Lyon"),
                ("Radio ISA", "https://radioisa.ice.infomaniak.ch/radioisa-high.mp3", "Isère / Savoie"),
                ("Lyon 1ère", "https://lyon1ere.ice.infomaniak.ch/lyon1ere-high.mp3", "Généraliste locale"),
                ("Impact FM", "https://impactfm.ice.infomaniak.ch/impactfm-high.mp3", "Nostalgie & Région"),
            ],
            "Nouvelle-Aquitaine (Bordeaux)": [
                ("Wit FM", "https://witfm.ice.infomaniak.ch/witfm-high.mp3", "Hits Bordeaux"),
                ("Blackbox", "https://blackbox.ice.infomaniak.ch/blackbox-high.mp3", "R'n'B & Hip-hop"),
                ("ARL", "https://stream.arlfm.com/arl", "Aquitaine Radio Live"),
                ("Gold FM", "https://goldfm.ice.infomaniak.ch/goldfm-high.mp3", "Régionale & Sport"),
            ],
            "Occitanie (Toulouse / Montpellier)": [
                ("100% Radio", "https://centpourcent.ice.infomaniak.ch/centpourcent-high.mp3", "Grand Sud"),
                ("Flash FM", "https://flashfm.ice.infomaniak.ch/flashfm-high.mp3", "Pop & Hits"),
                ("RTS FM", "https://rtsfm.ice.infomaniak.ch/rtsfm-high.mp3", "Soleil Méditerranée"),
                ("Radio Présence", "https://radiopresence.ice.infomaniak.ch/radiopresence-high.mp3", "Midi-Pyrénées"),
            ],
            "Provence-Alpes-Côte d'Azur (Marseille / Nice)": [
                ("Radio Star", "https://radiostar.ice.infomaniak.ch/radiostar-high.mp3", "Marseille & Provence"),
                ("Kiss FM", "https://kissfm.ice.infomaniak.ch/kissfm-high.mp3", "Côte d'Azur"),
                ("Maritima", "https://maritima.ice.infomaniak.ch/maritima-high.mp3", "Étang de Berre"),
                ("Radio Emotion", "https://radioemotion.ice.infomaniak.ch/radioemotion-high.mp3", "Nice & Riviera"),
            ],
            "Hauts-de-France (Lille)": [
                ("Metropolys", "https://metropolys.ice.infomaniak.ch/metropolys-high.mp3", "Pop / Électro"),
                ("Contact FM", "https://contactfm.ice.infomaniak.ch/contactfm-high.mp3", "Le Grand Nord"),
                ("Mona FM", "https://monafm.ice.infomaniak.ch/monafm-high.mp3", "Proximité & Souvenirs"),
            ],
            "Grand Est (Strasbourg / Nancy)": [
                ("Top Music", "https://topmusic.ice.infomaniak.ch/topmusic-high.mp3", "Alsace"),
                ("DKL Dreyeckland", "https://dkldrey.ice.infomaniak.ch/dkldrey-high.mp3", "Régionale Alsace"),
                ("Magnum la radio", "https://magnum.ice.infomaniak.ch/magnum-high.mp3", "Lorraine"),
            ],
        }
    },
    "BE": {
        "name": "Belgique 🇧🇪",
        "multilingual": True,
        "languages": [("FR", "Wallonie & Bruxelles (Français)"), ("NL", "Flandre (Néerlandais)")],
        "sub_bouquets": {
            "FR": {
                "national": [
                    ("La Première", "https://radios.rtbf.be/laprem-128.mp3", "RTBF - Info & Société"),
                    ("VivaCité", "https://radios.rtbf.be/vivacite-128.mp3", "RTBF - Proximité & Sport"),
                    ("Classic 21", "https://radios.rtbf.be/classic21-128.mp3", "RTBF - Rock Classique"),
                    ("Tipik", "https://radios.rtbf.be/tipik-128.mp3", "RTBF - Jeunes & Pop"),
                    ("Musiq3", "https://radios.rtbf.be/musiq3-128.mp3", "RTBF - Classique & Jazz"),
                    ("Bel RTL", "https://belrtl.ice.infomaniak.ch/belrtl-mp3-128.mp3", "Généraliste privée"),
                    ("Radio Contact", "https://radiocontact.ice.infomaniak.ch/radiocontact-mp3-128.mp3", "Hits & Divertissement"),
                    ("Nostalgie Belgique", "https://nostalgiewallonie.ice.infomaniak.ch/nostalgiewallonie-128.mp3", "Grands classiques"),
                    ("NRJ Belgique", "https://nrjbelgique.ice.infomaniak.ch/nrjbelgique-128.mp3", "Hits du moment"),
                    ("DH Radio", "https://dhradio.ice.infomaniak.ch/dhradio-128.mp3", "Pop Rock"),
                    ("Fun Radio Belgique", "https://funradiobe.ice.infomaniak.ch/funradiobe-128.mp3", "Dance & Electro"),
                ],
                "regions": {
                    "Régionales & Locales": [
                        ("Antipode", "https://stream.antipode.be/antipode-128.mp3", "Brabant Wallon"),
                        ("Maximum FM", "https://stream.maximumfm.be/maximum-128.mp3", "Liège & Région"),
                        ("Must FM", "https://stream.mustfm.be/mustfm-128.mp3", "Namur & Luxembourg"),
                        ("Sud Radio Belgique", "https://stream.sudradio.be/sudradio-128.mp3", "Hainaut"),
                    ]
                }
            },
            "NL": {
                "national": [
                    ("Radio 1", "https://icecast.vrtcdn.be/radio1-high.mp3", "VRT - Nieuws & Cultuur"),
                    ("Radio 2", "https://icecast.vrtcdn.be/ra2vlb-high.mp3", "VRT - Familieradio"),
                    ("Studio Brussel", "https://icecast.vrtcdn.be/stubru-high.mp3", "VRT - Alternatieve Rock & Pop"),
                    ("MNM", "https://icecast.vrtcdn.be/mnm-high.mp3", "VRT - Hits & Jongeren"),
                    ("Klara", "https://icecast.vrtcdn.be/klara-high.mp3", "VRT - Klassiek"),
                    ("Qmusic Vlaanderen", "https://stream.qmusic.be/qmusic/mp3", "Pop & Hits"),
                    ("Joe", "https://stream.joe.be/joe/mp3", "70s, 80s & 90s"),
                    ("Nostalgie Vlaanderen", "https://stream.nostalgie.be/nostalgie/mp3", "Klassiekers"),
                    ("Willy", "https://stream.willy.radio/willy/mp3", "Rock"),
                    ("TOPradio", "https://topradio.stream.b2stream.be/topradio.mp3", "Dance & House"),
                ],
                "regions": {}
            }
        }
    },
    "CH": {
        "name": "Suisse 🇨🇭",
        "multilingual": True,
        "languages": [("FR", "Suisse romande (Français)"), ("DE", "Suisse alémanique (Allemand)"), ("IT", "Tessin (Italien)")],
        "sub_bouquets": {
            "FR": {
                "national": [
                    ("RTS La 1ère", "https://stream.srg-ssr.ch/m/la-1ere/mp3_128", "SSR - Information & Magazine"),
                    ("RTS Espace 2", "https://stream.srg-ssr.ch/m/espace-2/mp3_128", "SSR - Culture & Classique"),
                    ("RTS Couleur 3", "https://stream.srg-ssr.ch/m/couleur3/mp3_128", "SSR - Pop, Rock & Humour"),
                    ("RTS Option Musique", "https://stream.srg-ssr.ch/m/option-musique/mp3_128", "SSR - Chanson francophone"),
                    ("Rouge FM", "https://rouge.ice.infomaniak.ch/rouge-high.mp3", "Pop & Hits romands"),
                    ("One FM", "https://onefm.ice.infomaniak.ch/onefm-high.mp3", "Genève & Vaud"),
                    ("LFM", "https://lfm.ice.infomaniak.ch/lfm-high.mp3", "Adulte contemporain"),
                    ("Radio Lac", "https://radiolac.ice.infomaniak.ch/radiolac-high.mp3", "Actualité & Débats"),
                    ("Radio Chablais", "https://radiochablais.ice.infomaniak.ch/radiochablais-high.mp3", "Régionale Chablais"),
                    ("RFJ", "https://rfj.ice.infomaniak.ch/rfj-high.mp3", "Jura"),
                    ("GRRIF", "https://grrif.ice.infomaniak.ch/grrif-high.mp3", "Alternative & Décalée"),
                ],
                "regions": {}
            },
            "DE": {
                "national": [
                    ("SRF 1", "https://stream.srg-ssr.ch/m/srf-1/mp3_128", "SRG - Information & Kultur"),
                    ("SRF 2 Kultur", "https://stream.srg-ssr.ch/m/srf-2/mp3_128", "SRG - Klassik & Wissen"),
                    ("SRF 3", "https://stream.srg-ssr.ch/m/srf-3/mp3_128", "SRG - Pop & Rock"),
                    ("SRF 4 News", "https://stream.srg-ssr.ch/m/srf-4/mp3_128", "SRG - Nachrichten"),
                    ("Radio 24", "https://radio24.ice.infomaniak.ch/radio24-high.mp3", "Zürich Hits"),
                    ("Energy Zürich", "https://energyzuerich.ice.infomaniak.ch/energyzuerich-high.mp3", "Energy Pop"),
                    ("Radio Pilatus", "https://radiopilatus.ice.infomaniak.ch/radiopilatus-high.mp3", "Luzern & Zentralschweiz"),
                ],
                "regions": {}
            },
            "IT": {
                "national": [
                    ("RSI Rete Uno", "https://stream.srg-ssr.ch/m/rete-uno/mp3_128", "SSR - Attualità & Musica"),
                    ("RSI Rete Due", "https://stream.srg-ssr.ch/m/rete-due/mp3_128", "SSR - Cultura"),
                    ("RSI Rete Tre", "https://stream.srg-ssr.ch/m/rete-tre/mp3_128", "SSR - Giovani & Rock"),
                    ("Radio 3i", "https://radio3i.ice.infomaniak.ch/radio3i-high.mp3", "Ticino Informazione"),
                ],
                "regions": {}
            }
        }
    },
    "CA": {
        "name": "Canada 🇨🇦",
        "multilingual": True,
        "languages": [("FR", "Québec & Francophonie (Français)"), ("EN", "Canada anglophone (Anglais)")],
        "sub_bouquets": {
            "FR": {
                "national": [
                    ("ICI Radio-Canada Première", "https://rcavliveaudio.akamaized.net/hls/live/2006635/P-2QMTL0_MTL/master.m3u8", "Actualité & Société"),
                    ("ICI Musique", "https://rcavliveaudio.akamaized.net/hls/live/2006634/M-2MMTL0_MTL/master.m3u8", "Musique & Éclectisme"),
                    ("98.5 FM Montréal", "https://cogf.streamon.fm/CHMP-48k.aac", "Opinion & Parlé"),
                    ("CKOI 96.9", "https://cogf.streamon.fm/CKOI-48k.aac", "Hits & Humour"),
                    ("Rythme FM 105.7", "https://cogf.streamon.fm/CFGL-48k.aac", "Pop & Variété"),
                    ("Énergie 94.3", "https://stream.revma.ihrhls.com/zc7458", "Rock & Pop"),
                    ("Rouge FM 107.3", "https://stream.revma.ihrhls.com/zc7462", "Adulte contemporain"),
                    ("CHOI Radio X", "https://radiox.ice.infomaniak.ch/radiox-high.mp3", "Québec Talk & Rock"),
                    ("WKND 91.9", "https://wknd.ice.infomaniak.ch/wknd-high.mp3", "Québec Pop Indie"),
                ],
                "regions": {}
            },
            "EN": {
                "national": [
                    ("CBC Radio One", "https://cbcradiolive.akamaized.net/hls/live/2041285/ES_R1ET/master.m3u8", "News & Current Affairs"),
                    ("CBC Music", "https://cbcradiolive.akamaized.net/hls/live/2041286/ES_R2ET/master.m3u8", "Adult Alternative"),
                    ("Virgin Radio Toronto", "https://stream.revma.ihrhls.com/zc7470", "Top 40"),
                    ("CHUM FM", "https://stream.revma.ihrhls.com/zc7472", "Hot AC Toronto"),
                    ("Q107 Toronto", "https://corus.leanstream.co/CILQFM", "Classic Rock"),
                ],
                "regions": {}
            }
        }
    },
    "UK": {
        "name": "Royaume-Uni 🇬🇧",
        "multilingual": False,
        "languages": [],
        "national": [
            ("BBC Radio 1", "https://as-hls-ww-live.akamaized.net/pool_904/live/ww/bbc_radio_one/bbc_radio_one.isml/bbc_radio_one-audio%3d96000.norewind.m3u8", "New Music & Youth"),
            ("BBC Radio 2", "https://as-hls-ww-live.akamaized.net/pool_904/live/ww/bbc_radio_two/bbc_radio_two.isml/bbc_radio_two-audio%3d96000.norewind.m3u8", "Adult Contemporary"),
            ("BBC Radio 3", "https://as-hls-ww-live.akamaized.net/pool_904/live/ww/bbc_radio_three/bbc_radio_three.isml/bbc_radio_three-audio%3d96000.norewind.m3u8", "Classical & Jazz"),
            ("BBC Radio 4", "https://as-hls-ww-live.akamaized.net/pool_904/live/ww/bbc_radio_fourfm/bbc_radio_fourfm.isml/bbc_radio_fourfm-audio%3d96000.norewind.m3u8", "News & Spoken"),
            ("BBC Radio 5 Live", "https://as-hls-ww-live.akamaized.net/pool_904/live/ww/bbc_radio_five_live/bbc_radio_five_live.isml/bbc_radio_five_live-audio%3d96000.norewind.m3u8", "Live News & Sport"),
            ("BBC 6 Music", "https://as-hls-ww-live.akamaized.net/pool_904/live/ww/bbc_6music/bbc_6music.isml/bbc_6music-audio%3d96000.norewind.m3u8", "Alternative & Indie"),
            ("Capital FM", "https://icecast.thisisdax.com/CapitalUKMP3", "Top 40 / UK Pop"),
            ("Heart UK", "https://icecast.thisisdax.com/HeartUKMP3", "Feel Good"),
            ("Classic FM", "https://icecast.thisisdax.com/ClassicFMMP3", "Classical"),
            ("LBC", "https://icecast.thisisdax.com/LBCUKMP3", "Leading Britain's Conversation"),
            ("Absolute Radio", "https://icecast.timlradio.co.uk/absoluteradio.mp3", "Classic & Modern Rock"),
            ("Virgin Radio UK", "https://radio.virginradio.co.uk/stream", "Rock & Pop"),
            ("Smooth Radio", "https://icecast.thisisdax.com/SmoothUKMP3", "Relaxing Music"),
        ],
        "regions": {}
    }
}


class BrowseBouquetsWindow(Gtk.Window):
    def __init__(self, existing_stations):
        super().__init__(title="📻 Découvrir les bouquets de radios (TiMonde)")
        self.set_default_size(750, 560)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(12)
        self.set_icon_name("audio-x-generic")

        self.existing_stations = existing_stations
        # Sets pour recherche rapide des doublons (insensible à la casse)
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
        for code, info in BOUQUETS_DB.items():
            self.combo_country.append(code, info["name"])
        self.combo_country.set_active_id("FR")
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

        # Liste déroulante des régions (active uniquement si radio_region est coché)
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

        # Colonne Checkbox
        renderer_toggle = Gtk.CellRendererToggle()
        renderer_toggle.connect("toggled", self.on_cell_toggled)
        col_check = Gtk.TreeViewColumn("Ajouter", renderer_toggle, active=0)
        self.treeview.append_column(col_check)

        # Colonne Nom de la radio
        renderer_text = Gtk.CellRendererText()
        col_name = Gtk.TreeViewColumn("Nom de la station", renderer_text, text=1)
        col_name.set_min_width(200)
        self.treeview.append_column(col_name)

        # Colonne Genre / Style
        renderer_genre = Gtk.CellRendererText()
        col_genre = Gtk.TreeViewColumn("Genre / Style", renderer_genre, text=2)
        col_genre.set_min_width(180)
        self.treeview.append_column(col_genre)

        # Colonne Remarque / Doublon
        renderer_note = Gtk.CellRendererText()
        col_note = Gtk.TreeViewColumn("Statut", renderer_note, markup=3)
        self.treeview.append_column(col_note)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.treeview)
        list_box.pack_start(scroll, True, True, 0)

        # Boutons de sélection rapide
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

        # 4. Pied de page : Groupe cible et bouton d'action
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

        # Initialisation de l'affichage
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
            # Si on clique sur "Tout cocher", on n'impose pas de cocher les doublons
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
        country_id = self.combo_country.get_active_id() or "FR"
        info = BOUQUETS_DB.get(country_id, {})
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
        country_id = self.combo_country.get_active_id() or "FR"
        info = BOUQUETS_DB.get(country_id, {})

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

        # Mettre à jour la liste des régions disponibles
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

        # Déterminer la liste des stations
        stations = []
        default_group = ""

        country_name = info.get("name", "").split()[0] # ex "France"
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

        # Remplir le store
        self.store.clear()
        for name, url, genre in stations:
            clean_url = url.strip()
            clean_name = name.strip().lower()

            is_dup = (clean_url in self.existing_urls) or (clean_name in self.existing_names)
            # Par défaut, on coche si ce n'est PAS un doublon
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

    win = BrowseBouquetsWindow(existing_stations)
    win.show_all()
    Gtk.main()

    if win.saved:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
