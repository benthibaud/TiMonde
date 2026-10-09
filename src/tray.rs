use crate::audio::{AudioEngine, PlaybackState};
use crate::bookmarks::{save_bookmarks, update_station_url};
use crate::models::{Group, Station};
use crate::playlist::resolve_stream_url;
use crate::radio_browser::{find_backup_stream, notify};
use ksni::menu::{CheckmarkItem, MenuItem, StandardItem, SubMenu};
use log::{error, info};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
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
    pub is_ephemeral: Arc<AtomicBool>,
    pub play_generation: Arc<AtomicU64>,
    pub tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    pub sleep_timer: Arc<Mutex<Option<std::time::Instant>>>,
}

impl TiMondeTray {
    pub fn find_station_by_url(root: &Group, station_url: &str) -> Option<Station> {
        let norm = crate::import::normalize_url(station_url);
        for s in &root.stations {
            if !s.is_separator() && (s.url == station_url || crate::import::normalize_url(&s.url) == norm) {
                return Some(s.clone());
            }
        }
        for sub in &root.subgroups {
            if let Some(found) = Self::find_station_by_url(sub, station_url) {
                return Some(found);
            }
        }
        None
    }
    pub fn new(root_group: Group, bookmarks_path: PathBuf) -> Self {
        let initial_last_station = {
            let state = crate::state::AppState::load(&crate::state::AppState::default_path());
            // Si la dernière station sauvegardée existe toujours dans les bookmarks, l'utiliser
            if let Some(ref st) = state.last_station {
                Self::find_station_by_url(&root_group, &st.url).or(Some(st.clone()))
            } else {
                None
            }
        };

        Self {
            audio: Arc::new(Mutex::new(None)),
            current_volume: Arc::new(Mutex::new(0.80)),
            root_group: Arc::new(Mutex::new(root_group)),
            bookmarks_path,
            last_station: Arc::new(Mutex::new(initial_last_station)),
            current_station: Arc::new(Mutex::new(None)),
            current_title: Arc::new(Mutex::new(None)),
            is_ephemeral: Arc::new(AtomicBool::new(false)),
            play_generation: Arc::new(AtomicU64::new(0)),
            tray_handle: Arc::new(Mutex::new(None)),
            sleep_timer: Arc::new(Mutex::new(None)),
        }
    }

