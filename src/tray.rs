use crate::audio::{AudioEngine, PlaybackState};
use crate::bookmarks::{save_bookmarks, update_station_url};
use crate::models::{Group, Station};
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

    /// Exécute le flux complet de lecture avec watchdog et secours automatique
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
        let url = station.url.clone();
        info!("Sélection de la station : {} ({})", station_name, url);

        if let Err(e) = Self::get_or_create_engine(audio, current_volume, current_title) {
            error!("{}", e);
            notify("TiMonde", "Impossible d'initialiser l'audio");
            return;
        }

        {
            let guard = audio.lock().unwrap();
            if let Some(ref engine) = *guard {
                if let Err(e) = engine.play(&url) {
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
                    info!("Watchdog : bascule sur le flux de secours {}", backup_url);
                    let played = {
                        let guard = audio_clone.lock().unwrap();
                        if let Some(ref engine) = *guard {
                            engine.play(&backup_url).is_ok()
                        } else {
                            false
                        }
                    };

                    if played {
                        {
                            let mut group = root_group_clone.lock().unwrap();
                            if update_station_url(&mut group, &name_for_watchdog, &backup_url) {
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
        drop(cur_st);
        drop(cur_title);

        menu.push(MenuItem::Standard(StandardItem {
            label: status_label,
            enabled: false,
            visible: true,
            ..Default::default()
        }));

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

        // 5. Quitter proprement l'application
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
