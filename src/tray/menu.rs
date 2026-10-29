//! Implémentation du trait ksni::Tray et construction du menu D-Bus / StatusNotifierItem.

use std::sync::atomic::Ordering;
use std::sync::Arc;

use ksni::menu::{MenuItem, StandardItem, SubMenu};
use log::info;

use crate::audio::PlaybackState;
use crate::models::{Group, Station};
use crate::tray::TiMondeTray;

impl TiMondeTray {
    /// Formate le libellé d'une station dans le menu avec le drapeau national si étiqueté
    pub(crate) fn format_station_menu_label(station: &Station) -> String {
        if let Some((_, flag, _, _)) = crate::timezone::resolve_station_meta(
            station.country.as_deref(),
            &station.name,
            None,
            station.timezone.as_deref(),
        ) {
            format!("{} {}", flag, station.name)
        } else {
            station.name.clone()
        }
    }

    /// Construit récursivement les éléments de menu pour un sous-groupe donné
    pub(crate) fn build_group_menu(group: &Group) -> Vec<MenuItem<Self>> {
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
}

impl ksni::Tray for TiMondeTray {
    const MENU_ON_ACTIVATE: bool = false;

    fn activate(&mut self, _x: i32, _y: i32) {
        log::info!("Clic gauche sur l'icône de la barre des tâches : ouverture du menu des stations");
        // Priorité 1 : Déclenchement instantané 0 ms via X11 / XTest (LXQt, XFCE, MATE sous X11)
        if Self::try_trigger_context_menu_x11() {
            return;
        }

        // Priorité 2 : Fallback D-BusMenu GTK3 pour environnements hors-X11 / Wayland purs
        if let Some(script_path) = Self::find_script("show_menu.py") {
            let pid = std::process::id();
            let bus_name = format!("org.kde.StatusNotifierItem-{}-1", pid);
            let _ = crate::tray::dialogs::prepare_python_command("python3")
                .arg(script_path)
                .arg(format!("--bus={}", bus_name))
                .spawn();
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
                let time_str = crate::timezone::get_local_time_for_station(
                    st.country.as_deref(),
                    &st.name,
                    None,
                    st.timezone.as_deref(),
                )
                .map(|t| format!(" • {} {} ({})", t.icon, t.formatted_time, t.relative_badge()))
                .unwrap_or_default();
                if let Some(ref t) = *cur_title {
                    format!("{} - {}{}", st.name, t, time_str)
                } else {
                    format!("{}{}", st.name, time_str)
                }
            }
            (Some(st), PlaybackState::Buffering) => format!("TiMonde ({}) : {}", crate::i18n::tr("Connecting..."), st.name),
            (Some(st), PlaybackState::Paused) => format!("TiMonde ({}) : {}", crate::i18n::tr("Paused"), st.name),
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
            "/usr/share/icons/hicolor/scalable/panel",
            "/usr/share/icons/hicolor/scalable/apps",
            "/usr/share/icons/hicolor/24x24/panel",
            "/usr/share/icons/hicolor/22x22/panel",
            "/usr/share/icons/hicolor/24x24/apps",
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
            #[cfg(debug_assertions)]
            {
                let project_icons = concat!(env!("CARGO_MANIFEST_DIR"), "/data/icons");
                project_icons.to_string()
            }
            #[cfg(not(debug_assertions))]
            {
                "/usr/share/icons/hicolor/24x24/apps".to_string()
            }
        }
    }

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

