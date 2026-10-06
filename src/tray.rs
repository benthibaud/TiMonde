use crate::audio::{AudioEngine, PlaybackState};
use crate::models::{Group, Station};
use crate::radio_browser::{find_backup_stream, notify};
use ksni::menu::{MenuItem, StandardItem, SubMenu};
use log::{error, info};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

pub struct TiMondeTray {
    pub audio: Arc<AudioEngine>,
    pub root_group: Group,
    pub last_station: Option<Station>,
    pub current_station: Option<Station>,
    pub play_generation: Arc<AtomicU64>,
}

impl TiMondeTray {
    pub fn new(audio: Arc<AudioEngine>, root_group: Group) -> Self {
        Self {
            audio,
            root_group,
            last_station: None,
            current_station: None,
            play_generation: Arc::new(AtomicU64::new(0)),
        }
    }

    /// Démarre une station avec surveillance d'inactivité et auto-guérison Radio-Browser
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

        // Incrémente la génération pour annuler tout watchdog précédent
        let gen = self.play_generation.fetch_add(1, Ordering::SeqCst) + 1;
        let gen_clone = Arc::clone(&self.play_generation);
        let audio_clone = Arc::clone(&self.audio);
        let name_for_watchdog = station_name.clone();

        std::thread::spawn(move || {
            // Attente de 5 secondes pour laisser le temps au flux de démarrer
            std::thread::sleep(Duration::from_secs(5));

            // Si la lecture a changé entre temps, on abandonne
            if gen_clone.load(Ordering::SeqCst) != gen {
                return;
            }

            // Vérification de l'état
            let st = audio_clone.state();
            if st == PlaybackState::Buffering || st == PlaybackState::Error {
                info!("Watchdog : flux silencieux ou en erreur au bout de 5s pour {}", name_for_watchdog);
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
                        notify(
                            "TiMonde",
                            &format!("Flux de secours reconnecté pour {} !", name_for_watchdog),
                        );
                    }
                } else {
                    if gen_clone.load(Ordering::SeqCst) == gen {
                        notify(
                            "TiMonde",
                            &format!("La radio {} est actuellement indisponible.", name_for_watchdog),
                        );
                        let _ = audio_clone.stop();
                    }
                }
            }
        });
    }

    /// Construit récursivement les éléments de menu pour un groupe donné
    fn build_group_menu(group: &Group) -> Vec<MenuItem<Self>> {
        let mut items = Vec::new();

        // 1. Sous-groupes d'abord
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

        // Séparateur entre sous-groupes et stations si les deux existent
        if !group.subgroups.is_empty() && !group.stations.is_empty() {
            items.push(MenuItem::Separator);
        }

        // 2. Stations du groupe
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
    /// Ouvre directement le menu des radios au clic gauche !
    const MENU_ON_ACTIVATE: bool = true;

    fn id(&self) -> String {
        "timonde".to_string()
    }

    fn title(&self) -> String {
        match (&self.current_station, self.audio.state()) {
            (Some(st), PlaybackState::Playing) => format!("TiMonde : {}", st.name),
            (Some(st), PlaybackState::Buffering) => format!("TiMonde (Connexion...) : {}", st.name),
            _ => "TiMonde".to_string(),
        }
    }

    fn icon_name(&self) -> String {
        match self.audio.state() {
            PlaybackState::Playing => "radiotray_on".to_string(),
            PlaybackState::Buffering => "radiotray_connecting".to_string(),
            PlaybackState::Stopped | PlaybackState::Error => "radiotray_off".to_string(),
        }
    }

    /// Molette sur l'icône : Réglage du volume sonore (+5% / -5%)
    fn scroll(&mut self, delta: i32, _orientation: ksni::Orientation) {
        let current_vol = self.audio.volume();
        let step = (delta as f64) * 0.05;
        self.audio.set_volume(current_vol + step);
    }

    /// Menu contextuel complet
    fn menu(&self) -> Vec<MenuItem<Self>> {
        let mut menu = Vec::new();

        // 1. En-tête informatif sur la lecture en cours
        let status_label = match (&self.current_station, self.audio.state()) {
            (Some(st), PlaybackState::Playing) => format!("▶ En lecture : {}", st.name),
            (Some(st), PlaybackState::Buffering) => format!("⏳ Connexion : {}", st.name),
            _ => "⏹️ TiMonde (En veille)".to_string(),
        };

        menu.push(MenuItem::Standard(StandardItem {
            label: status_label,
            enabled: false,
            visible: true,
            ..Default::default()
        }));

        // Bouton Arrêter direct si lecture active
        if self.audio.state() == PlaybackState::Playing || self.audio.state() == PlaybackState::Buffering {
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

        menu.push(MenuItem::Separator);

        // 2. Arborescence des radios depuis bookmarks.xml
        // Détection et suppression du palier intermédiaire "root" pour un affichage direct au 1er niveau
        let effective_root = if self.root_group.subgroups.len() == 1
            && self.root_group.subgroups[0].name.to_lowercase() == "root"
        {
            &self.root_group.subgroups[0]
        } else {
            &self.root_group
        };

        // Sous-groupes directs au premier niveau
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

        // Stations directes du premier niveau
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

        // 3. Contrôle rapide du volume
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

        // 4. Quitter proprement l'application
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
