use crate::audio::{AudioEngine, PlaybackState};
use crate::models::{Group, Station};
use ksni::menu::{MenuItem, StandardItem, SubMenu};
use log::info;
use std::sync::Arc;

pub struct TiMondeTray {
    pub audio: Arc<AudioEngine>,
    pub root_group: Group,
    pub last_station: Option<Station>,
    pub current_station: Option<Station>,
}

impl TiMondeTray {
    pub fn new(audio: Arc<AudioEngine>, root_group: Group) -> Self {
        Self {
            audio,
            root_group,
            last_station: None,
            current_station: None,
        }
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
                let url = station.url.clone();
                let item = StandardItem {
                    label: station.name.clone(),
                    activate: Box::new(move |tray: &mut Self| {
                        info!("Sélection de la station : {} ({})", st_clone.name, url);
                        if let Err(e) = tray.audio.play(&url) {
                            log::error!("Échec lecture : {}", e);
                        } else {
                            tray.last_station = Some(st_clone.clone());
                            tray.current_station = Some(st_clone.clone());
                        }
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

    /// Clic gauche : Bascule Play / Stop instantanée
    fn activate(&mut self, _x: i32, _y: i32) {
        match self.audio.state() {
            PlaybackState::Playing | PlaybackState::Buffering => {
                let _ = self.audio.stop();
                self.current_station = None;
            }
            PlaybackState::Stopped | PlaybackState::Error => {
                if let Some(ref st) = self.last_station.clone() {
                    if let Ok(()) = self.audio.play(&st.url) {
                        self.current_station = Some(st.clone());
                    }
                }
            }
        }
    }

    /// Molette sur l'icône : Réglage du volume sonore (+5% / -5%)
    fn scroll(&mut self, delta: i32, _orientation: ksni::Orientation) {
        let current_vol = self.audio.volume();
        let step = (delta as f64) * 0.05;
        self.audio.set_volume(current_vol + step);
    }

    /// Menu contextuel complet (clic droit)
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
        // On explore directement les sous-groupes du groupe "root"
        for sub in &self.root_group.subgroups {
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

        // Stations directes de la racine s'il y en a
        for st in &self.root_group.stations {
            if !st.is_separator() {
                let st_clone = st.clone();
                let url = st.url.clone();
                menu.push(MenuItem::Standard(StandardItem {
                    label: st.name.clone(),
                    activate: Box::new(move |tray: &mut Self| {
                        if let Ok(()) = tray.audio.play(&url) {
                            tray.last_station = Some(st_clone.clone());
                            tray.current_station = Some(st_clone.clone());
                        }
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