    fn scroll(&mut self, delta: i32, _orientation: ksni::Orientation) {
        let step = if delta > 0 { -0.01 } else { 0.01 };
        let mut cur = self.current_volume.lock().unwrap();
        let new_vol = (*cur + step).clamp(0.0, 1.0);
        *cur = new_vol;
        drop(cur);
        let guard = self.audio.lock().unwrap();
        if let Some(ref engine) = *guard {
            engine.set_volume(new_vol);
        }
        drop(guard);
        std::thread::spawn(move || {
            let mut state = crate::state::AppState::load(&crate::state::AppState::default_path());
            state.volume = new_vol;
            let _ = state.save(&crate::state::AppState::default_path());
        });
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
                    icon_name: "media-playback-stop".to_string(),
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
                    icon_name: "media-playback-stop".to_string(),
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
                        icon_name: "media-playback-start".to_string(),
                        activate: Box::new(move |tray: &mut Self| {
                            tray.play_station(st_clone.clone());
                        }),
                        enabled: true,
                        visible: true,
                        ..Default::default()
                    }));
                } else {
                    menu.push(MenuItem::Standard(StandardItem {
                        label: crate::i18n::tr("No station loaded").to_string(),
                        icon_name: "audio-x-generic".to_string(),
                        enabled: false,
                        visible: true,
                        ..Default::default()
                    }));
                }
            }
        }

        // 2. Si une station est sélectionnée/en cours : Métadonnées, Titre, Fuseau horaire et Édition
        if let Some(ref st) = *cur_st {
            menu.push(MenuItem::Separator);

            // Titre en cours (si stream actif avec tag)
            if let Some(ref title) = *cur_title {
                if !title.trim().is_empty() {
                    let t_clone = title.clone();
                    menu.push(MenuItem::Standard(StandardItem {
                        label: format!("♪ {}", title),
                        icon_name: "audio-speakers".to_string(),
                        activate: Box::new(move |_tray: &mut Self| {
                            Self::copy_to_clipboard(&t_clone);
                        }),
                        enabled: true,
                        visible: true,
                        ..Default::default()
                    }));
                }
            }

            // Heure locale & Décalage horaire dynamique de la radio
            let time_info = crate::timezone::get_local_time_for_station(
                st.country.as_deref(),
                &st.name,
                None,
                st.timezone.as_deref(),
            );
            if let Some(t) = time_info {
                let diff_label = t.relative_badge();
                let tz_label = if diff_label.is_empty() {
                    format!("{} {} ({})", t.icon, t.formatted_time, t.country_name)
                } else {
                    format!("{} {} ({}, {})", t.icon, t.formatted_time, t.country_name, diff_label)
                };
                menu.push(MenuItem::Standard(StandardItem {
                    label: format!("   {}", tz_label),
                    icon_name: "appointment-soon".to_string(),
                    activate: Box::new(|_| {}),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));
            }

            // Boutons d'action : Édition (qui inclut la suppression) ou découverte éphémère
            if is_eph {
                let st_name = st.name.clone();
                menu.push(MenuItem::Standard(StandardItem {
                    label: format!("   {}", crate::i18n::save_ephemeral_label(&st_name)),
                    icon_name: "list-add".to_string(),
                    activate: Box::new(|tray: &mut Self| {
                        tray.trigger_save_current_ephemeral_station();
                    }),
                    enabled: true,
                    visible: true,
                    ..Default::default()
                }));

                menu.push(MenuItem::Standard(StandardItem {
                    label: format!("   {}", crate::i18n::tr("Zap to another random station")),
                    icon_name: "media-skip-forward".to_string(),
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
                    label: format!("   {}", crate::i18n::tr("Edit")),
                    icon_name: "document-edit".to_string(),
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
                icon_name: "media-playlist-shuffle".to_string(),
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
                        icon_name: "folder".to_string(),
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
            icon_name: "audio-volume-high".to_string(),
            submenu: vec![
                MenuItem::Standard(StandardItem {
                    label: "100%".to_string(),
                    activate: Box::new(|tray| {
                        tray.set_volume_level(1.0);
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "75%".to_string(),
                    activate: Box::new(|tray| {
                        tray.set_volume_level(0.75);
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "50%".to_string(),
                    activate: Box::new(|tray| {
                        tray.set_volume_level(0.50);
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "25%".to_string(),
                    activate: Box::new(|tray| {
                        tray.set_volume_level(0.25);
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: "10%".to_string(),
                    activate: Box::new(|tray| {
                        tray.set_volume_level(0.10);
                    }),
                    ..Default::default()
                }),
                MenuItem::Standard(StandardItem {
                    label: crate::i18n::tr("Mute (0%)").to_string(),
                    activate: Box::new(|tray| {
                        tray.set_volume_level(0.0);
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
            icon_name: "appointment-new".to_string(),
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

        // 6. Console de Paramètres unifiée (sans sous-menus)
        menu.push(MenuItem::Standard(StandardItem {
            label: crate::i18n::tr("Settings...").to_string(),
            icon_name: "preferences-system".to_string(),
            activate: Box::new(|tray: &mut Self| {
                Self::trigger_settings_dialog(
                    Arc::clone(&tray.root_group),
                    tray.bookmarks_path.clone(),
                    Arc::clone(&tray.tray_handle),
                );
            }),
            enabled: true,
            visible: true,
            ..Default::default()
        }));

        // 7. Quitter proprement l'application
        menu.push(MenuItem::Standard(StandardItem {
            label: crate::i18n::tr("Quit TiMonde").to_string(),
            icon_name: "application-exit".to_string(),
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
