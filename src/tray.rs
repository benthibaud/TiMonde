use crate::audio::{AudioEngine, PlaybackState};
use crate::bookmarks::{save_bookmarks, update_station_url};
use crate::models::{Group, Station};
use crate::radio_browser::{find_backup_stream, notify};
use ksni::menu::{MenuItem, StandardItem, SubMenu};
use log::{error, info};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

pub struct TiMondeTray {
    pub audio: Arc<AudioEngine>,
    pub root_group: Arc<Mutex<Group>>,
    pub bookmarks_path: PathBuf,
    pub last_station: Option<Station>,
    pub current_station: Option<Station>,
    pub play_generation: Arc<AtomicU64>,
}

impl TiMondeTray {
    pub fn new(audio: Arc<AudioEngine>, root_group: Group, bookmarks_path: PathBuf) -> Self {
        Self {
            audio,
            root_group: Arc::new(Mutex::new(root_group)),
            bookmarks_path,
            last_station: None,
            current_station: None,
            play_generation: Arc::new(AtomicU64::new(0)),
        }
    }

    /// Démarre une station avec watchdog et auto-réparation persistante
    pub fn play_station_with_watchdog(&mut self, station: Station) {
        let station_name = station.name.clone();
        let url = station.url.clone();
        info!("Sélection de la station : {} ({})", station_name, url);

        if let Err(e) = self.audio.play(&url) {
            error!("Échec initial de lecture : {}", e);
            notify("TiMonde", &format!("Impossible de lancer {}", station_name));
            return;
        }

        self.last_station = Some(station.clone());
        self.current_station = Some(station);

        let gen = self.play_generation.fetch_add(1, Ordering::SeqCst) + 1;
        let gen_clone = Arc::clone(&self.play_generation);
        let audio_clone = Arc::clone(&self.audio);
        let root_group_clone = Arc::clone(&self.root_group);
        let bookmarks_path_clone = self.bookmarks_path.clone();
        let name_for_watchdog = station_name.clone();

        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs(5));

            if gen_clone.load(Ordering::SeqCst) != gen {
                return;
            }

