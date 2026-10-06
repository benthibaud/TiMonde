use crate::audio::{AudioEngine, PlaybackState};
use crate::bookmarks::{save_bookmarks, update_station_url};
use crate::models::{Group, Station};
use crate::playlist::resolve_stream_url;
use crate::radio_browser::{find_backup_stream, notify};
use ksni::menu::{MenuItem, StandardItem, SubMenu};
use log::{error, info};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

pub struct TiMondeTray {
    pub audio: Arc<Mutex<Option<AudioEngine>>>,
    pub current_volume: Arc<Mutex<f64>>,
    pub root_group: Arc<Mutex<Group>>,
    pub bookmarks_path: PathBuf,
    pub last_station: Arc<Mutex<Option<Station>>>,
    pub current_station: Arc<Mutex<Option<Station>>>,
    pub current_title: Arc<Mutex<Option<String>>>,
    pub play_generation: Arc<AtomicU64>,
}

impl TiMondeTray {
    pub fn new(root_group: Group, bookmarks_path: PathBuf) -> Self {
        Self {
            audio: Arc::new(Mutex::new(None)),
            current_volume: Arc::new(Mutex::new(0.80)),
            root_group: Arc::new(Mutex::new(root_group)),
            bookmarks_path,
            last_station: Arc::new(Mutex::new(None)),
            current_station: Arc::new(Mutex::new(None)),
            current_title: Arc::new(Mutex::new(None)),
            play_generation: Arc::new(AtomicU64::new(0)),
        }
    }

    /// Obtient l'état audio actuel de façon non-bloquante sans forcer l'allocation
    pub fn state(&self) -> PlaybackState {
        let guard = self.audio.lock().unwrap();
        match guard.as_ref() {
            Some(engine) => engine.state(),
            None => PlaybackState::Stopped,
        }
    }

    /// Assure l'existence du moteur audio à la demande (Lazy Loading)
    pub fn get_or_create_engine(
        audio_mutex: &Arc<Mutex<Option<AudioEngine>>>,
        current_volume: &Arc<Mutex<f64>>,
        current_title: &Arc<Mutex<Option<String>>>,
    ) -> Result<(), String> {
        let mut guard = audio_mutex.lock().unwrap();
        if guard.is_none() {
            info!("⚡ Chargement à la demande du moteur GStreamer...");
            match AudioEngine::new(Arc::clone(current_title)) {
                Ok(engine) => {
                    let vol = *current_volume.lock().unwrap();
                    engine.set_volume(vol);
                    *guard = Some(engine);
                }
                Err(e) => return Err(format!("Échec GStreamer : {}", e)),
            }
        }
        Ok(())
    }

    /// Exécute le flux complet de lecture avec résolution de playlists, watchdog et secours automatique
    #[allow(clippy::too_many_arguments)]
    pub fn play_station_flow(
        station: Station,
        audio: &Arc<Mutex<Option<AudioEngine>>>,
        current_volume: &Arc<Mutex<f64>>,
        current_station: &Arc<Mutex<Option<Station>>>,
        last_station: &Arc<Mutex<Option<Station>>>,
        current_title: &Arc<Mutex<Option<String>>>,
        play_generation: &Arc<AtomicU64>,
        root_group: &Arc<Mutex<Group>>,
        bookmarks_path: &Path,
    ) {
        let station_name = station.name.clone();
        let raw_url = station.url.clone();
        info!("Sélection de la station : {} ({})", station_name, raw_url);

        // Résolution préalable si l'URL pointe vers un fichier de playlist (.m3u, .pls, .asx)
        let resolved_url = resolve_stream_url(&raw_url);

        if let Err(e) = Self::get_or_create_engine(audio, current_volume, current_title) {
            error!("{}", e);
            notify("TiMonde", "Impossible d'initialiser l'audio");
            return;
        }

        {
            let guard = audio.lock().unwrap();
            if let Some(ref engine) = *guard {
                if let Err(e) = engine.play(&resolved_url) {
                    error!("Échec initial de lecture : {}", e);
                    notify("TiMonde", &format!("Impossible de lancer {}", station_name));
                    return;
                }
            }
        }

        *last_station.lock().unwrap() = Some(station.clone());
        *current_station.lock().unwrap() = Some(station);
        *current_title.lock().unwrap() = None;

        let gen = play_generation.fetch_add(1, Ordering::SeqCst) + 1;
        let gen_clone = Arc::clone(play_generation);
        let audio_clone = Arc::clone(audio);
        let root_group_clone = Arc::clone(root_group);
        let bookmarks_path_clone = bookmarks_path.to_path_buf();
        let name_for_watchdog = station_name.clone();

        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs(5));