    /// Recharge systématiquement les signets depuis le fichier bookmarks.xml
    /// et notifie la barre des tâches (ksni / dbusmenu) pour reconstruire immédiatement le menu.
    pub fn reload_bookmarks_and_update_tray(
        root_group: &Arc<Mutex<Group>>,
        bookmarks_path: &Path,
        tray_handle: &Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    ) -> Result<usize, String> {
        match crate::bookmarks::load_bookmarks(bookmarks_path) {
            Ok(new_group) => {
                let total = new_group.total_stations();
                *root_group.lock().unwrap() = new_group;
                info!("{} signets rechargés avec succès depuis {:?}", total, bookmarks_path);

                let handle_cell = Arc::clone(tray_handle);
                std::thread::spawn(move || {
                    if let Some(ref h) = *handle_cell.lock().unwrap() {
                        h.update(|_| {});
                    }
                });

                Ok(total)
            }
            Err(e) => {
                let err_msg = format!("{}", e);
                error!("Erreur lors du rechargement des signets : {}", err_msg);
                Err(err_msg)
            }
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
            info!("Chargement à la demande du moteur GStreamer...");
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
    /// Recherche récursive du chemin hiérarchique du groupe contenant une station donnée (ex: "France/Bretagne")
    fn find_group_name_for_station(root: &Group, station_url: &str) -> Option<String> {
        fn find_rec(group: &Group, prefix: &str, url: &str) -> Option<String> {
            for sub in &group.subgroups {
                if sub.is_separator() {
                    continue;
                }
                let current_path = if prefix.is_empty() {
                    sub.name.clone()
                } else {
                    format!("{}/{}", prefix, sub.name)
                };
                if sub.stations.iter().any(|s| crate::import::normalize_url(&s.url) == crate::import::normalize_url(url)) {
                    return Some(current_path);
                }
                if let Some(found) = find_rec(sub, &current_path, url) {
                    return Some(found);
                }
            }
            None
        }
        find_rec(root, "", station_url)
    }

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
        *current_station.lock().unwrap() = Some(station.clone());
        *current_title.lock().unwrap() = None;

        // Persistance atomique immédiate de la station en écoute dans state.json
        {
            let st_persist = station.clone();
            std::thread::spawn(move || {
                let mut state = crate::state::AppState::load(&crate::state::AppState::default_path());
                state.last_station = Some(st_persist);
                let _ = state.save(&crate::state::AppState::default_path());
            });
        }

        let group_name = {
            let guard = root_group.lock().unwrap();
            Self::find_group_name_for_station(&guard, &station.url)
        };
        if let Some(time_info) = crate::timezone::get_local_time_for_station(station.country.as_deref(), &station_name, group_name.as_deref(), station.timezone.as_deref()) {
            let offset_sign = if time_info.offset_hours >= 0.0 { "+" } else { "" };
            crate::radio_browser::notify(
                "TiMonde",
                &format!(
                    "{}
{} • {} (UTC{}{:.0}h)",
                    station_name,
                    time_info.country_name,
                    time_info.formatted_time,
                    offset_sign,
                    time_info.offset_hours
                ),
            );
        }

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
        info!("Mémoire audio libérée (malloc_trim)");
    }

    pub fn play_station(&self, station: Station) {
        self.is_ephemeral.store(false, Ordering::SeqCst);
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
        let handle_cell = Arc::clone(&self.tray_handle);
        std::thread::spawn(move || {
            if let Some(ref h) = *handle_cell.lock().unwrap() {
                h.update(|_| {});
            }
        });
    }

    pub fn stop_and_trim(&self) {
        self.is_ephemeral.store(false, Ordering::SeqCst);
        Self::stop_and_trim_flow(&self.audio, &self.current_station, &self.current_title);
        let handle_cell = Arc::clone(&self.tray_handle);
        std::thread::spawn(move || {
            if let Some(ref h) = *handle_cell.lock().unwrap() {
                h.update(|_| {});
            }
        });
    }

    /// Lance la lecture d'une station de radio de façon éphémère (sans l'ajouter aux signets)
    pub fn play_ephemeral_station(&self, station: Station) {
        let station_name = station.name.clone();
        let raw_url = station.url.clone();
        info!("Écoute éphémère : {} ({})", station_name, raw_url);

        self.is_ephemeral.store(true, Ordering::SeqCst);

        let resolved_url = resolve_stream_url(&raw_url);

        if let Err(e) = Self::get_or_create_engine(&self.audio, &self.current_volume, &self.current_title) {
            error!("{}", e);
            notify("TiMonde", "Impossible d'initialiser l'audio");
            return;
        }

        {
            let guard = self.audio.lock().unwrap();
            if let Some(ref engine) = *guard {
                if let Err(e) = engine.play(&resolved_url) {
                    error!("Échec lecture flux éphémère : {}", e);
                    notify("TiMonde", &format!("Impossible de lancer {}", station_name));
                    return;
                }
            }
        }

        *self.current_station.lock().unwrap() = Some(station.clone());
        *self.current_title.lock().unwrap() = None;

        // Persistance de la station éphémère dans state.json (sans écraser la station habituelle)
        {
            let st_eph = station.clone();
            std::thread::spawn(move || {
                let mut state = crate::state::AppState::load(&crate::state::AppState::default_path());
                state.last_ephemeral = Some(st_eph);
                let _ = state.save(&crate::state::AppState::default_path());
            });
        }

        if let Some(time_info) = crate::timezone::get_local_time_for_station(station.country.as_deref(), &station_name, None, station.timezone.as_deref()) {
            let offset_sign = if time_info.offset_hours >= 0.0 { "+" } else { "" };
            crate::radio_browser::notify(
                "TiMonde • Découverte éphémère",
                &format!(
                    "{}
{} • {} (UTC{}{:.0}h)
Radio éphémère non enregistrée.",
                    station_name,
                    time_info.country_name,
                    time_info.formatted_time,
                    offset_sign,
                    time_info.offset_hours
                ),
            );
        } else {
            crate::radio_browser::notify(
                "TiMonde • Découverte éphémère",
                &format!(
                    "{}
Radio éphémère non enregistrée.",
                    station_name
                ),
            );
        }

        let handle_cell = Arc::clone(&self.tray_handle);
        std::thread::spawn(move || {
            if let Some(ref h) = *handle_cell.lock().unwrap() {
                h.update(|_| {});
            }
        });
    }

    /// Choisit une station au hasard dans le catalogue mondial et lance sa lecture éphémère
    pub fn play_random_ephemeral_station(&self) {
        let existing_urls: Vec<String> = {
            let root = self.root_group.lock().unwrap();
            let mut set = std::collections::HashSet::new();
            crate::import::collect_all_urls(&root, &mut set);
            set.into_iter().collect()
        };

        let picked = match crate::discovery::pick_random_station(&existing_urls) {
            Some(st) => st,
            None => {
                crate::radio_browser::notify(
                    "TiMonde",
                    "Impossible de trouver une station dans le catalogue des bouquets.",
                );
                return;
            }
        };

        self.play_ephemeral_station(picked);
    }

    /// Ouvre la boîte de dialogue pour enregistrer la radio éphémère courante dans les favoris
    pub fn trigger_save_current_ephemeral_station(&self) {
        let station_opt = self.current_station.lock().unwrap().clone();
        let station = match station_opt {
            Some(s) => s,
            None => {
                crate::radio_browser::notify("TiMonde", "Aucune radio n'est en cours d'écoute.");
                return;
            }
        };

        let root_group = Arc::clone(&self.root_group);
        let bookmarks_path = self.bookmarks_path.clone();
        let tray_handle = Arc::clone(&self.tray_handle);
        let is_ephemeral = Arc::clone(&self.is_ephemeral);
        let last_station = Arc::clone(&self.last_station);

        std::thread::spawn(move || {
            let all_groups: Vec<String> = {
                let guard = root_group.lock().unwrap();
                let mut list = Vec::new();
                guard.collect_all_group_paths("", &mut list);
                list
            };
            let groups_json = serde_json::to_string(&all_groups).unwrap_or_else(|_| "[]".to_string());
            let default_grp = all_groups.first().cloned().unwrap_or_else(|| "Sélection".to_string());

            let (new_name, new_url, new_country, new_timezone, new_target_group) = if let Some(script_path) = Self::find_edit_script() {
                let out = match std::process::Command::new(script_path)
                    .arg("--mode")
                    .arg("save-ephemeral")
                    .arg("--station-name")
                    .arg(&station.name)
                    .arg("--url")
                    .arg(&station.url)
                    .arg("--country")
                    .arg(station.country.as_deref().unwrap_or(""))
                    .arg("--timezone")
                    .arg(station.timezone.as_deref().unwrap_or(""))
                    .arg("--group")
                    .arg(&default_grp)
                    .arg("--groups-json")
                    .arg(&groups_json)
                    .output()
                {
                    Ok(o) if o.status.success() => o,
                    _ => return, // Annulé
                };

                let out_str = String::from_utf8_lossy(&out.stdout).trim().to_string();
                if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(&out_str) {
                    let n = json_val["name"].as_str().unwrap_or("").trim().to_string();
                    let u = json_val["url"].as_str().unwrap_or("").trim().to_string();
                    let c = json_val["country"]
                        .as_str()
                        .map(|s| s.trim().to_ascii_uppercase())
                        .filter(|s| !s.is_empty());
                    let tz = json_val["timezone"]
                        .as_str()
                        .map(|s| s.trim().to_string())
                        .filter(|s| !s.is_empty());
                    let g = json_val["group"].as_str().unwrap_or("").trim().to_string();
                    (n, u, c, tz, g)
                } else {
                    return;
                }
            } else {
                return;
            };

            if new_name.is_empty() || new_url.is_empty() {
                return;
            }

            let mut final_st = Station::new(&new_name, &new_url);
            final_st.country = new_country;
            final_st.timezone = new_timezone;

            let mut root = root_group.lock().unwrap().clone();
            match crate::import::add_station_to_group(
                &mut root,
                final_st.clone(),
                Some(&new_target_group),
            ) {
                Ok(msg) => {
                    if let Err(e) = crate::bookmarks::save_bookmarks(&root, &bookmarks_path) {
                        log::error!("Erreur lors de la sauvegarde : {}", e);
                        crate::radio_browser::notify("TiMonde", &format!("Erreur sauvegarde : {}", e));
                        return;
                    }

                    // Bascule de l'état : la radio est désormais pérenne dans les signets
                    is_ephemeral.store(false, Ordering::SeqCst);
                    *last_station.lock().unwrap() = Some(final_st.clone());

                    // Sauvegarder dans state.json
                    let st_saved = final_st.clone();
                    std::thread::spawn(move || {
                        let mut state = crate::state::AppState::load(&crate::state::AppState::default_path());
                        state.last_station = Some(st_saved);
                        let _ = state.save(&crate::state::AppState::default_path());
                    });

                    match Self::reload_bookmarks_and_update_tray(&root_group, &bookmarks_path, &tray_handle) {
                        Ok(total) => {
                            log::info!("{} (Total : {} stations)", msg, total);
                            crate::radio_browser::notify(
                                "TiMonde • Sauvegardée !",
                                &format!("« {} » conservée dans vos favoris ! (Total : {}).", final_st.name, total),
                            );
                        }
                        Err(e) => {
                            crate::radio_browser::notify("TiMonde", &format!("Station ajoutée mais erreur rechargement : {}", e));
                        }
                    }
                }
                Err(err) => {
                    log::warn!("Impossible de sauvegarder la station éphémère : {}", err);
                    crate::radio_browser::notify("TiMonde", &format!("Notice : {}", err));
                }
            }
        });
    }

    /// Programme une mise en veille automatique après un délai en minutes
    pub fn set_sleep_timer(&mut self, minutes: u64) {
        let dur = Duration::from_secs(minutes * 60);
        let target = std::time::Instant::now() + dur;
        *self.sleep_timer.lock().unwrap() = Some(target);

        let audio = Arc::clone(&self.audio);
        let current_station = Arc::clone(&self.current_station);
        let current_title = Arc::clone(&self.current_title);
        let sleep_timer = Arc::clone(&self.sleep_timer);
        let tray_handle = Arc::clone(&self.tray_handle);
        let gen = self.play_generation.load(Ordering::SeqCst);
        let play_gen = Arc::clone(&self.play_generation);

        notify("TiMonde", &format!("Minuteur activé : arrêt dans {} minutes", minutes));

        std::thread::spawn(move || {
            std::thread::sleep(dur);

            let mut guard = sleep_timer.lock().unwrap();
            if let Some(t) = *guard {
                if t <= std::time::Instant::now() {
                    *guard = None;
                    drop(guard);

                    if play_gen.load(Ordering::SeqCst) == gen {
                        Self::stop_and_trim_flow(&audio, &current_station, &current_title);
                        notify("TiMonde", "Minuteur écoulé : mise en veille et arrêt de la lecture.");
                        if let Some(ref h) = *tray_handle.lock().unwrap() {
                            h.update(|_| {});
                        }
                    }
                }
            }
        });
    }

    /// Annule la mise en veille programmée
    pub fn cancel_sleep_timer(&mut self) {
        *self.sleep_timer.lock().unwrap() = None;
        notify("TiMonde", "Minuteur de mise en veille annulé.");
    }

    /// Construit récursivement les éléments de menu pour un groupe donné
    /// Formate le libellé d une station dans le menu avec le drapeau national si étiqueté
    fn format_station_menu_label(station: &Station) -> String {
        if let Some((_, flag, _, _)) = crate::timezone::resolve_station_meta(station.country.as_deref(), &station.name, None, station.timezone.as_deref()) {
            format!("{} {}", flag, station.name)
        } else {
            station.name.clone()
        }
    }

    fn build_group_menu(group: &Group) -> Vec<MenuItem<Self>> {
        let mut items = Vec::new();

        for sub in &group.subgroups {
            if sub.is_separator() {
                let label = if let Some(title) = sub.separator_title() {
                    format!("─── {} ───", title)
                } else {
                    "────────────────────────".to_string()
                };
                let item = StandardItem {
                    label,
                    enabled: false,
                    visible: true,
                    ..Default::default()
                };
                items.push(MenuItem::Standard(item));
            } else {
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
        }

        if !group.subgroups.is_empty() && !group.stations.is_empty() {
            items.push(MenuItem::Separator);
        }

        for station in &group.stations {
            if station.is_separator() {
                let label = if let Some(title) = station.separator_title() {
                    format!("─── {} ───", title)
                } else {
                    "────────────────────────".to_string()
                };
                let item = StandardItem {
                    label,
                    enabled: false,
                    visible: true,
                    ..Default::default()
                };
                items.push(MenuItem::Standard(item));
            } else {
                let st_clone = station.clone();
                let item = StandardItem {
                    label: Self::format_station_menu_label(station),
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

    /// Ouvre la boîte de dialogue native pour ajouter une station manuellement
    pub fn trigger_add_station_dialog(
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    ) {
        std::thread::spawn(move || {
            let all_groups: Vec<String> = {
                let guard = root_group.lock().unwrap();
                let mut list = Vec::new();
                guard.collect_all_group_paths("", &mut list);
                list
            };
            let groups_json = serde_json::to_string(&all_groups).unwrap_or_else(|_| "[]".to_string());
            let default_grp = all_groups.first().cloned().unwrap_or_else(|| "Sélection".to_string());

            let (new_name, new_url, new_country, new_timezone, new_target_group) = if let Some(script_path) = Self::find_edit_script() {
                let out = match Self::prepare_python_command(&script_path)
                    .arg("--mode")
                    .arg("add")
                    .arg("--group")
                    .arg(&default_grp)
                    .arg("--groups-json")
                    .arg(&groups_json)
                    .output()
                {
                    Ok(o) if o.status.success() => o,
                    _ => return, // Annulé
                };

                let out_str = String::from_utf8_lossy(&out.stdout).trim().to_string();
                if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(&out_str) {
                    let n = json_val["name"].as_str().unwrap_or("").trim().to_string();
                    let u = json_val["url"].as_str().unwrap_or("").trim().to_string();
                    let c = json_val["country"]
                        .as_str()
                        .map(|s| s.trim().to_ascii_uppercase())
                        .filter(|s| !s.is_empty());
                    let tz = json_val["timezone"]
                        .as_str()
                        .map(|s| s.trim().to_string())
                        .filter(|s| !s.is_empty());
                    let g = json_val["group"].as_str().unwrap_or("").trim().to_string();
                    (n, u, c, tz, g)
                } else {
                    return;
                }
            } else {
                return;
            };

            if new_name.is_empty() || new_url.is_empty() {
                return;
            }

            let mut final_st = Station::new(&new_name, &new_url);
            final_st.country = new_country;
            final_st.timezone = new_timezone;

            let mut root = root_group.lock().unwrap().clone();
            match crate::import::add_station_to_group(
                &mut root,
                final_st.clone(),
                Some(&new_target_group),
            ) {
                Ok(msg) => {
                    if let Err(e) = crate::bookmarks::save_bookmarks(&root, &bookmarks_path) {
                        log::error!("Erreur lors de la sauvegarde : {}", e);
                        crate::radio_browser::notify("TiMonde", &format!("Erreur sauvegarde : {}", e));
                        return;
                    }
                    match Self::reload_bookmarks_and_update_tray(&root_group, &bookmarks_path, &tray_handle) {
                        Ok(total) => {
                            log::info!("{} (Total : {} stations)", msg, total);
                            crate::radio_browser::notify("TiMonde", &format!("{} (Total : {} stations)", msg, total));
                        }
                        Err(e) => {
                            crate::radio_browser::notify("TiMonde", &format!("Station ajoutée mais erreur rechargement : {}", e));
                        }
                    }
                }
                Err(e) => {
                    log::warn!("Échec de l ajout : {}", e);
                    crate::radio_browser::notify("TiMonde", &format!("Ajout impossible : {}", e));
                }
            }
        });
    }

    /// Recherche unifiée d un script Python compagnon (archive portable, deb/rpm, local ou dev)
    pub fn find_script(script_name: &str) -> Option<PathBuf> {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());

        // 1. Relatif au binaire en cours d exécution (archive portable .tar.gz)
        if let Ok(exe) = std::env::current_exe() {
            if let Some(exe_dir) = exe.parent() {
                let candidate_share = exe_dir.join("../share/timonde/scripts").join(script_name);
                if candidate_share.exists() {
                    return Some(candidate_share);
                }
                let candidate_scripts = exe_dir.join("scripts").join(script_name);
                if candidate_scripts.exists() {
                    return Some(candidate_scripts);
                }
                let candidate_parent_scripts = exe_dir.join("../scripts").join(script_name);
                if candidate_parent_scripts.exists() {
                    return Some(candidate_parent_scripts);
                }
                let candidate_rel_data = exe_dir.join("data/scripts").join(script_name);
                if candidate_rel_data.exists() {
                    return Some(candidate_rel_data);
                }
                let candidate_parent_data = exe_dir.join("../data/scripts").join(script_name);
                if candidate_parent_data.exists() {
                    return Some(candidate_parent_data);
                }
            }
        }

        // 2. Emplacement système officiel du paquet (.deb, .rpm)
        let sys_share = PathBuf::from("/usr/share/timonde/scripts").join(script_name);
        if sys_share.exists() {
            return Some(sys_share);
        }
        let local_sys_share = PathBuf::from("/usr/local/share/timonde/scripts").join(script_name);
        if local_sys_share.exists() {
            return Some(local_sys_share);
        }

        // 3. Emplacement utilisateur XDG ~/.local/share/timonde/scripts/
        let user_share = PathBuf::from(&home).join(".local/share/timonde/scripts").join(script_name);
        if user_share.exists() {
            return Some(user_share);
        }

        // 4. Dossier relatif au répertoire courant de travail
        let dev_path = PathBuf::from("data/scripts").join(script_name);
        if dev_path.exists() {
            return Some(dev_path);
        }

        None
    }

    fn prepare_python_command<P: AsRef<std::path::Path>>(program: P) -> std::process::Command {
        let mut cmd = std::process::Command::new(program.as_ref());
        // Neutralisation absolue de variables de méthodes de saisie orphelines (ex: socket IBus manquante)
        // qui bloquent la saisie des touches clavier dans GTK3.
        cmd.env_remove("GTK_IM_MODULE");
        cmd.env_remove("XMODIFIERS");
        cmd.env_remove("QT_IM_MODULE");
        cmd
    }

    fn find_edit_script() -> Option<PathBuf> {
        Self::find_script("edit_station.py")
    }

    /// Ouvre la boîte de dialogue pour modifier le nom, l'URL, le groupe et le code pays de la station
    pub fn trigger_edit_station_dialog(
        station: Station,
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
        current_station: Arc<Mutex<Option<Station>>>,
        last_station: Arc<Mutex<Option<Station>>>,
        audio: Arc<Mutex<Option<AudioEngine>>>,
        current_title: Arc<Mutex<Option<String>>>,
    ) {
        std::thread::spawn(move || {
            // Rapatriement infaillible de la station réelle dans les signets par son URL
            let (real_name, real_country, real_tz) = {
                let guard = root_group.lock().unwrap();
                if let Some(found) = Self::find_station_by_url(&guard, &station.url) {
                    (
                        if station.name.trim().is_empty() { found.name } else { station.name.clone() },
                        station.country.clone().or(found.country),
                        station.timezone.clone().or(found.timezone),
                    )
                } else {
                    (station.name.clone(), station.country.clone(), station.timezone.clone())
                }
            };

            let current_group_name = {
                let guard = root_group.lock().unwrap();
                Self::find_group_name_for_station(&guard, &station.url)
            }.unwrap_or_else(|| "Sélection".to_string());

            let all_groups: Vec<String> = {
                let guard = root_group.lock().unwrap();
                let mut list = Vec::new();
                guard.collect_all_group_paths("", &mut list);
                list
            };
            let groups_json = serde_json::to_string(&all_groups).unwrap_or_else(|_| "[]".to_string());

            let deduced_country = if let Some(ref c) = real_country {
                c.clone()
            } else {
                crate::timezone::get_local_time_for_station(None, &real_name, Some(&current_group_name), real_tz.as_deref())
                    .map(|t| t.country_code)
                    .unwrap_or_default()
            };

            let deduced_tz = if let Some(ref tz) = real_tz {
                tz.clone()
            } else {
                crate::timezone::get_local_time_for_station(Some(&deduced_country), &real_name, Some(&current_group_name), None)
                    .map(|t| t.timezone)
                    .unwrap_or_default()
            };

            let (new_name, new_url, new_country, new_timezone, new_target_group) = if let Some(script_path) = Self::find_edit_script() {
                let out = match Self::prepare_python_command(&script_path)
                    .arg("--mode")
                    .arg("edit")
                    .arg("--station-name")
                    .arg(&real_name)
                    .arg("--url")
                    .arg(&station.url)
                    .arg("--country")
                    .arg(&deduced_country)
                    .arg("--timezone")
                    .arg(&deduced_tz)
                    .arg("--group")
                    .arg(&current_group_name)
                    .arg("--groups-json")
                    .arg(&groups_json)
                    .output()
                {
                    Ok(o) if o.status.success() => o,
                    _ => return, // Annulé
                };

                let out_str = String::from_utf8_lossy(&out.stdout).trim().to_string();
                if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(&out_str) {
                    if json_val["action"].as_str() == Some("delete") {
                        let mut root = root_group.lock().unwrap().clone();
                        let target_url = json_val["url"].as_str().unwrap_or(&station.url);
                        if crate::bookmarks::remove_station_by_url(&mut root, target_url) {
                            let _ = crate::bookmarks::save_bookmarks(&root, &bookmarks_path);
                            *root_group.lock().unwrap() = root;
                        }
                        let is_current = {
                            let cur = current_station.lock().unwrap();
                            cur.as_ref().map(|c| crate::import::normalize_url(&c.url) == crate::import::normalize_url(&station.url)).unwrap_or(false)
                        };
                        if is_current {
                            Self::stop_and_trim_flow(&audio, &current_station, &current_title);
                        }
                        {
                            let mut last = last_station.lock().unwrap();
                            if last.as_ref().map(|l| crate::import::normalize_url(&l.url) == crate::import::normalize_url(&station.url)).unwrap_or(false) {
                                *last = None;
                                let mut state = crate::state::AppState::load(&crate::state::AppState::default_path());
                                state.last_station = None;
                                let _ = state.save(&crate::state::AppState::default_path());
                            }
                        }
                        crate::radio_browser::notify("TiMonde", &format!("Station « {} » supprimée de vos favoris.", station.name));
                        if let Some(ref h) = *tray_handle.lock().unwrap() {
                            h.update(|_| {});
                        }
                        return;
                    }

                    let n = json_val["name"].as_str().unwrap_or("").trim().to_string();
                    let u = json_val["url"].as_str().unwrap_or("").trim().to_string();
                    let c = json_val["country"]
                        .as_str()
                        .map(|s| s.trim().to_ascii_uppercase())
                        .filter(|s| !s.is_empty());
                    let tz = json_val["timezone"]
                        .as_str()
                        .map(|s| s.trim().to_string())
                        .filter(|s| !s.is_empty());
                    let g = json_val["group"].as_str().unwrap_or("").trim().to_string();
                    (n, u, Some(c), Some(tz), g)
                } else {
                    return;
                }
            } else {
                log::warn!("Script edit_station.py introuvable pour modifier la radio");
                return;
            };

            if new_name.is_empty() || new_url.is_empty() {
                return;
            }

            let mut root = root_group.lock().unwrap().clone();

            // Si le groupe a changé, transférer vers le nouveau groupe (ou racine)
            let norm_new = new_target_group.trim().trim_matches('/');
            let norm_cur = current_group_name.trim().trim_matches('/');
            let group_changed = !norm_new.eq_ignore_ascii_case(norm_cur);

            if group_changed {
                let _ = crate::bookmarks::remove_station_by_url(&mut root, &station.url);
                let mut new_st = Station::new(&new_name, &new_url);
                if let Some(ref nc) = new_country {
                    new_st.country = nc.clone();
                }
                if let Some(ref ntz) = new_timezone {
                    new_st.timezone = ntz.clone();
                }
                let target_opt = if norm_new.is_empty() || norm_new.eq_ignore_ascii_case("root") {
                    None
                } else {
                    Some(norm_new)
                };
                let _ = crate::import::add_station_to_group(&mut root, new_st, target_opt);
            } else {
                let _ = crate::bookmarks::update_station_full(
                    &mut root,
                    &station.url,
                    &new_name,
                    &new_url,
                    new_country.clone(),
                    new_timezone.clone(),
                );
            }

            if let Err(e) = crate::bookmarks::save_bookmarks(&root, &bookmarks_path) {
                log::error!("Erreur sauvegarde : {}", e);
                crate::radio_browser::notify("TiMonde", &format!("Erreur sauvegarde : {}", e));
                return;
            }

            // Mettre à jour current_station si elle était en cours
            {
                let mut cur = current_station.lock().unwrap();
                if let Some(ref mut c) = *cur {
                    if crate::import::normalize_url(&c.url) == crate::import::normalize_url(&station.url) || c.name == station.name {
                        c.name = new_name.clone();
                        c.url = new_url.clone();
                        if let Some(nc) = &new_country {
                            c.country = nc.clone();
                        }
                        if let Some(ntz) = &new_timezone {
                            c.timezone = ntz.clone();
                        }
                    }
                }
            }
            {
                let mut last = last_station.lock().unwrap();
                if let Some(ref mut l) = *last {
                    if crate::import::normalize_url(&l.url) == crate::import::normalize_url(&station.url) || l.name == station.name {
                        l.name = new_name.clone();
                        l.url = new_url.clone();
                        if let Some(nc) = &new_country {
                            l.country = nc.clone();
                        }
                        if let Some(ntz) = &new_timezone {
                            l.timezone = ntz.clone();
                        }
                        if let Some(nc) = &new_country {
                            l.country = nc.clone();
                        }
                    }
                }
            }

            let _ = Self::reload_bookmarks_and_update_tray(&root_group, &bookmarks_path, &tray_handle);
            log::info!("Station modifiée : {} -> {}", station.name, new_name);
            crate::radio_browser::notify("TiMonde", &format!("Station « {} » mise à jour avec succès !", new_name));
        });
    }

    fn find_bouquets_script() -> Option<PathBuf> {
        Self::find_script("browse_bouquets.py")
    }

    /// Découverte et importation de bouquets (Nationaux & Régionaux) sans doublons
    pub fn trigger_browse_bouquets_dialog(
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
        initial_tab: Option<usize>,
    ) {
        std::thread::spawn(move || {
            let (existing_stations, available_groups) = {
                let guard = root_group.lock().unwrap();
                let mut list = Vec::new();
                fn collect(g: &Group, acc: &mut Vec<serde_json::Value>) {
                    for s in &g.stations {
                        if !s.is_separator() {
                            acc.push(serde_json::json!({
                                "name": s.name,
                                "url": s.url,
                            }));
                        }
                    }
                    for sub in &g.subgroups {
                        collect(sub, acc);
                    }
                }
                collect(&guard, &mut list);
                let mut grps = Vec::new();
                guard.collect_all_group_paths("", &mut grps);
                (list, grps)
            };

            let script_path = match Self::find_bouquets_script() {
                Some(p) => p,
                None => {
                    log::error!("Script browse_bouquets.py introuvable");
                    crate::radio_browser::notify("TiMonde", "Outil de bouquets introuvable");
                    return;
                }
            };

            let payload = serde_json::json!({
                "stations": existing_stations,
                "groups": available_groups,
            });

            let json_input = match serde_json::to_string(&payload) {
                Ok(s) => s,
                Err(e) => {
                    log::error!("Erreur sérialisation json : {}", e);
                    return;
                }
            };

            let mut cmd = Self::prepare_python_command("python3");
            cmd.arg(&script_path);
            if let Some(tab) = initial_tab {
                cmd.arg(format!("--tab={}", tab));
            }
            let mut child = match cmd
                .stdin(std::process::Stdio::piped())
                .stdout(std::process::Stdio::piped())
                .spawn()
            {
                Ok(c) => c,
                Err(e) => {
                    log::error!("Impossible d'exécuter python3 : {}", e);
                    crate::radio_browser::notify("TiMonde", "Impossible d'ouvrir l'outil de bouquets");
                    return;
                }
            };

            if let Some(mut stdin) = child.stdin.take() {
                use std::io::Write;
                let _ = stdin.write_all(json_input.as_bytes());
            }

            let output = match child.wait_with_output() {
                Ok(out) => out,
                Err(_) => return,
            };

            if output.status.success() {
                let stdout_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
                log::info!("Script browse_bouquets terminé avec succès. Longueur stdout: {}", stdout_str.len());

                #[derive(serde::Deserialize)]
                struct InStation {
                    name: String,
                    url: String,
                    #[serde(default)]
                    country: Option<String>,
                    #[serde(default)]
                    group: Option<String>,
                }
                #[derive(serde::Deserialize)]
                struct InResult {
                    group_name: String,
                    #[serde(default)]
                    country_code: Option<String>,
                    stations: Vec<InStation>,
                    #[serde(default)]
                    all_bouquet_stations: Vec<InStation>,
                }

                match serde_json::from_str::<InResult>(&stdout_str) {
                    Ok(res) => {
                    let mut guard = root_group.lock().unwrap();
                    let mut enriched_count = 0;

                    // 1. Enrichir automatiquement les stations existantes avec le code pays
                    if let Some(c_code) = &res.country_code {
                        if !c_code.is_empty() {
                            for b_st in &res.all_bouquet_stations {
                                if guard.enrich_station_country(&b_st.name, &b_st.url, c_code) {
                                    enriched_count += 1;
                                }
                            }
                            // Enrichir aussi à partir des stations sélectionnées
                            for s in &res.stations {
                                if guard.enrich_station_country(&s.name, &s.url, c_code) {
                                    enriched_count += 1;
                                }
                            }
                        }
                    }

                    // 2. Ajouter les nouvelles stations dans les groupes cibles (avec support hiérarchique)
                    let mut added = 0;
                    if !res.stations.is_empty() {
                        for st in res.stations {
                            let target_path = match &st.group {
                                Some(g) if !g.trim().is_empty() && g.trim() != "root" && g.trim() != "/" => g.trim().to_string(),
                                _ => res.group_name.clone(),
                            };

                            let clean_path = target_path.trim().trim_matches('/');
                            let target_grp = if clean_path.is_empty() || clean_path.eq_ignore_ascii_case("root") {
                                &mut *guard
                            } else {
                                Self::get_or_create_subgroup_hierarchy(&mut guard, clean_path)
                            };

                            if !target_grp.stations.iter().any(|s| s.url == st.url || s.name == st.name) {
                                let station_item = if let Some(c) = st.country.as_deref().or(res.country_code.as_deref()) {
                                    Station::with_country(st.name, st.url, c)
                                } else {
                                    Station::new(st.name, st.url)
                                };
                                target_grp.stations.push(station_item);
                                added += 1;
                            }
                        }
                    }

                    if added > 0 || enriched_count > 0 {
                        if let Err(e) = crate::bookmarks::save_bookmarks(&guard, &bookmarks_path) {
                            log::error!("Erreur sauvegarde signets : {}", e);
                            crate::radio_browser::notify("TiMonde", &format!("Erreur sauvegarde : {}", e));
                            return;
                        }
                    }
                    drop(guard);

                    let total = Self::reload_bookmarks_and_update_tray(&root_group, &bookmarks_path, &tray_handle).unwrap_or(0);
                    let country_msg = res.country_code.map(|c| format!(" [{}]", c)).unwrap_or_default();
                    crate::radio_browser::notify(
                        "TiMonde",
                        &format!(
                            "{} radio(s) ajoutée(s), {} existante(s) étiquetée(s){} !\nTotal : {} stations.",
                            added, enriched_count, country_msg, total
                        ),
                    );
                    }
                    Err(e) => {
                        log::error!("Erreur désérialisation JSON bouquet: {}, brut: {}", e, stdout_str);
                    }
                }
            }
        });
    }

    fn get_or_create_subgroup_hierarchy<'a>(mut current: &'a mut Group, path: &str) -> &'a mut Group {
        for part in path.split('/') {
            let clean = part.trim();
            if clean.is_empty() || clean.eq_ignore_ascii_case("root") {
                continue;
            }
            let pos = if let Some(idx) = current.subgroups.iter().position(|g| g.name.eq_ignore_ascii_case(clean)) {
                idx
            } else {
                current.subgroups.push(Group::new(clean));
                current.subgroups.len() - 1
            };
            current = &mut current.subgroups[pos];
        }
        current
    }

    fn find_first_station(group: &Group) -> Option<Station> {
        for s in &group.stations {
            if !s.is_separator() {
                return Some(s.clone());
            }
        }
        for sub in &group.subgroups {
            if let Some(s) = Self::find_first_station(sub) {
                return Some(s);
            }
        }
        None
    }

    fn find_reorder_script() -> Option<PathBuf> {
        Self::find_script("reorder_groups.py")
    }

    /// Exportation des radios en CSV via boîte de dialogue GTK3
    pub fn trigger_export_csv_dialog(
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    ) {
        Self::trigger_reorder_groups_dialog_with_arg(
            root_group,
            bookmarks_path,
            tray_handle,
            Some("--export"),
        );
    }

    /// Réorganisation ergonomique des groupes et des radios via fenêtre GTK3 dédiée (Option 1 BB)
    pub fn trigger_reorder_groups_dialog(
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
        auto_check: bool,
    ) {
        Self::trigger_reorder_groups_dialog_with_arg(
            root_group,
            bookmarks_path,
            tray_handle,
            if auto_check { Some("--check") } else { None },
        );
    }

    /// Lance l'outil de gestion avec un argument supplémentaire optionnel (--check ou --export)
    pub fn trigger_reorder_groups_dialog_with_arg(
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
        extra_arg: Option<&'static str>,
    ) {
        std::thread::spawn(move || {
            let groups_payload: Vec<serde_json::Value> = {
                let guard = root_group.lock().unwrap();
                if guard.subgroups.is_empty() {
                    crate::radio_browser::notify("TiMonde", "Aucun groupe de radios à classer");
                    return;
                }
                let mut payload = Vec::new();

                fn collect_payload(group: &Group, prefix: &str, out: &mut Vec<serde_json::Value>) {
                    for g in &group.subgroups {
                        if g.is_separator() {
                            out.push(serde_json::json!({
                                "name": g.separator_title().unwrap_or_default(),
                                "stations": [],
                                "is_separator": true,
                            }));
                        } else {
                            let full_path = if prefix.is_empty() {
                                g.name.clone()
                            } else {
                                format!("{}/{}", prefix, g.name)
                            };

                            let stations_json: Vec<serde_json::Value> = g
                                .stations
                                .iter()
                                .map(|s| {
                                    if s.is_separator() {
                                        serde_json::json!({
                                            "name": s.separator_title().unwrap_or_default(),
                                            "url": "",
                                            "is_separator": true,
                                        })
                                    } else {
                                        serde_json::json!({
                                            "name": s.name,
                                            "url": s.url,
                                            "country": s.country,
                                            "timezone": s.timezone,
                                            "is_separator": false,
                                        })
                                    }
                                })
                                .collect();

                            out.push(serde_json::json!({
                                "name": full_path,
                                "stations": stations_json,
                                "is_separator": false,
                            }));

                            // Récursion pour explorer tous les sous-groupes enfants (ex: France/Bretagne, Country/Bluegrass)
                            collect_payload(g, &full_path, out);
                        }
                    }
                }

                collect_payload(&guard, "", &mut payload);
                payload
            };

            let script_path = match Self::find_reorder_script() {
                Some(p) => p,
                None => {
                    log::error!("Script reorder_groups.py introuvable");
                    crate::radio_browser::notify("TiMonde", "Outil de réorganisation introuvable");
                    return;
                }
            };

            let json_input = match serde_json::to_string(&groups_payload) {
                Ok(s) => s,
                Err(e) => {
                    log::error!("Erreur sérialisation json : {}", e);
                    return;
                }
            };

            let mut cmd = Self::prepare_python_command("python3");
            cmd.arg(&script_path);
            if let Some(arg) = extra_arg {
                cmd.arg(arg);
            }
            let mut child = match cmd
                .stdin(std::process::Stdio::piped())
                .stdout(std::process::Stdio::piped())
                .spawn()
            {
                Ok(c) => c,
                Err(e) => {
                    log::error!("Impossible d'exécuter python3 : {}", e);
                    crate::radio_browser::notify("TiMonde", "Impossible d'ouvrir l'outil de réorganisation");
                    return;
                }
            };

            if let Some(mut stdin) = child.stdin.take() {
                use std::io::Write;
                let _ = stdin.write_all(json_input.as_bytes());
            }

            let output = match child.wait_with_output() {
                Ok(out) => out,
                Err(_) => return,
            };

            // Si code 0 : l'utilisateur a cliqué sur "Enregistrer et recharger"
            if output.status.success() {
                let stdout_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
                log::info!("Script browse_bouquets terminé avec succès. Longueur stdout: {}", stdout_str.len());
                
                #[derive(serde::Deserialize)]
                struct OutStation {
                    name: String,
                    #[serde(default)]
                    url: String,
                    #[serde(default)]
                    country: Option<String>,
                    #[serde(default)]
                    timezone: Option<String>,
                    #[serde(default)]
                    is_separator: bool,
                }
                #[derive(serde::Deserialize)]
                struct OutGroup {
                    name: String,
                    #[serde(default)]
                    stations: Vec<OutStation>,
                    #[serde(default)]
                    is_separator: bool,
                }

                let new_data: Vec<OutGroup> = match serde_json::from_str(&stdout_str) {
                    Ok(d) => d,
                    Err(e) => {
                        log::error!("Erreur désérialisation du nouvel ordre : {}", e);
                        return;
                    }
                };

                let mut old_root = root_group.lock().unwrap().clone();
                let mut new_root = Group::new("root");
                new_root.stations = old_root.stations.clone();

                for g_data in new_data {
                    if g_data.is_separator || g_data.name.starts_with("---") {
                        new_root.subgroups.push(Group::separator(g_data.name));
                        continue;
                    }

                    let clean_grp_name = g_data.name.trim();
                    if clean_grp_name.is_empty() {
                        continue;
                    }

                    // Réordonner ou transférer les stations et séparateurs selon les actions de l'utilisateur
                    let mut new_stations = Vec::new();
                    for s_data in g_data.stations {
                        if s_data.is_separator || s_data.url.is_empty() {
                            new_stations.push(Station::separator(s_data.name));
                        } else {
                            // Recherche dans toute l'ancienne hiérarchie pour préserver le pays, timezone, etc.
                            let st = if let Some(mut existing) = old_root.remove_station_from_tree(&s_data.url, &s_data.name) {
                                existing.name = s_data.name;
                                if !s_data.url.is_empty() {
                                    existing.url = s_data.url;
                                }
                                if s_data.country.is_some() {
                                    existing.country = s_data.country;
                                }
                                if s_data.timezone.is_some() {
                                    existing.timezone = s_data.timezone;
                                }
                                existing
                            } else {
                                let mut s = Station::new(&s_data.name, &s_data.url);
                                s.country = s_data.country;
                                s.timezone = s_data.timezone;
                                s
                            };
                            new_stations.push(st);
                        }
                    }

                    let target_grp = new_root.get_or_create_subgroup_hierarchy(clean_grp_name);
                    target_grp.stations = new_stations;
                }

                if let Err(e) = crate::bookmarks::save_bookmarks(&new_root, &bookmarks_path) {
                    log::error!("Erreur sauvegarde : {}", e);
                    crate::radio_browser::notify("TiMonde", &format!("Erreur sauvegarde : {}", e));
                    return;
                }

                *root_group.lock().unwrap() = new_root;
                let count = Self::reload_bookmarks_and_update_tray(&root_group, &bookmarks_path, &tray_handle).unwrap_or(0);
                log::info!("Ordre des groupes et radios enregistré et signets rechargés !");
                crate::radio_browser::notify(
                    "TiMonde",
                    &format!("Organisation mise à jour ({} radios rechargées)", count),
                );
            }
        });
    }

    /// Chemin du fichier XDG Autostart pour TiMonde
    pub fn autostart_file_path() -> PathBuf {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(home).join(".config/autostart/timonde.desktop")
    }

    /// Vérifie si le lancement automatique au démarrage de session est activé
    pub fn is_autostart_enabled() -> bool {
        Self::autostart_file_path().exists()
    }

    /// Active ou désactive le lancement automatique au démarrage
    pub fn toggle_autostart() -> bool {
        let path = Self::autostart_file_path();
        if path.exists() {
            let _ = std::fs::remove_file(&path);
            log::info!("Démarrage automatique désactivé (fichier supprimé: {:?})", path);
            false
        } else {
            if let Some(parent) = path.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            let desktop_content = "[Desktop Entry]\n\
Type=Application\n\
Name=TiMonde\n\
GenericName=Radio Tray Player\n\
Comment=Lecteur de radios ultra-léger pour la zone de notification\n\
Exec=timonde\n\
Icon=timonde_on\n\
Terminal=false\n\
Categories=AudioVideo;Audio;Player;\n\
StartupNotify=false\n\
X-GNOME-Autostart-enabled=true\n";
            let _ = std::fs::write(&path, desktop_content);
            log::info!("Démarrage automatique activé (fichier créé: {:?})", path);
            true
        }
    }
}

impl ksni::Tray for TiMondeTray {
    const MENU_ON_ACTIVATE: bool = true;

    fn activate(&mut self, _x: i32, _y: i32) {
        log::info!("Clic gauche sur l'icône de la barre des tâches");
        if self.state() == PlaybackState::Playing {
            log::info!("Clic gauche : bascule vers Arrêt : bascule vers Arrêt");
            Self::stop_and_trim_flow(&self.audio, &self.current_station, &self.current_title);
            if let Some(ref h) = *self.tray_handle.lock().unwrap() {
                h.update(|_| {});
            }
        } else {
            let target_station = {
                let cur = self.current_station.lock().unwrap();
                let last = self.last_station.lock().unwrap();
                cur.clone().or_else(|| last.clone())
            };

            let station_to_play = if let Some(st) = target_station {
                Some(st)
            } else {
                let root = self.root_group.lock().unwrap();
                Self::find_first_station(&root)
            };

            if let Some(st) = station_to_play {
                log::info!("Clic gauche : lecture : lecture de « {} »", st.name);
                Self::play_station_flow(
                    st,
                    &self.audio,
                    &self.current_volume,
                    &self.current_station,
                    &self.last_station,
                    &self.current_title,
                    &self.play_generation,
                    &self.root_group,
                    &self.bookmarks_path,
                );
                if let Some(ref h) = *self.tray_handle.lock().unwrap() {
                    h.update(|_| {});
                }
            } else {
                Self::trigger_browse_bouquets_dialog(
                    Arc::clone(&self.root_group),
                    self.bookmarks_path.clone(),
                    Arc::clone(&self.tray_handle),
                    None,
                );
            }
        }
    }

    fn id(&self) -> String {
        "timonde".to_string()
    }

    fn title(&self) -> String {
        let cur_st = self.current_station.lock().unwrap();
        match (cur_st.as_ref(), self.state()) {
            (Some(st), PlaybackState::Playing) => {
                let cur_title = self.current_title.lock().unwrap();
                let time_str = crate::timezone::get_local_time_for_station(st.country.as_deref(), &st.name, None, st.timezone.as_deref())
                    .map(|t| format!(" • {} {} ({})", t.icon, t.formatted_time, t.relative_badge()))
                    .unwrap_or_default();
                if let Some(ref t) = *cur_title {
                    format!("{} - {}{}", st.name, t, time_str)
                } else {
                    format!("{}{}", st.name, time_str)
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
        for candidate in &[
            "/usr/share/icons/hicolor/24x24/panel",
            "/usr/share/icons/hicolor/22x22/panel",
            "/usr/share/icons/hicolor/24x24/apps",
            "/usr/share/icons/hicolor/scalable/panel",
            "/usr/share/icons/hicolor/scalable/apps",
        ] {
            if std::path::Path::new(candidate).exists() {
                return candidate.to_string();
            }
        }
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        let local_icons = format!("{}/.local/share/icons/hicolor/24x24/panel", home);
        if std::path::Path::new(&local_icons).exists() {
            local_icons
        } else {
            let project_icons = concat!(env!("CARGO_MANIFEST_DIR"), "/data/icons");
            project_icons.to_string()
        }
    }

    /// Clic du milieu (molette) sur l'icône : Bouton Marche/Arrêt instantané façon Hi-Fi
    fn secondary_activate(&mut self, _x: i32, _y: i32) {
        if self.state() == PlaybackState::Playing || self.state() == PlaybackState::Buffering {
            self.stop_and_trim();
        } else {
            let station_to_turn_on = {
                let last = self.last_station.lock().unwrap();
                if let Some(ref last_st) = *last {
                    Some(last_st.clone())
                } else {
                    let root = self.root_group.lock().unwrap();
                    Self::find_first_station(&root)
                }
            };
            if let Some(st) = station_to_turn_on {
                self.play_station(st);
            }
        }
    }

    /// Défilement de la molette sur l'icône de la barre des tâches : Ajustement direct du volume
    fn scroll(&mut self, delta: i32, _orientation: ksni::Orientation) {
        let step = if delta > 0 { -0.05 } else { 0.05 };
        let mut cur = self.current_volume.lock().unwrap();
        let new_vol = (*cur + step).clamp(0.0, 1.0);
        *cur = new_vol;
        let guard = self.audio.lock().unwrap();
        if let Some(ref engine) = *guard {
            engine.set_volume(new_vol);
        }
    }

    fn menu(&self) -> Vec<MenuItem<Self>> {
        let mut menu = Vec::new();
        let current_state = self.state();

        // 1. Bouton principal Marche / Arrêt / Connexion en tête du menu
        let is_eph = self.is_ephemeral.load(Ordering::SeqCst);
        let cur_st = self.current_station.lock().unwrap();
        let cur_title = self.current_title.lock().unwrap();

        match cur_st.as_ref() {
            Some(st) if current_state == PlaybackState::Buffering => {
                let label = crate::i18n::connecting_station_label(&st.name, is_eph);
                menu.push(MenuItem::Standard(StandardItem {
                    label,
                    activate: Box::new(|tray: &mut Self| {
                        tray.stop_and_trim();
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
            }
            Some(st) => {
                let label = crate::i18n::stop_station_label(&st.name, is_eph);
                menu.push(MenuItem::Standard(StandardItem {
                    label,
                    activate: Box::new(|tray: &mut Self| {
                        tray.stop_and_trim();
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
            }
            None => {
                let station_to_turn_on = {
                    let last = self.last_station.lock().unwrap();
                    if let Some(ref last_st) = *last {
                        Some(last_st.clone())
                    } else {
                        let root = self.root_group.lock().unwrap();
                        Self::find_first_station(&root)
                    }
                };

                if let Some(st) = station_to_turn_on {
                    let st_clone = st.clone();
                    let label = crate::i18n::play_station_label(&st.name);
                    menu.push(MenuItem::Standard(StandardItem {
                        label,
                        activate: Box::new(move |tray: &mut Self| {
                            tray.play_station(st_clone.clone());
                        }),
                        enabled: true,
                        visible: true,
                        ..Default::default()
                    }));
                } else {
                    menu.push(MenuItem::Standard(StandardItem {
                        label: crate::i18n::tr("Play").to_string(),
                        enabled: false,
                        visible: true,
                        ..Default::default()
                    }));
                }
            }
        }

        // 2. Actions et informations contextuelles sur la station active
        if let Some(ref st) = *cur_st {
                let group_name = {
                    let guard = self.root_group.lock().unwrap();
                    Self::find_group_name_for_station(&guard, &st.url)
                };

                // Ligne d'heure locale & décalage (non-cliquable)
                if let Some(time_info) = crate::timezone::get_local_time_for_station(st.country.as_deref(), &st.name, group_name.as_deref(), st.timezone.as_deref()) {
                    let offset_str = if time_info.offset_hours >= 0.0 {
                        format!("+{}", time_info.offset_hours)
                    } else {
                        format!("{}", time_info.offset_hours)
                    };
                    let date_tag = if !time_info.day_diff_label.is_empty() {
                        format!(" ({})", time_info.day_diff_label)
                    } else {
                        String::new()
                    };
                    let info_label = format!(
                        "[{}] {} • {}{} • Décalage : {} (UTC{})",
                        time_info.country_code,
                        time_info.country_name,
                        time_info.formatted_time,
                        date_tag,
                        time_info.user_diff_label,
                        offset_str
                    );
                    menu.push(MenuItem::Standard(StandardItem {
                        label: info_label,
                        enabled: false,
                        visible: true,
                        ..Default::default()
                    }));
                }

                // Ligne du titre du morceau en cours (non-cliquable)
                if let Some(ref title) = *cur_title {
                    if !title.trim().is_empty() {
                        menu.push(MenuItem::Standard(StandardItem {
                            label: title.trim().to_string(),
                            enabled: false,
                            visible: true,
                            ..Default::default()
                        }));
                    }
                }

                // Boutons d'action : Édition (qui inclut la suppression) ou découverte éphémère
                if is_eph {
                    let st_name = st.name.clone();
                    menu.push(MenuItem::Standard(StandardItem {
                        label: crate::i18n::save_ephemeral_label(&st_name),
                        activate: Box::new(|tray: &mut Self| {
                            tray.trigger_save_current_ephemeral_station();
                        }),
                        enabled: true,
                        visible: true,
                        ..Default::default()
                    }));

                    menu.push(MenuItem::Standard(StandardItem {
                        label: crate::i18n::tr("Zap to another random station").to_string(),
                        activate: Box::new(|tray: &mut Self| {
                            tray.play_random_ephemeral_station();
                        }),
                        enabled: true,
                        visible: true,
                        ..Default::default()
                    }));
                } else {
                    let st_edit = st.clone();
                    menu.push(MenuItem::Standard(StandardItem {
                        label: crate::i18n::tr("Edit").to_string(),
                        activate: Box::new(move |tray: &mut Self| {
                            Self::trigger_edit_station_dialog(
                                st_edit.clone(),
                                Arc::clone(&tray.root_group),
                                tray.bookmarks_path.clone(),
                                Arc::clone(&tray.tray_handle),
                                Arc::clone(&tray.current_station),
                                Arc::clone(&tray.last_station),
                                Arc::clone(&tray.audio),
                                Arc::clone(&tray.current_title),
                            );
                        }),
                        enabled: true,
                        visible: true,
                        ..Default::default()
                    }));
                }
        }

        drop(cur_st);
        drop(cur_title);

        menu.push(MenuItem::Separator);

        // Découverte éphémère d'une radio au hasard (affiché uniquement si aucune radio éphémère n'est déjà en cours d'écoute)
        if !is_eph {
            menu.push(MenuItem::Standard(StandardItem {
                label: crate::i18n::tr("Play random radio (Ephemeral discovery)").to_string(),
                activate: Box::new(|tray: &mut Self| {
                    tray.play_random_ephemeral_station();
                }),
                enabled: true,
                visible: true,
                ..Default::default()
            }));

            menu.push(MenuItem::Separator);
        }

        // 3. Arborescence des radios (le niveau "root" est déjà épuré au chargement)
        let root_group = self.root_group.lock().unwrap();

        for sub in &root_group.subgroups {
            if sub.is_separator() {
                let label = if let Some(title) = sub.separator_title() {
                    format!("─── {} ───", title)
                } else {
                    "────────────────────────".to_string()
                };
                menu.push(MenuItem::Standard(StandardItem {
                    label,
                    enabled: false,
                    visible: true,
                    ..Default::default()
                }));
            } else {
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
        }

        for st in &root_group.stations {
            if st.is_separator() {
                let label = if let Some(title) = st.separator_title() {
                    format!("─── {} ───", title)
                } else {
                    "────────────────────────".to_string()
                };
                menu.push(MenuItem::Standard(StandardItem {
                    label,
                    enabled: false,
                    visible: true,
                    ..Default::default()
                }));
            } else {
                let st_clone = st.clone();
                menu.push(MenuItem::Standard(StandardItem {
                    label: Self::format_station_menu_label(st),
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
            label: format!("Volume ({vol_percent}%)"),
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
                    label: crate::i18n::tr("Mute (0%)").to_string(),
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

        // 5. Minuteur de mise en veille (Sleep timer)
        let sleep_guard = self.sleep_timer.lock().unwrap();
        let sleep_label = match *sleep_guard {
            Some(target) => {
                let now = std::time::Instant::now();
                if target > now {
                    let mins = (target - now).as_secs() / 60 + 1;
                    crate::i18n::sleep_timer_active_label(mins)
                } else {
                    crate::i18n::tr("Sleep timer").to_string()
                }
            }
            None => crate::i18n::tr("Sleep timer").to_string(),
        };

        menu.push(MenuItem::SubMenu(SubMenu {
            label: sleep_label,
            submenu: vec![
                MenuItem::Standard(StandardItem {
                    label: crate::i18n::tr("In 15 minutes").to_string(),
                    activate: Box::new(|tray| {
                        tray.set_sleep_timer(15);
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: crate::i18n::tr("In 30 minutes").to_string(),
                    activate: Box::new(|tray| {
                        tray.set_sleep_timer(30);
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: crate::i18n::tr("In 45 minutes").to_string(),
                    activate: Box::new(|tray| {
                        tray.set_sleep_timer(45);
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: crate::i18n::tr("In 60 minutes (1h)").to_string(),
                    activate: Box::new(|tray| {
                        tray.set_sleep_timer(60);
                    }),
                    ..Default::default()
                }),
                MenuItem::Separator,
                MenuItem::Standard(StandardItem {
                    label: crate::i18n::tr("Cancel sleep timer").to_string(),
                    activate: Box::new(|tray| {
                        tray.cancel_sleep_timer();
                    }),
                    ..Default::default()
                }),
            ],
            enabled: true,
            visible: true,
            ..Default::default()
        }));

        menu.push(MenuItem::Separator);

        // 6. Options et gestion des signets
        menu.push(MenuItem::SubMenu(SubMenu {
            label: crate::i18n::tr("Options").to_string(),
            submenu: vec![
                MenuItem::Standard(StandardItem {
                    label: crate::i18n::tr("Add a station...").to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        Self::trigger_add_station_dialog(
                            Arc::clone(&tray.root_group),
                            tray.bookmarks_path.clone(),
                            Arc::clone(&tray.tray_handle),
                        );
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: crate::i18n::tr("Discover & Import stations...").to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        Self::trigger_browse_bouquets_dialog(
                            Arc::clone(&tray.root_group),
                            tray.bookmarks_path.clone(),
                            Arc::clone(&tray.tray_handle),
                            Some(0),
                        );
                    }),
                    ..Default::default()
                }),
                MenuItem::Separator,
                MenuItem::Checkmark(CheckmarkItem {
                    label: crate::i18n::tr("Start automatically at login").to_string(),
                    checked: Self::is_autostart_enabled(),
                    activate: Box::new(|tray: &mut Self| {
                        Self::toggle_autostart();
                        if let Some(ref h) = *tray.tray_handle.lock().unwrap() {
                            h.update(|_| {});
                        }
                    }),
                    ..Default::default()
                }),
                MenuItem::Separator,
                MenuItem::SubMenu(SubMenu {
                    label: crate::i18n::tr("Maintenance & Data").to_string(),
                    submenu: vec![
                        MenuItem::Standard(StandardItem {
                            label: crate::i18n::tr("Manage groups and stations...").to_string(),
                            activate: Box::new(|tray: &mut Self| {
                                Self::trigger_reorder_groups_dialog(
                                    Arc::clone(&tray.root_group),
                                    tray.bookmarks_path.clone(),
                                    Arc::clone(&tray.tray_handle),
                                    false,
                                );
                            }),
                            ..Default::default()
                        }),
                        MenuItem::Standard(StandardItem {
                            label: crate::i18n::tr("Check streams (dead links)...").to_string(),
                            activate: Box::new(|tray: &mut Self| {
                                Self::trigger_reorder_groups_dialog(
                                    Arc::clone(&tray.root_group),
                                    tray.bookmarks_path.clone(),
                                    Arc::clone(&tray.tray_handle),
                                    true,
                                );
                            }),
                            ..Default::default()
                        }),
                        MenuItem::Standard(StandardItem {
                            label: crate::i18n::tr("Import my files (XML, CSV, JSON, M3U)...").to_string(),
                            activate: Box::new(|tray: &mut Self| {
                                Self::trigger_browse_bouquets_dialog(
                                    Arc::clone(&tray.root_group),
                                    tray.bookmarks_path.clone(),
                                    Arc::clone(&tray.tray_handle),
                                    Some(3),
                                );
                            }),
                            ..Default::default()
                        }),
                        MenuItem::Standard(StandardItem {
                            label: crate::i18n::tr("Export my stations to CSV...").to_string(),
                            activate: Box::new(|tray: &mut Self| {
                                Self::trigger_export_csv_dialog(
                                    Arc::clone(&tray.root_group),
                                    tray.bookmarks_path.clone(),
                                    Arc::clone(&tray.tray_handle),
                                );
                            }),
                            ..Default::default()
                        }),
                        MenuItem::Standard(StandardItem {
                            label: crate::i18n::tr("Open bookmarks.xml").to_string(),
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
                }),
            ],
            enabled: true,
            visible: true,
            ..Default::default()
        }));

        // 6. Quitter proprement l'application
        menu.push(MenuItem::Standard(StandardItem {
            label: crate::i18n::tr("Quit TiMonde").to_string(),
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

#[cfg(test)]
mod tests {
    use super::*;
    use ksni::Tray;

    #[test]
    fn test_find_station_and_edit_params() {
        let xml = r#"
        <bookmarks>
            <group name="English">
                <bookmark name="Bluegrass Planet Radio" url="http://65.108.105.26:7966/stream"/>
            </group>
        </bookmarks>
        "#;
        let root = crate::bookmarks::parse_bookmarks_reader(xml.as_bytes()).unwrap();
        let found = TiMondeTray::find_station_by_url(&root, "http://65.108.105.26:7966/stream");
        assert!(found.is_some());
        let st = found.unwrap();
        assert_eq!(st.name, "Bluegrass Planet Radio");
    }

    #[test]
    fn test_autostart_toggle_and_path() {
        let path = TiMondeTray::autostart_file_path();
        assert!(path.to_string_lossy().contains(".config/autostart/timonde.desktop"));
    }

    static I18N_TEST_MUTEX: std::sync::Mutex<()> = std::sync::Mutex::new(());

    #[test]
    fn test_menu_layout_stopped_and_playing() {
        let _lock = I18N_TEST_MUTEX.lock().unwrap();
        crate::i18n::set_language("fr");
        let xml = r#"
        <bookmarks>
            <group name="English">
                <bookmark name="Bluegrass Planet Radio" url="http://65.108.105.26:7966/stream"/>
            </group>
        </bookmarks>
        "#;
        let root = crate::bookmarks::parse_bookmarks_reader(xml.as_bytes()).unwrap();
        let bpath = std::path::PathBuf::from("/tmp/bookmarks_test.xml");
        let tray = TiMondeTray::new(root, bpath);
        *tray.last_station.lock().unwrap() = Some(Station::new("Bluegrass Planet Radio", "http://65.108.105.26:7966/stream"));

        // 1. En veille / arrêté : première entrée "Écouter    « Bluegrass Planet Radio »"
        let menu_stopped = tray.menu();
        match &menu_stopped[0] {
            MenuItem::Standard(item) => {
                assert!(item.label.starts_with("Écouter : « Bluegrass Planet Radio »") || item.label.contains("Bluegrass Planet Radio"));
            }
            _ => panic!("Le premier élément doit être le bouton Écouter"),
        }

        // 2. En cours de lecture : première entrée "Éteindre    « Bluegrass Planet Radio »" et présence de "Éditer"
        *tray.current_station.lock().unwrap() = Some(Station::new("Bluegrass Planet Radio", "http://65.108.105.26:7966/stream"));
        *tray.current_title.lock().unwrap() = Some("Matt Combs - Fifty Years of Clown School".to_string());

        let menu_playing = tray.menu();
        let labels: Vec<String> = menu_playing.iter().filter_map(|m| {
            if let MenuItem::Standard(item) = m {
                Some(item.label.clone())
            } else {
                None
            }
        }).collect();

        assert!(labels.iter().any(|l| l.contains("Matt Combs - Fifty Years of Clown School")));
        assert!(labels.iter().any(|l| l.contains("Éditer")));
    }
    #[test]
    fn test_menu_layout_english_mode() {
        let _lock = I18N_TEST_MUTEX.lock().unwrap();
        crate::i18n::set_language("en");

        let xml = r#"
        <bookmarks>
            <group name="English">
                <bookmark name="Bluegrass Planet Radio" url="http://65.108.105.26:7966/stream"/>
            </group>
        </bookmarks>
        "#;
        let root = crate::bookmarks::parse_bookmarks_reader(xml.as_bytes()).unwrap();
        let bpath = std::path::PathBuf::from("/tmp/bookmarks_test_en.xml");
        let tray = TiMondeTray::new(root, bpath);
        *tray.last_station.lock().unwrap() = Some(Station::new("Bluegrass Planet Radio", "http://65.108.105.26:7966/stream"));

        // 1. En veille
        let menu_stopped = tray.menu();
        match &menu_stopped[0] {
            MenuItem::Standard(item) => {
                assert!(item.label.starts_with("Play : « Bluegrass Planet Radio »") || item.label.contains("Bluegrass Planet Radio"), "Le label doit être en anglais: {}", item.label);
                assert!(!item.label.contains("Écouter"), "Aucun mot français ne doit subsister");
            }
            _ => panic!("Le premier élément doit être le bouton Play"),
        }

        // 2. En lecture
        *tray.current_station.lock().unwrap() = Some(Station::new("Bluegrass Planet Radio", "http://65.108.105.26:7966/stream"));
        *tray.current_title.lock().unwrap() = Some("Country Song".to_string());

        let menu_playing = tray.menu();
        let labels: Vec<String> = menu_playing.iter().filter_map(|m| {
            if let MenuItem::Standard(item) = m {
                Some(item.label.clone())
            } else {
                None
            }
        }).collect();

        assert!(labels[0].starts_with("Stop : « Bluegrass Planet Radio »") || labels[0].contains("Bluegrass Planet Radio"));
        assert!(!labels[0].contains("Éteindre"));
        assert!(labels.iter().any(|l| l.contains("Edit")));
        assert!(!labels.iter().any(|l| l.contains("Éditer")));
        assert!(labels.iter().any(|l| l == "Quit TiMonde"));
        assert!(!labels.iter().any(|l| l == "Quitter TiMonde"));

        // Rétablir le français
        crate::i18n::set_language("fr");
    }

    #[test]
    fn test_reorder_groups_hierarchy_serialization_and_reconstruction() {
        let mut root = Group::new("root");

        let france = root.get_or_create_subgroup_hierarchy("France");
        france.stations.push(Station::with_country("France Inter", "http://franceinter.fr/stream", "FR"));

        let bretagne = root.get_or_create_subgroup_hierarchy("France/Bretagne");
        bretagne.stations.push(Station::with_country("Radio Bro Gwened", "http://rbg.bzh/stream", "FR"));

        let country = root.get_or_create_subgroup_hierarchy("Country");
        country.stations.push(Station::with_country("Allzic Country", "http://allzic.com/country", "FR"));

        let bluegrass = root.get_or_create_subgroup_hierarchy("Country/Bluegrass");
        bluegrass.stations.push(Station::with_timezone("Bluegrass Planet Radio", "http://bluegrass.com/live", "US", "America/New_York"));

        // 1. Vérification de la sérialisation récursive (collect_payload)
        let mut payload = Vec::new();
        fn collect_test_payload(group: &Group, prefix: &str, out: &mut Vec<serde_json::Value>) {
            for g in &group.subgroups {
                if g.is_separator() {
                    out.push(serde_json::json!({
                        "name": g.separator_title().unwrap_or_default(),
                        "stations": [],
                        "is_separator": true,
                    }));
                } else {
                    let full_path = if prefix.is_empty() {
                        g.name.clone()
                    } else {
                        format!("{}/{}", prefix, g.name)
                    };

                    let stations_json: Vec<serde_json::Value> = g
                        .stations
                        .iter()
                        .map(|s| {
                            serde_json::json!({
                                "name": s.name,
                                "url": s.url,
                                "country": s.country,
                                "timezone": s.timezone,
                                "is_separator": s.is_separator(),
                            })
                        })
                        .collect();

                    out.push(serde_json::json!({
                        "name": full_path,
                        "stations": stations_json,
                        "is_separator": false,
                    }));

                    collect_test_payload(g, &full_path, out);
                }
            }
        }
        collect_test_payload(&root, "", &mut payload);

        let group_names: Vec<&str> = payload.iter().filter_map(|p| p["name"].as_str()).collect();
        assert_eq!(group_names, vec!["France", "France/Bretagne", "Country", "Country/Bluegrass"]);

        // 2. Vérification de la reconstruction depuis le JSON retourné par l'outil
        let returned_json = r#"[
            {
                "name": "France",
                "stations": [
                    { "name": "France Inter", "url": "http://franceinter.fr/stream", "country": "FR" }
                ]
            },
            {
                "name": "France/Bretagne",
                "stations": [
                    { "name": "Radio Bro Gwened", "url": "http://rbg.bzh/stream", "country": "FR" },
                    { "name": "Radio Laser", "url": "http://radiolaser.fr/live", "country": "FR" }
                ]
            },
            {
                "name": "France/Normandie",
                "stations": [
                    { "name": "Radio 666", "url": "http://radio666.com/stream", "country": "FR" }
                ]
            },
            {
                "name": "Country",
                "stations": [
                    { "name": "Allzic Country", "url": "http://allzic.com/country", "country": "FR" }
                ]
            },
            {
                "name": "Country/Bluegrass",
                "stations": [
                    { "name": "Bluegrass Planet Radio", "url": "http://bluegrass.com/live" }
                ]
            }
        ]"#;

        #[derive(serde::Deserialize)]
        #[allow(dead_code)]
        struct TestStation {
            name: String,
            #[serde(default)]
            url: String,
            #[serde(default)]
            country: Option<String>,
            #[serde(default)]
            timezone: Option<String>,
            #[serde(default)]
            is_separator: bool,
        }
        #[derive(serde::Deserialize)]
        #[allow(dead_code)]
        struct TestGroup {
            name: String,
            #[serde(default)]
            stations: Vec<TestStation>,
            #[serde(default)]
            is_separator: bool,
        }

        let new_data: Vec<TestGroup> = serde_json::from_str(returned_json).unwrap();
        let mut old_root = root.clone();
        let mut new_root = Group::new("root");

        for g_data in new_data {
            let mut new_stations = Vec::new();
            for s_data in g_data.stations {
                let st = if let Some(mut existing) = old_root.remove_station_from_tree(&s_data.url, &s_data.name) {
                    existing.name = s_data.name;
                    if !s_data.url.is_empty() {
                        existing.url = s_data.url;
                    }
                    if s_data.country.is_some() {
                        existing.country = s_data.country;
                    }
                    if s_data.timezone.is_some() {
                        existing.timezone = s_data.timezone;
                    }
                    existing
                } else {
                    let mut s = Station::new(&s_data.name, &s_data.url);
                    s.country = s_data.country;
                    s.timezone = s_data.timezone;
                    s
                };
                new_stations.push(st);
            }
            let grp = new_root.get_or_create_subgroup_hierarchy(&g_data.name);
            grp.stations = new_stations;
        }

        // Vérifications de structure
        assert_eq!(new_root.subgroups.len(), 2);
        assert_eq!(new_root.subgroups[0].name, "France");
        assert_eq!(new_root.subgroups[0].subgroups.len(), 2);
        assert_eq!(new_root.subgroups[0].subgroups[0].name, "Bretagne");
        assert_eq!(new_root.subgroups[0].subgroups[0].stations.len(), 2);
        assert_eq!(new_root.subgroups[0].subgroups[1].name, "Normandie");
        assert_eq!(new_root.subgroups[0].subgroups[1].stations.len(), 1);

        assert_eq!(new_root.subgroups[1].name, "Country");
        assert_eq!(new_root.subgroups[1].subgroups.len(), 1);
        assert_eq!(new_root.subgroups[1].subgroups[0].name, "Bluegrass");
        let bg_st = &new_root.subgroups[1].subgroups[0].stations[0];
        assert_eq!(bg_st.name, "Bluegrass Planet Radio");
        assert_eq!(bg_st.country, Some("US".to_string()));
        assert_eq!(bg_st.timezone, Some("America/New_York".to_string()));

        // Sauvegarde XML et relecture
        let temp_xml = std::env::temp_dir().join("test_reorder_hierarchy.xml");
        crate::bookmarks::save_bookmarks(&new_root, &temp_xml).unwrap();
        let loaded = crate::bookmarks::load_bookmarks(&temp_xml).unwrap();
        let _ = std::fs::remove_file(&temp_xml);

        assert_eq!(loaded.subgroups.len(), 2);
        assert_eq!(loaded.subgroups[0].name, "France");
        assert_eq!(loaded.subgroups[0].subgroups[0].name, "Bretagne");
        assert_eq!(loaded.subgroups[0].subgroups[1].name, "Normandie");
        assert_eq!(loaded.subgroups[1].name, "Country");
        assert_eq!(loaded.subgroups[1].subgroups[0].name, "Bluegrass");
    }

}