            let st = audio_clone.state();
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
                    if let Ok(()) = audio_clone.play(&backup_url) {
                        // 1. Mise à jour pérenne dans bookmarks.xml
                        {
                            let mut group = root_group_clone.lock().unwrap();
                            if update_station_url(&mut group, &name_for_watchdog, &backup_url) {
                                if let Err(e) = save_bookmarks(&group, &bookmarks_path_clone) {
                                    error!("Erreur lors de la sauvegarde du flux réparé : {}", e);
                                } else {
                                    info!("✅ Nouveau flux enregistré de façon permanente dans {:?}", bookmarks_path_clone);
                                }
                            }
                        }

                        // 2. Notification de confirmation
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
                    let _ = audio_clone.stop();
                }
            }
        });
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
                        tray.play_station_with_watchdog(st_clone.clone());
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
        match (&self.current_station, self.audio.state()) {
            (Some(st), PlaybackState::Playing) => format!("TiMonde : {}", st.name),
            (Some(st), PlaybackState::Buffering) => format!("TiMonde (Connexion...) : {}", st.name),
            (Some(st), PlaybackState::Paused) => format!("TiMonde (Pause) : {}", st.name),
            _ => "TiMonde".to_string(),
        }
    }

    fn icon_name(&self) -> String {
        match self.audio.state() {
            PlaybackState::Playing => "radiotray_on".to_string(),
            PlaybackState::Buffering => "radiotray_connecting".to_string(),
            PlaybackState::Paused | PlaybackState::Stopped | PlaybackState::Error => "radiotray_off".to_string(),
        }
    }

    fn icon_theme_path(&self) -> String {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        format!("{}/.local/share/icons/hicolor/48x48/panel", home)
    }

    fn scroll(&mut self, delta: i32, _orientation: ksni::Orientation) {
        let current_vol = self.audio.volume();
        let step = (delta as f64) * 0.05;
        self.audio.set_volume(current_vol + step);
    }

    fn menu(&self) -> Vec<MenuItem<Self>> {
        let mut menu = Vec::new();

        // 1. En-tête informatif sur la lecture en cours
        let status_label = match (&self.current_station, self.audio.state()) {
            (Some(st), PlaybackState::Playing) => format!("▶ En lecture : {}", st.name),
            (Some(st), PlaybackState::Buffering) => format!("⏳ Connexion : {}", st.name),
            (Some(st), PlaybackState::Paused) => format!("⏸ En pause : {}", st.name),
            _ => "⏹️ TiMonde (En veille)".to_string(),
        };

        menu.push(MenuItem::Standard(StandardItem {
            label: status_label,
            enabled: false,
            visible: true,
            ..Default::default()
        }));

        // 2. Contrôles de lecture (Pause, Reprendre, Relancer, Arrêter)
        match self.audio.state() {
            PlaybackState::Playing => {
                menu.push(MenuItem::Standard(StandardItem {
                    label: "⏸ Mettre en pause".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        let _ = tray.audio.pause();
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
                menu.push(MenuItem::Standard(StandardItem {
                    label: "⏹ Arrêter la lecture".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        let _ = tray.audio.stop();
                        tray.current_station = None;
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
                        let _ = tray.audio.resume();
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
                menu.push(MenuItem::Standard(StandardItem {
                    label: "⏹ Arrêter la lecture".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        let _ = tray.audio.stop();
                        tray.current_station = None;
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
            }
            PlaybackState::Stopped | PlaybackState::Error => {
                if let Some(ref last_st) = self.last_station {
                    let st_to_replay = last_st.clone();
                    menu.push(MenuItem::Standard(StandardItem {
                        label: format!("▶ Relancer : {}", st_to_replay.name),
                        activate: Box::new(move |tray: &mut Self| {
                            tray.play_station_with_watchdog(st_to_replay.clone());
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
                        let _ = tray.audio.stop();
                        tray.current_station = None;
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
            }
        }

        menu.push(MenuItem::Separator);

        // 3. Arborescence des radios sans palier "root" intermédiaire
        let root_group = self.root_group.lock().unwrap();
        let effective_root = if root_group.subgroups.len() == 1
            && root_group.subgroups[0].name.to_lowercase() == "root"
        {
            &root_group.subgroups[0]
        } else {
            &*root_group
        };

        for sub in &effective_root.subgroups {
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

        for st in &effective_root.stations {
            if !st.is_separator() {
                let st_clone = st.clone();
                menu.push(MenuItem::Standard(StandardItem {
                    label: st.name.clone(),
                    activate: Box::new(move |tray: &mut Self| {
                        tray.play_station_with_watchdog(st_clone.clone());
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
            }
        }

        menu.push(MenuItem::Separator);

        // 4. Contrôle rapide du volume
        let vol_percent = (self.audio.volume() * 100.0).round() as i32;
        menu.push(MenuItem::SubMenu(SubMenu {
            label: format!("🔊 Volume ({vol_percent}%)"),
            submenu: vec![
                MenuItem::Standard(StandardItem {
                    label: "100%".to_string(),
                    activate: Box::new(|tray| tray.audio.set_volume(1.0)),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "75%".to_string(),
                    activate: Box::new(|tray| tray.audio.set_volume(0.75)),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "50%".to_string(),
                    activate: Box::new(|tray| tray.audio.set_volume(0.50)),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "25%".to_string(),
                    activate: Box::new(|tray| tray.audio.set_volume(0.25)),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "Muet (0%)".to_string(),
                    activate: Box::new(|tray| tray.audio.set_volume(0.0)),
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
                let _ = tray.audio.stop();
                std::process::exit(0);
            }),
            enabled: true,
            visible: true,
            ..Default::default()
        }));

        menu
    }
}