            if gen_clone.load(Ordering::SeqCst) != gen {
                return;
            }

            let st = {
                let guard = audio_clone.lock().unwrap();
                guard.as_ref().map(|e| e.state()).unwrap_or(PlaybackState::Stopped)
            };

            if st == PlaybackState::Buffering || st == PlaybackState::Error {
                info!("Watchdog : flux muet pour {}", name_for_watchdog);
                notify(
                    "TiMonde",
                    &format!("{} ne répond pas. Recherche d'un flux de secours...", name_for_watchdog),
                );

                if let Some((_found_name, backup_url)) = find_backup_stream(&name_for_watchdog) {
                    if gen_clone.load(Ordering::SeqCst) != gen {
                        return;
                    }
                    let direct_backup = resolve_stream_url(&backup_url);
                    info!("Watchdog : bascule sur le flux de secours {}", direct_backup);
                    let played = {
                        let guard = audio_clone.lock().unwrap();
                        if let Some(ref engine) = *guard {
                            engine.play(&direct_backup).is_ok()
                        } else {
                            false
                        }
                    };

                    if played {
                        {
                            let mut group = root_group_clone.lock().unwrap();
                            if update_station_url(&mut group, &name_for_watchdog, &direct_backup) {
                                let _ = save_bookmarks(&group, &bookmarks_path_clone);
                            }
                        }
                        notify(
                            "TiMonde",
                            &format!("Flux réparé et enregistré pour {} !", name_for_watchdog),
                        );
                    }
                } else if gen_clone.load(Ordering::SeqCst) == gen {
                    notify(
                        "TiMonde",
                        &format!("La radio {} est indisponible actuellement.", name_for_watchdog),
                    );
                    let guard = audio_clone.lock().unwrap();
                    if let Some(ref engine) = *guard {
                        let _ = engine.stop();
                    }
                }
            }
        });
    }

    /// Arrête la lecture et restitue la mémoire vers le système d'exploitation
    pub fn stop_and_trim_flow(
        audio: &Arc<Mutex<Option<AudioEngine>>>,
        current_station: &Arc<Mutex<Option<Station>>>,
        current_title: &Arc<Mutex<Option<String>>>,
    ) {
        let mut guard = audio.lock().unwrap();
        if let Some(ref engine) = *guard {
            let _ = engine.stop();
        }
        *current_station.lock().unwrap() = None;
        *current_title.lock().unwrap() = None;

        // Décharge le pipeline GStreamer et restitue la mémoire vive au système Linux
        *guard = None;
        unsafe {
            libc::malloc_trim(0);
        }
        info!("🧹 Mémoire audio libérée (malloc_trim)");
    }

    pub fn play_station(&self, station: Station) {
        Self::play_station_flow(
            station,
            &self.audio,
            &self.current_volume,
            &self.current_station,
            &self.last_station,
            &self.current_title,
            &self.play_generation,
            &self.root_group,
            &self.bookmarks_path,
        );
    }

    pub fn stop_and_trim(&self) {
        Self::stop_and_trim_flow(&self.audio, &self.current_station, &self.current_title);
    }

    /// Construit récursivement les éléments de menu pour un groupe donné
    fn build_group_menu(group: &Group) -> Vec<MenuItem<Self>> {
        let mut items = Vec::new();

        for sub in &group.subgroups {
            let submenu_items = Self::build_group_menu(sub);
            if !submenu_items.is_empty() {
                let sub_item = SubMenu {
                    label: sub.name.clone(),
                    submenu: submenu_items,
                    enabled: true,
                    visible: true,
                    ..Default::default()
                };
                items.push(MenuItem::SubMenu(sub_item));
            }
        }

        if !group.subgroups.is_empty() && !group.stations.is_empty() {
            items.push(MenuItem::Separator);
        }

        for station in &group.stations {
            if station.is_separator() {
                items.push(MenuItem::Separator);
            } else {
                let st_clone = station.clone();
                let item = StandardItem {
                    label: station.name.clone(),
                    activate: Box::new(move |tray: &mut Self| {
                        tray.play_station(st_clone.clone());
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                };
                items.push(MenuItem::Standard(item));
            }
        }

        items
    }

    /// Dialogue interactif de sélection de groupe (racine, existant ou nouveau)
    pub fn select_target_group_dialog(root_group: &Arc<Mutex<Group>>) -> Option<Option<String>> {
        let existing_groups: Vec<String> = {
            let guard = root_group.lock().unwrap();
            fn collect_names(g: &Group, list: &mut Vec<String>) {
                for sub in &g.subgroups {
                    list.push(sub.name.clone());
                    collect_names(sub, list);
                }
            }
            let mut list = Vec::new();
            collect_names(&guard, &mut list);
            list
        };

        // Si aucun groupe n est encore créé, on envoie directement à la racine par défaut
        if existing_groups.is_empty() {
            return Some(None);
        }

        let mut zenity_list = std::process::Command::new("zenity");
        zenity_list
            .arg("--list")
            .arg("--title=Groupe de destination")
            .arg("--text=Choisissez le groupe de destination :")
            .arg("--column=Groupe")
            .arg("(Racine - aucun groupe)")
            .arg("[+ Nouveau groupe...]");

        for g in &existing_groups {
            zenity_list.arg(g);
        }

        let choice_out = match zenity_list.output() {
            Ok(out) if out.status.success() => out,
            _ => return None, // Annulé
        };

        let choice = String::from_utf8_lossy(&choice_out.stdout).trim().to_string();
        if choice.is_empty() || choice.starts_with("(Racine") {
            Some(None)
        } else if choice.starts_with("[+ Nouveau") {
            let entry_out = match std::process::Command::new("zenity")
                .arg("--entry")
                .arg("--title=Nouveau groupe")
                .arg("--text=Nom du nouveau groupe de radios :")
                .output()
            {
                Ok(out) if out.status.success() => out,
                _ => return None,
            };
            let name = String::from_utf8_lossy(&entry_out.stdout).trim().to_string();
            if !name.is_empty() {
                Some(Some(name))
            } else {
                Some(None)
            }
        } else {
            Some(Some(choice))
        }
    }

    /// Ouvre la boîte de dialogue native pour ajouter une station manuellement
    pub fn trigger_add_station_dialog(root_group: Arc<Mutex<Group>>, bookmarks_path: PathBuf) {
        std::thread::spawn(move || {
            let form_output = match std::process::Command::new("zenity")
                .arg("--forms")
                .arg("--title=➕ Ajouter une station (TiMonde)")
                .arg("--text=Entrez les informations de la nouvelle station :")
                .arg("--add-entry=Nom de la station")
                .arg("--add-entry=URL du flux (http/https)")
                .output()
            {
                Ok(out) if out.status.success() => out,
                _ => return, // Annulé
            };

            let fields = String::from_utf8_lossy(&form_output.stdout).trim().to_string();
            let parts: Vec<&str> = fields.split('|').collect();
            if parts.len() < 2 {
                return;
            }

            let station_name = parts[0].trim();
            let station_url = parts[1].trim();

            if station_name.is_empty() || station_url.is_empty() {
                crate::radio_browser::notify("TiMonde", "Nom ou URL manquant");
                return;
            }

            let target_group = match Self::select_target_group_dialog(&root_group) {
                Some(tg) => tg,
                None => return,
            };

            let mut root = root_group.lock().unwrap().clone();
            match crate::import::add_single_station(
                &mut root,
                station_name,
                station_url,
                target_group.as_deref(),
            ) {
                Ok(msg) => {
                    if let Err(e) = crate::bookmarks::save_bookmarks(&root, &bookmarks_path) {
                        log::error!("Erreur lors de la sauvegarde : {}", e);
                        crate::radio_browser::notify("TiMonde", &format!("Erreur sauvegarde : {}", e));
                        return;
                    }
                    *root_group.lock().unwrap() = root;
                    log::info!("✅ {}", msg);
                    crate::radio_browser::notify("TiMonde", &msg);
                }
                Err(e) => {
                    log::warn!("Échec de l ajout : {}", e);
                    crate::radio_browser::notify("TiMonde", &format!("Ajout impossible : {}", e));
                }
            }
        });
    }

    /// Recherche interactive dans l annuaire mondial Radio-Browser
    pub fn trigger_search_online_dialog(root_group: Arc<Mutex<Group>>, bookmarks_path: PathBuf) {
        std::thread::spawn(move || {
            let entry_output = match std::process::Command::new("zenity")
                .arg("--entry")
                .arg("--title=🔍 Rechercher sur Radio-Browser")
                .arg("--text=Nom ou mot-clé de la radio (ex: FIP, Jazz, BBC, Rock, Nostalgie...) :")
                .output()
            {
                Ok(out) if out.status.success() => out,
                _ => return,
            };

            let query = String::from_utf8_lossy(&entry_output.stdout).trim().to_string();
            if query.is_empty() {
                return;
            }

            crate::radio_browser::notify("TiMonde", &format!("Recherche pour '{}'...", query));
            let results = crate::radio_browser::search_online(&query, 30);

            if results.is_empty() {
                crate::radio_browser::notify("TiMonde", &format!("Aucune station trouvée pour '{}'", query));
                return;
            }

            let mut list_cmd = std::process::Command::new("zenity");
            list_cmd
                .arg("--list")
                .arg(format!("--title=Résultats pour '{}' ({} trouvées)", query, results.len()))
                .arg("--text=Sélectionnez la station à ajouter à vos favoris :")
                .arg("--column=ID")
                .arg("--column=Nom")
                .arg("--column=Pays")
                .arg("--column=Format")
                .arg("--column=Débit")
                .arg("--column=Votes")
                .arg("--width=720")
                .arg("--height=420");

            for (i, r) in results.iter().enumerate() {
                list_cmd.arg(format!("{}", i));
                list_cmd.arg(&r.name);
                list_cmd.arg(if r.country.is_empty() { "-" } else { &r.country });
                list_cmd.arg(if r.codec.is_empty() { "-" } else { &r.codec });
                list_cmd.arg(if r.bitrate > 0 { format!("{} kbps", r.bitrate) } else { "-".to_string() });
                list_cmd.arg(format!("{}", r.votes));
            }

            let sel_output = match list_cmd.output() {
                Ok(out) if out.status.success() => out,
                _ => return,
            };

            let sel_str = String::from_utf8_lossy(&sel_output.stdout).trim().to_string();
            let selected_idx: usize = match sel_str.parse() {
                Ok(idx) if idx < results.len() => idx,
                _ => return,
            };

            let chosen = &results[selected_idx];

            let target_group = match Self::select_target_group_dialog(&root_group) {
                Some(tg) => tg,
                None => return,
            };

            let mut root = root_group.lock().unwrap().clone();
            match crate::import::add_single_station(
                &mut root,
                &chosen.name,
                &chosen.url_resolved,
                target_group.as_deref(),
            ) {
                Ok(msg) => {
                    if let Err(e) = crate::bookmarks::save_bookmarks(&root, &bookmarks_path) {
                        log::error!("Erreur sauvegarde : {}", e);
                        crate::radio_browser::notify("TiMonde", &format!("Erreur sauvegarde : {}", e));
                        return;
                    }
                    *root_group.lock().unwrap() = root;
                    log::info!("✅ {}", msg);
                    crate::radio_browser::notify("TiMonde", &msg);
                }
                Err(e) => {
                    log::warn!("Échec de l ajout : {}", e);
                    crate::radio_browser::notify("TiMonde", &format!("Ajout impossible : {}", e));
                }
            }
        });
    }

    /// Ouvre les boîtes de dialogue natives (Zenity) pour importer une liste de stations
    pub fn trigger_import_dialog(root_group: Arc<Mutex<Group>>, bookmarks_path: PathBuf) {
        std::thread::spawn(move || {
            let file_output = match std::process::Command::new("zenity")
                .arg("--file-selection")
                .arg("--title=Importer une liste de radios (TiMonde)")
                .arg("--file-filter=Listes de radios (*.json, *.m3u, *.csv, *.xml) | *.json *.m3u *.m3u8 *.csv *.xml")
                .arg("--file-filter=Tous les fichiers | *")
                .output()
            {
                Ok(out) if out.status.success() => out,
                _ => return,
            };

            let file_str = String::from_utf8_lossy(&file_output.stdout).trim().to_string();
            if file_str.is_empty() {
                return;
            }
            let file_path = PathBuf::from(&file_str);
            if !file_path.exists() {
                crate::radio_browser::notify("TiMonde", "Fichier introuvable");
                return;
            }

            let target_group = match Self::select_target_group_dialog(&root_group) {
                Some(tg) => tg,
                None => return,
            };

            let mut root = root_group.lock().unwrap().clone();
            match crate::import::import_file(&mut root, &file_path, target_group.as_deref()) {
                Ok(report) => {
                    if let Err(e) = crate::bookmarks::save_bookmarks(&root, &bookmarks_path) {
                        log::error!("Erreur lors de la sauvegarde : {}", e);
                        crate::radio_browser::notify("TiMonde", &format!("Erreur lors de la sauvegarde : {}", e));
                        return;
                    }
                    *root_group.lock().unwrap() = root;
                    log::info!(
                        "✅ Importation réussie : {} ajoutée(s), {} doublon(s) ignoré(s), {} groupe(s) créé(s)",
                        report.stations_added, report.duplicates_skipped, report.groups_created
                    );
                    crate::radio_browser::notify(
                        "TiMonde",
                        &format!(
                            "Importation réussie !\n• {} station(s) ajoutée(s)\n• {} doublon(s) ignoré(s)",
                            report.stations_added, report.duplicates_skipped
                        ),
                    );
                }
                Err(e) => {
                    log::error!("Erreur lors de l importation : {}", e);
                    crate::radio_browser::notify("TiMonde", &format!("Erreur d importation : {}", e));
                }
            }
        });
    }
}

impl ksni::Tray for TiMondeTray {
    const MENU_ON_ACTIVATE: bool = true;

    fn id(&self) -> String {
        "timonde".to_string()
    }

    fn title(&self) -> String {
        let cur_st = self.current_station.lock().unwrap();
        match (cur_st.as_ref(), self.state()) {
            (Some(st), PlaybackState::Playing) => {
                let cur_title = self.current_title.lock().unwrap();
                if let Some(ref t) = *cur_title {
                    format!("TiMonde : {} - {}", st.name, t)
                } else {
                    format!("TiMonde : {}", st.name)
                }
            }
            (Some(st), PlaybackState::Buffering) => format!("TiMonde (Connexion...) : {}", st.name),
            (Some(st), PlaybackState::Paused) => format!("TiMonde (Pause) : {}", st.name),
            _ => "TiMonde".to_string(),
        }
    }

    fn icon_name(&self) -> String {
        match self.state() {
            PlaybackState::Playing => "timonde_on".to_string(),
            PlaybackState::Buffering => "timonde_error".to_string(),
            PlaybackState::Paused | PlaybackState::Stopped | PlaybackState::Error => "timonde_off".to_string(),
        }
    }

    fn icon_theme_path(&self) -> String {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        let local_icons = format!("{}/.local/share/icons/hicolor/scalable/panel", home);
        if std::path::Path::new(&local_icons).exists() {
            local_icons
        } else {
            let project_icons = concat!(env!("CARGO_MANIFEST_DIR"), "/data/icons");
            project_icons.to_string()
        }
    }

    fn menu(&self) -> Vec<MenuItem<Self>> {
        let mut menu = Vec::new();
        let current_state = self.state();

        // 1. En-tête : Station et état
        let cur_st = self.current_station.lock().unwrap();
        let cur_title = self.current_title.lock().unwrap();
        let status_label = match (cur_st.as_ref(), current_state) {
            (Some(st), PlaybackState::Playing) => {
                if let Some(ref t) = *cur_title {
                    format!("▶ {} ({})", st.name, t)
                } else {
                    format!("▶ En lecture : {}", st.name)
                }
            }
            (Some(st), PlaybackState::Buffering) => format!("⏳ Connexion à {}...", st.name),
            (Some(st), PlaybackState::Paused) => format!("⏸ En pause : {}", st.name),
            _ => "⏹️ TiMonde (En veille)".to_string(),
        };

        menu.push(MenuItem::Standard(StandardItem {
            label: status_label,
            enabled: false,
            visible: true,
            ..Default::default()
        }));

        // Option rapide : Copier le titre dans le presse-papier
        if let Some(ref t) = *cur_title {
            let title_copy = t.clone();
            menu.push(MenuItem::Standard(StandardItem {
                label: format!("📋 Copier : {}", title_copy),
                activate: Box::new(move |_tray| {
                    let _ = std::process::Command::new("sh")
                        .arg("-c")
                        .arg(format!("printf '%s' \"{}\" | (wl-copy 2>/dev/null || xclip -selection clipboard 2>/dev/null || true)", title_copy))
                        .spawn();
                    notify("TiMonde", "Titre copié dans le presse-papier !");
                }),
                enabled: true,
                visible: true,
                ..Default::default()
            }));
        }

        drop(cur_st);
        drop(cur_title);

        // 2. Contrôles de lecture (Pause, Reprendre, Relancer, Arrêter)
        match current_state {
            PlaybackState::Playing => {
                menu.push(MenuItem::Standard(StandardItem {
                    label: "⏸ Mettre en pause".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        let guard = tray.audio.lock().unwrap();
                        if let Some(ref engine) = *guard {
                            let _ = engine.pause();
                        }
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
                menu.push(MenuItem::Standard(StandardItem {
                    label: "⏹ Arrêter la lecture".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        tray.stop_and_trim();
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
            }
            PlaybackState::Paused => {
                menu.push(MenuItem::Standard(StandardItem {
                    label: "▶ Reprendre la lecture".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        let guard = tray.audio.lock().unwrap();
                        if let Some(ref engine) = *guard {
                            let _ = engine.resume();
                        }
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
                menu.push(MenuItem::Standard(StandardItem {
                    label: "⏹ Arrêter la lecture".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        tray.stop_and_trim();
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
            }
            PlaybackState::Stopped | PlaybackState::Error => {
                let last = self.last_station.lock().unwrap();
                if let Some(ref last_st) = *last {
                    let st_to_replay = last_st.clone();
                    menu.push(MenuItem::Standard(StandardItem {
                        label: format!("▶ Relancer : {}", st_to_replay.name),
                        activate: Box::new(move |tray: &mut Self| {
                            tray.play_station(st_to_replay.clone());
                        }),
                        enabled: true,
                        visible: true,
                        ..Default::default()
                    }));
                }
            }
            PlaybackState::Buffering => {
                menu.push(MenuItem::Standard(StandardItem {
                    label: "⏹ Arrêter la connexion".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        tray.stop_and_trim();
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
            }
        }

        menu.push(MenuItem::Separator);

        // 3. Arborescence des radios (le niveau "root" est déjà épuré au chargement)
        let root_group = self.root_group.lock().unwrap();

        for sub in &root_group.subgroups {
            let submenu_items = Self::build_group_menu(sub);
            if !submenu_items.is_empty() {
                menu.push(MenuItem::SubMenu(SubMenu {
                    label: sub.name.clone(),
                    submenu: submenu_items,
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
            }
        }

        for st in &root_group.stations {
            if !st.is_separator() {
                let st_clone = st.clone();
                menu.push(MenuItem::Standard(StandardItem {
                    label: st.name.clone(),
                    activate: Box::new(move |tray: &mut Self| {
                        tray.play_station(st_clone.clone());
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
            }
        }

        menu.push(MenuItem::Separator);

        // 4. Contrôle du volume
        let current_vol = *self.current_volume.lock().unwrap();
        let vol_percent = (current_vol * 100.0).round() as i32;
        menu.push(MenuItem::SubMenu(SubMenu {
            label: format!("🔊 Volume ({vol_percent}%)"),
            submenu: vec![
                MenuItem::Standard(StandardItem {
                    label: "100%".to_string(),
                    activate: Box::new(|tray| {
                        *tray.current_volume.lock().unwrap() = 1.0;
                        if let Some(ref e) = *tray.audio.lock().unwrap() {
                            e.set_volume(1.0);
                        }
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "75%".to_string(),
                    activate: Box::new(|tray| {
                        *tray.current_volume.lock().unwrap() = 0.75;
                        if let Some(ref e) = *tray.audio.lock().unwrap() {
                            e.set_volume(0.75);
                        }
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "50%".to_string(),
                    activate: Box::new(|tray| {
                        *tray.current_volume.lock().unwrap() = 0.50;
                        if let Some(ref e) = *tray.audio.lock().unwrap() {
                            e.set_volume(0.50);
                        }
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "25%".to_string(),
                    activate: Box::new(|tray| {
                        *tray.current_volume.lock().unwrap() = 0.25;
                        if let Some(ref e) = *tray.audio.lock().unwrap() {
                            e.set_volume(0.25);
                        }
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "Muet (0%)".to_string(),
                    activate: Box::new(|tray| {
                        *tray.current_volume.lock().unwrap() = 0.0;
                        if let Some(ref e) = *tray.audio.lock().unwrap() {
                            e.set_volume(0.0);
                        }
                    }),
                    ..Default::default()
                }),
            ],
            enabled: true,
            visible: true,
            ..Default::default()
        }));

        menu.push(MenuItem::Separator);

        // 5. Options et gestion des signets
        menu.push(MenuItem::SubMenu(SubMenu {
            label: "⚙️ Options".to_string(),
            submenu: vec![
                MenuItem::Standard(StandardItem {
                    label: "➕ Ajouter une station...".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        Self::trigger_add_station_dialog(
                            Arc::clone(&tray.root_group),
                            tray.bookmarks_path.clone(),
                        );
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "🔍 Rechercher sur Radio-Browser...".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        Self::trigger_search_online_dialog(
                            Arc::clone(&tray.root_group),
                            tray.bookmarks_path.clone(),
                        );
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "📥 Importer une liste de radios...".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        Self::trigger_import_dialog(
                            Arc::clone(&tray.root_group),
                            tray.bookmarks_path.clone(),
                        );
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "🔄 Recharger les signets".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        info!("Rechargement des signets depuis : {:?}", tray.bookmarks_path);
                        if let Ok(new_group) = crate::bookmarks::load_bookmarks(&tray.bookmarks_path) {
                            let count = new_group.total_stations();
                            *tray.root_group.lock().unwrap() = new_group;
                            notify("TiMonde", &format!("{} signets rechargés avec succès !", count));
                        } else {
                            notify("TiMonde", "Erreur lors du rechargement des signets");
                        }
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "📝 Ouvrir bookmarks.xml".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        let path_str = tray.bookmarks_path.to_string_lossy().to_string();
                        let _ = std::process::Command::new("xdg-open").arg(path_str).spawn();
                    }),
                    ..Default::default()
                }),
            ],
            enabled: true,
            visible: true,
            ..Default::default()
        }));

        // 6. Quitter proprement l'application
        menu.push(MenuItem::Standard(StandardItem {
            label: "Quitter TiMonde".to_string(),
            activate: Box::new(|tray: &mut Self| {
                info!("Fermeture demandée par l'utilisateur.");
                tray.stop_and_trim();
                std::process::exit(0);
            }),
            enabled: true,
            visible: true,
            ..Default::default()
        }));

        menu
    }
}
