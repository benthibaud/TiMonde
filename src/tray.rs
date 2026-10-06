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
    pub tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
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
            tray_handle: Arc::new(Mutex::new(None)),
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
                info!("🔄 {} signets rechargés avec succès depuis {:?}", total, bookmarks_path);

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
    pub fn trigger_add_station_dialog(
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    ) {
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
                    match Self::reload_bookmarks_and_update_tray(&root_group, &bookmarks_path, &tray_handle) {
                        Ok(total) => {
                            log::info!("✅ {} (Total : {} stations)", msg, total);
                            crate::radio_browser::notify("TiMonde", &format!("{}
Liste des radios rechargée ({} stations).", msg, total));
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

    fn find_reorder_script() -> Option<PathBuf> {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        let candidate1 = PathBuf::from(&home).join(".local/share/timonde/scripts/reorder_groups.py");
        if candidate1.exists() {
            return Some(candidate1);
        }
        let candidate2 = PathBuf::from("data/scripts/reorder_groups.py");
        if candidate2.exists() {
            return Some(candidate2);
        }
        let candidate3 = PathBuf::from(&home).join(".gemini/antigravity/scratch/TiMonde/data/scripts/reorder_groups.py");
        if candidate3.exists() {
            return Some(candidate3);
        }
        None
    }

    /// Réorganisation ergonomique des groupes et des radios via fenêtre GTK3 dédiée (Option 1 BB)
    pub fn trigger_reorder_groups_dialog(
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    ) {
        std::thread::spawn(move || {
            let groups_payload: Vec<serde_json::Value> = {
                let guard = root_group.lock().unwrap();
                if guard.subgroups.is_empty() {
                    crate::radio_browser::notify("TiMonde", "Aucun groupe de radios à classer");
                    return;
                }
                guard
                    .subgroups
                    .iter()
                    .map(|g| {
                        let stations_json: Vec<serde_json::Value> = g
                            .stations
                            .iter()
                            .filter(|s| !s.is_separator())
                            .map(|s| {
                                serde_json::json!({
                                    "name": s.name,
                                    "url": s.url,
                                })
                            })
                            .collect();

                        serde_json::json!({
                            "name": g.name,
                            "stations": stations_json,
                        })
                    })
                    .collect()
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

            let mut child = match std::process::Command::new("python3")
                .arg(script_path)
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

            // Si code 0 : l'utilisateur a cliqué sur "💾 Enregistrer et recharger"
            if output.status.success() {
                let stdout_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
                
                #[derive(serde::Deserialize)]
                struct OutStation {
                    name: String,
                    url: String,
                }
                #[derive(serde::Deserialize)]
                struct OutGroup {
                    name: String,
                    #[serde(default)]
                    stations: Vec<OutStation>,
                }

                let new_data: Vec<OutGroup> = match serde_json::from_str(&stdout_str) {
                    Ok(d) => d,
                    Err(e) => {
                        log::error!("Erreur désérialisation du nouvel ordre : {}", e);
                        return;
                    }
                };

                let mut root = root_group.lock().unwrap().clone();
                let mut reordered_subgroups = Vec::new();

                for g_data in new_data {
                    if let Some(pos) = root.subgroups.iter().position(|g| g.name.eq_ignore_ascii_case(&g_data.name)) {
                        let mut grp = root.subgroups.remove(pos);
                        
                        // Réordonner les stations selon la sélection de l utilisateur
                        let mut new_stations = Vec::new();
                        for s_data in g_data.stations {
                            if let Some(s_pos) = grp.stations.iter().position(|s| s.name.eq_ignore_ascii_case(&s_data.name)) {
                                new_stations.push(grp.stations.remove(s_pos));
                            } else {
                                new_stations.push(Station {
                                    name: s_data.name,
                                    url: s_data.url,
                                });
                            }
                        }
                        // Conserver les séparateurs ou résiduels
                        new_stations.append(&mut grp.stations);
                        grp.stations = new_stations;

                        reordered_subgroups.push(grp);
                    }
                }
                reordered_subgroups.append(&mut root.subgroups);
                root.subgroups = reordered_subgroups;

                if let Err(e) = crate::bookmarks::save_bookmarks(&root, &bookmarks_path) {
                    log::error!("Erreur sauvegarde : {}", e);
                    crate::radio_browser::notify("TiMonde", &format!("Erreur sauvegarde : {}", e));
                    return;
                }

                let _ = Self::reload_bookmarks_and_update_tray(&root_group, &bookmarks_path, &tray_handle);
                log::info!("✅ Ordre des groupes et radios enregistré et signets rechargés !");
                crate::radio_browser::notify(
                    "TiMonde",
                    "✅ Ordre des groupes et radios enregistré et rechargé !",
                );
            }
        });
    }

    /// Recherche multicritères (Genre, Pays, Langue, Mot-clé) et importation par lot
    pub fn trigger_search_online_dialog(
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    ) {
        std::thread::spawn(move || {
            let form_output = match std::process::Command::new("zenity")
                .arg("--forms")
                .arg("--title=🔍 Recherche & Import Radio-Browser")
                .arg("--text=Renseignez vos filtres (laissez vide pour ignorer) :")
                .arg("--add-entry=Nom ou mot-clé :")
                .arg("--add-entry=Genre / Style (ex: jazz, rock, news, ambient, reggae) :")
                .arg("--add-entry=Pays / Origine (ex: France, Belgium, Canada, Senegal) :")
                .arg("--add-entry=Langue (ex: French, English, Spanish, Arabic) :")
                .output()
            {
                Ok(out) if out.status.success() => out,
                _ => return,
            };

            let form_str = String::from_utf8_lossy(&form_output.stdout).trim().to_string();
            let parts: Vec<&str> = form_str.split('|').collect();
            if parts.is_empty() {
                return;
            }

            let name_val = parts.first().map(|s| s.trim()).filter(|s| !s.is_empty()).map(|s| s.to_string());
            let tag_val = parts.get(1).map(|s| s.trim()).filter(|s| !s.is_empty()).map(|s| s.to_string());
            let country_val = parts.get(2).map(|s| s.trim()).filter(|s| !s.is_empty()).map(|s| s.to_string());
            let lang_val = parts.get(3).map(|s| s.trim()).filter(|s| !s.is_empty()).map(|s| s.to_string());

            if name_val.is_none() && tag_val.is_none() && country_val.is_none() && lang_val.is_none() {
                return;
            }

            let filter = crate::radio_browser::SearchFilter {
                name: name_val,
                tag: tag_val,
                country: country_val,
                language: lang_val,
                limit: 50,
            };

            crate::radio_browser::notify("TiMonde", "Recherche Radio-Browser en cours...");
            let results = crate::radio_browser::search_advanced(&filter);

            if results.is_empty() {
                crate::radio_browser::notify("TiMonde", "Aucune station trouvée pour ces critères");
                return;
            }

            let mut list_cmd = std::process::Command::new("zenity");
            list_cmd
                .arg("--list")
                .arg("--checklist")
                .arg("--multiple")
                .arg("--separator=;")
                .arg(format!("--title=Résultats Radio-Browser ({} trouvées)", results.len()))
                .arg("--text=Cochez les stations à importer dans vos favoris :")
                .arg("--column=Ajouter")
                .arg("--column=ID")
                .arg("--column=Nom")
                .arg("--column=Pays")
                .arg("--column=Genre / Tags")
                .arg("--column=Format")
                .arg("--column=Débit")
                .arg("--column=Votes")
                .arg("--print-column=2")
                .arg("--hide-column=2")
                .arg("--width=850")
                .arg("--height=460");

            for (i, r) in results.iter().enumerate() {
                list_cmd.arg("FALSE");
                list_cmd.arg(format!("{}", i));
                list_cmd.arg(&r.name);
                list_cmd.arg(if r.country.is_empty() { "-" } else { &r.country });
                list_cmd.arg(if r.tags.is_empty() { "-" } else { &r.tags });
                list_cmd.arg(if r.codec.is_empty() { "-" } else { &r.codec });
                list_cmd.arg(if r.bitrate > 0 { format!("{}k", r.bitrate) } else { "-".to_string() });
                list_cmd.arg(format!("{}", r.votes));
            }

            let sel_output = match list_cmd.output() {
                Ok(out) if out.status.success() => out,
                _ => return,
            };

            let sel_str = String::from_utf8_lossy(&sel_output.stdout).trim().to_string();
            if sel_str.is_empty() {
                return;
            }

            let selected_indices: Vec<usize> = sel_str
                .split(';')
                .filter_map(|s| s.trim().parse::<usize>().ok())
                .filter(|&idx| idx < results.len())
                .collect();

            if selected_indices.is_empty() {
                return;
            }

            let target_group = match Self::select_target_group_dialog(&root_group) {
                Some(tg) => tg,
                None => return,
            };

            let mut root = root_group.lock().unwrap().clone();
            let mut added_count = 0;
            let mut skipped_count = 0;

            for idx in selected_indices {
                let chosen = &results[idx];
                match crate::import::add_single_station(
                    &mut root,
                    &chosen.name,
                    &chosen.url_resolved,
                    target_group.as_deref(),
                ) {
                    Ok(_) => added_count += 1,
                    Err(_) => skipped_count += 1,
                }
            }

            if added_count > 0 {
                if let Err(e) = crate::bookmarks::save_bookmarks(&root, &bookmarks_path) {
                    log::error!("Erreur sauvegarde : {}", e);
                    crate::radio_browser::notify("TiMonde", &format!("Erreur sauvegarde : {}", e));
                    return;
                }
                let total_count = Self::reload_bookmarks_and_update_tray(&root_group, &bookmarks_path, &tray_handle).unwrap_or(0);
                let grp_name = target_group.as_deref().unwrap_or("la racine");
                crate::radio_browser::notify(
                    "TiMonde",
                    &format!(
                        "Importation terminée dans {} !\n• {} station(s) ajoutée(s)\n• {} doublon(s) ignoré(s)\nListe des radios rechargée ({} stations).",
                        grp_name, added_count, skipped_count, total_count
                    ),
                );
            } else {
                crate::radio_browser::notify("TiMonde", "Toutes les stations sélectionnées étaient déjà dans vos favoris");
            }
        });
    }

    /// Ouvre les boîtes de dialogue natives (Zenity) pour importer une liste de stations
    pub fn trigger_import_dialog(
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    ) {
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
                    let total_count = Self::reload_bookmarks_and_update_tray(&root_group, &bookmarks_path, &tray_handle).unwrap_or(0);
                    log::info!(
                        "✅ Importation réussie : {} ajoutée(s), {} doublon(s) ignoré(s), {} groupe(s) créé(s)",
                        report.stations_added, report.duplicates_skipped, report.groups_created
                    );
                    crate::radio_browser::notify(
                        "TiMonde",
                        &format!(
                            "Importation réussie !\n• {} station(s) ajoutée(s)\n• {} doublon(s) ignoré(s)\nListe des radios rechargée ({} stations).",
                            report.stations_added, report.duplicates_skipped, total_count
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
                            Arc::clone(&tray.tray_handle),
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
                            Arc::clone(&tray.tray_handle),
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
                            Arc::clone(&tray.tray_handle),
                        );
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "↕️ Classer groupes et radios...".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        Self::trigger_reorder_groups_dialog(
                            Arc::clone(&tray.root_group),
                            tray.bookmarks_path.clone(),
                            Arc::clone(&tray.tray_handle),
                        );
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "🔄 Recharger les signets".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        info!("Rechargement manuel des signets depuis : {:?}", tray.bookmarks_path);
                        match Self::reload_bookmarks_and_update_tray(
                            &tray.root_group,
                            &tray.bookmarks_path,
                            &tray.tray_handle,
                        ) {
                            Ok(count) => {
                                notify("TiMonde", &format!("{} signets rechargés avec succès !", count));
                            }
                            Err(_) => {
                                notify("TiMonde", "Erreur lors du rechargement des signets");
                            }
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
