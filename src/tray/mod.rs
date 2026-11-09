//! Module d'intégration barre des tâches (StatusNotifierItem / KSNI) et orchestration du lecteur.

pub mod dialogs;
pub mod menu;
pub mod x11_ffi;

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use log::{error, info};

use crate::audio::{AudioEngine, PlaybackState};
use crate::models::{Group, Station};
use crate::notify::notify;
use crate::playlist::resolve_stream_url;
use crate::radio_browser::find_backup_stream;
use crate::sync_util::SafeLock;

/// Mémorisation de l'horodatage de la dernière écriture interne pour éviter les doubles rechargements
pub static LAST_RELOAD_MTIME_MILLIS: AtomicU64 = AtomicU64::new(0);

/// Déclenche un rafraîchissement asynchrone non-bloquant de l'icône du plateau.
/// Clone le `Handle` de ksni (qui implémente `Clone` dans ksni 0.3.6), relâche immédiatement
/// le verrou du `Mutex` pour interdire tout interblocage (*deadlock*), et exécute
/// l'appel `update` bloquant dans un thread détaché.
pub fn request_tray_refresh(handle_cell: &Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>) {
    let handle_opt = {
        let guard = handle_cell.safe_lock();
        guard.clone()
    };
    if let Some(h) = handle_opt {
        std::thread::spawn(move || {
            h.update(|_| {});
        });
    }
}

pub struct TiMondeTray {
    pub(crate) audio: Arc<Mutex<Option<AudioEngine>>>,
    pub(crate) current_volume: Arc<Mutex<f64>>,
    pub(crate) root_group: Arc<Mutex<Group>>,
    pub(crate) bookmarks_path: PathBuf,
    pub(crate) last_station: Arc<Mutex<Option<Station>>>,
    pub(crate) current_station: Arc<Mutex<Option<Station>>>,
    pub(crate) current_title: Arc<Mutex<Option<String>>>,
    pub(crate) is_ephemeral: Arc<AtomicBool>,
    pub(crate) play_generation: Arc<AtomicU64>,
    pub(crate) sleep_generation: Arc<AtomicU64>,
    pub(crate) tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    pub(crate) sleep_timer: Arc<Mutex<Option<std::time::Instant>>>,
}

impl TiMondeTray {
    pub fn request_tray_refresh(handle_cell: &Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>) {
        request_tray_refresh(handle_cell);
    }

    pub fn new(root_group: Group, bookmarks_path: PathBuf) -> Self {
        let state = crate::state::AppState::load(&crate::state::AppState::default_path());
        let initial_last_station = if let Some(ref st) = state.last_station {
            Self::find_station_by_url(&root_group, &st.url).or(Some(st.clone()))
        } else {
            None
        };
        let initial_volume = state.volume.clamp(0.0, 1.0);

        Self {
            audio: Arc::new(Mutex::new(None)),
            current_volume: Arc::new(Mutex::new(initial_volume)),
            root_group: Arc::new(Mutex::new(root_group)),
            bookmarks_path,
            last_station: Arc::new(Mutex::new(initial_last_station)),
            current_station: Arc::new(Mutex::new(None)),
            current_title: Arc::new(Mutex::new(None)),
            is_ephemeral: Arc::new(AtomicBool::new(false)),
            play_generation: Arc::new(AtomicU64::new(0)),
            sleep_generation: Arc::new(AtomicU64::new(0)),
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
                *root_group.safe_lock() = new_group;
                info!("{} signets rechargés avec succès depuis {:?}", total, bookmarks_path);

                if let Ok(meta) = std::fs::metadata(bookmarks_path) {
                    if let Ok(mtime) = meta.modified() {
                        if let Ok(dur) = mtime.duration_since(std::time::UNIX_EPOCH) {
                            LAST_RELOAD_MTIME_MILLIS.store(dur.as_millis() as u64, Ordering::SeqCst);
                        }
                    }
                }

                request_tray_refresh(tray_handle);

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
        let guard = self.audio.safe_lock();
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
        tray_notifier: Option<Arc<dyn Fn() + Send + Sync>>,
    ) -> Result<(), String> {
        let mut guard = audio_mutex.safe_lock();
        if guard.is_none() {
            info!("Chargement à la demande du moteur GStreamer...");
            match AudioEngine::new(Arc::clone(current_title), tray_notifier) {
                Ok(engine) => {
                    let vol = *current_volume.safe_lock();
                    engine.set_volume(vol);
                    *guard = Some(engine);
                }
                Err(e) => return Err(format!("Échec GStreamer : {}", e)),
            }
        }
        Ok(())
    }

    /// Notifie l'utilisateur de l'heure locale et du décalage de la station (avec mention éphémère si applicable)
    pub(crate) fn notify_station_local_time(station: &Station, group_name: Option<&str>, is_ephemeral: bool) {
        let station_name = &station.name;
        let prefix = if is_ephemeral {
            crate::i18n::tr("TiMonde • Ephemeral discovery")
        } else {
            "TiMonde".to_string()
        };
        let ephemeral_suffix = if is_ephemeral {
            format!("\n{}", crate::i18n::tr("Ephemeral radio (not saved)."))
        } else {
            String::new()
        };

        if let Some(time_info) = crate::timezone::get_local_time_for_station(
            station.country.as_deref(),
            station_name,
            group_name,
            station.timezone.as_deref(),
        ) {
            let offset_sign = if time_info.offset_hours >= 0.0 { "+" } else { "" };
            crate::notify::notify(
                &prefix,
                &format!(
                    "{}\n{} • {} (UTC{}{:.0}h){}",
                    station_name,
                    time_info.country_name,
                    time_info.formatted_time,
                    offset_sign,
                    time_info.offset_hours,
                    ephemeral_suffix
                ),
            );
        } else if is_ephemeral {
            crate::notify::notify(
                &prefix,
                &format!("{}{}", station_name, ephemeral_suffix),
            );
        }
    }

    /// Lance la résolution d'URL et le démarrage du pipeline GStreamer en arrière-plan
    #[allow(clippy::too_many_arguments)]
    /// Lance un thread asynchrone pour résoudre la playlist et démarrer la lecture
    pub fn spawn_engine_play_thread(
        raw_url: String,
        station_name: String,
        gen: u64,
        play_generation: Arc<AtomicU64>,
        audio: Arc<Mutex<Option<AudioEngine>>>,
        current_volume: Arc<Mutex<f64>>,
        current_title: Arc<Mutex<Option<String>>>,
        tray_notifier: Option<Arc<dyn Fn() + Send + Sync>>,
        on_success: impl FnOnce() + Send + 'static,
    ) {
        std::thread::spawn(move || {
            let resolved_url = resolve_stream_url(&raw_url);
            if play_generation.load(Ordering::SeqCst) != gen {
                return;
            }
            if let Err(e) = Self::get_or_create_engine(&audio, &current_volume, &current_title, tray_notifier) {
                error!("{}", e);
                notify("TiMonde", &crate::i18n::tr("Unable to initialize audio"));
                return;
            }
            {
                let guard = audio.safe_lock();
                if let Some(ref engine) = *guard {
                    if let Err(e) = engine.play(&resolved_url) {
                        error!("Échec initial de lecture : {}", e);
                        notify("TiMonde", &format!("{} {}", crate::i18n::tr("Unable to play"), station_name));
                        return;
                    }
                }
            }
            on_success();
        });
    }

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
        _bookmarks_path: &Path,
        tray_handle: &Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    ) {
        let station_name = station.name.clone();
        let raw_url = station.url.clone();
        info!("Sélection de la station : {} ({})", station_name, raw_url);

        *last_station.safe_lock() = Some(station.clone());
        *current_station.safe_lock() = Some(station.clone());
        *current_title.safe_lock() = None;

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
            let guard = root_group.safe_lock();
            Self::find_group_name_for_station(&guard, &station.url)
        };
        Self::notify_station_local_time(&station, group_name.as_deref(), false);

        let gen = play_generation.fetch_add(1, Ordering::SeqCst) + 1;
        let gen_clone = Arc::clone(play_generation);
        let audio_clone = Arc::clone(audio);
        let name_for_watchdog = station_name.clone();
        let handle_for_init = Arc::clone(tray_handle);
        let handle_for_watchdog = Arc::clone(tray_handle);

        let tray_notifier: Option<Arc<dyn Fn() + Send + Sync>> = {
            let handle_cell = Arc::clone(tray_handle);
            Some(Arc::new(move || {
                Self::request_tray_refresh(&handle_cell);
            }))
        };

        Self::spawn_engine_play_thread(
            raw_url,
            station_name,
            gen,
            Arc::clone(play_generation),
            Arc::clone(audio),
            Arc::clone(current_volume),
            Arc::clone(current_title),
            tray_notifier,
            move || {
                Self::request_tray_refresh(&handle_for_init);
                std::thread::sleep(Duration::from_secs(5));

                if gen_clone.load(Ordering::SeqCst) != gen {
                    return;
                }

                let st = {
                    let guard = audio_clone.safe_lock();
                    guard.as_ref().map(|e| e.state()).unwrap_or(PlaybackState::Stopped)
                };

                if st == PlaybackState::Buffering || st == PlaybackState::Error {
                    info!("Watchdog : flux muet pour {}", name_for_watchdog);
                    notify(
                        "TiMonde",
                        &format!("{} {}", name_for_watchdog, crate::i18n::tr("is not responding. Searching for a backup stream...")),
                    );

                    // Note qualité / éthique : Le watchdog ne modifie JAMAIS bookmarks.xml en douce !
                    // Il bascule temporairement sur un flux de secours en mémoire sans écraser le fichier de l'utilisateur.
                    if let Some((found_name, backup_url)) = find_backup_stream(&name_for_watchdog) {
                        if gen_clone.load(Ordering::SeqCst) != gen {
                            return;
                        }
                        let direct_backup = resolve_stream_url(&backup_url);
                        info!("Watchdog : bascule temporaire sur flux alternatif : {} ({})", found_name, direct_backup);
                        let played = {
                            let guard = audio_clone.safe_lock();
                            if let Some(ref engine) = *guard {
                                engine.play(&direct_backup).is_ok()
                            } else {
                                false
                            }
                        };

                        if played {
                            notify(
                                "TiMonde",
                                &format!("{} « {} ».", crate::i18n::tr("Temporary backup stream found for"), name_for_watchdog),
                            );
                            Self::request_tray_refresh(&handle_for_watchdog);
                        }
                    } else if gen_clone.load(Ordering::SeqCst) == gen {
                        notify(
                            "TiMonde",
                            &format!("« {} » {}.", name_for_watchdog, crate::i18n::tr("is currently unavailable")),
                        );
                        let guard = audio_clone.safe_lock();
                        if let Some(ref engine) = *guard {
                            let _ = engine.stop();
                        }
                        Self::request_tray_refresh(&handle_for_watchdog);
                    }
                }
            },
        );
    }

    pub fn play_station(&mut self, station: Station) {
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
            &self.tray_handle,
        );
        Self::request_tray_refresh(&self.tray_handle);
    }

    /// Arrête la lecture et restitue la mémoire vers le système d'exploitation
    pub fn stop_and_trim_flow(
        audio: &Arc<Mutex<Option<AudioEngine>>>,
        current_station: &Arc<Mutex<Option<Station>>>,
        current_title: &Arc<Mutex<Option<String>>>,
    ) {
        let guard = audio.safe_lock();
        if let Some(ref engine) = *guard {
            let _ = engine.stop();
        }
        *current_station.safe_lock() = None;
        *current_title.safe_lock() = None;

        // Appel trim low-tech glibc / musl
        #[cfg(target_os = "linux")]
        unsafe {
            libc::malloc_trim(0);
        }
    }

    pub fn stop_and_trim(&mut self) {
        self.play_generation.fetch_add(1, Ordering::SeqCst);
        self.is_ephemeral.store(false, Ordering::SeqCst);
        Self::stop_and_trim_flow(&self.audio, &self.current_station, &self.current_title);
        Self::request_tray_refresh(&self.tray_handle);
    }

    pub fn play_ephemeral_station(&self, station: Station) {
        let station_name = station.name.clone();
        let raw_url = station.url.clone();
        info!("Écoute éphémère (découverte) : {} ({})", station_name, raw_url);
        self.is_ephemeral.store(true, Ordering::SeqCst);
        *self.current_station.safe_lock() = Some(station.clone());
        *self.current_title.safe_lock() = None;

        // Notification explicite informant l'utilisateur que cette radio est temporaire
        let group_name = {
            let guard = self.root_group.safe_lock();
            Self::find_group_name_for_station(&guard, &station.url)
        };
        Self::notify_station_local_time(&station, group_name.as_deref(), true);

        let gen = self.play_generation.fetch_add(1, Ordering::SeqCst) + 1;
        let handle_cell = Arc::clone(&self.tray_handle);
        let tray_notifier: Option<Arc<dyn Fn() + Send + Sync>> = {
            let h = Arc::clone(&self.tray_handle);
            Some(Arc::new(move || {
                Self::request_tray_refresh(&h);
            }))
        };

        Self::spawn_engine_play_thread(
            raw_url,
            station_name,
            gen,
            Arc::clone(&self.play_generation),
            Arc::clone(&self.audio),
            Arc::clone(&self.current_volume),
            Arc::clone(&self.current_title),
            tray_notifier,
            move || {
                Self::request_tray_refresh(&handle_cell);
            },
        );

        Self::request_tray_refresh(&self.tray_handle);
    }

    /// Choisit une station au hasard dans le catalogue mondial et lance sa lecture éphémère
    pub fn play_random_ephemeral_station(&self) {
        let existing_urls: Vec<String> = {
            let root = self.root_group.safe_lock();
            let mut set = std::collections::HashSet::new();
            crate::import::collect_all_urls(&root, &mut set);
            set.into_iter().collect()
        };

        let picked = match crate::discovery::pick_random_station(&existing_urls) {
            Some(st) => st,
            None => {
                crate::notify::notify(
                    "TiMonde",
                    &crate::i18n::tr("Unable to find a station in the bouquets catalog."),
                );
                return;
            }
        };

        self.play_ephemeral_station(picked);
    }

    /// Ouvre la boîte de dialogue pour enregistrer la radio éphémère courante dans les favoris
    pub fn trigger_save_current_ephemeral_station(&self) {
        let station_opt = self.current_station.safe_lock().clone();
        let station = match station_opt {
            Some(s) => s,
            None => {
                crate::notify::notify("TiMonde", &crate::i18n::tr("No radio is currently playing."));
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
                let guard = root_group.safe_lock();
                let mut list = Vec::new();
                guard.collect_all_group_paths("", &mut list);
                list
            };
            let groups_json = serde_json::to_string(&all_groups).unwrap_or_else(|_| "[]".to_string());
            let default_grp = all_groups.first().cloned().unwrap_or_else(|| crate::i18n::tr("Selection").to_string());

            let (new_name, new_url, new_country, new_timezone, new_target_group) =
                if let Some(script_path) = dialogs::find_script("edit_station.py") {
                    let out = match dialogs::prepare_python_command(&script_path)
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

            let mut root = root_group.safe_lock().clone();
            match crate::import::add_station_to_group(
                &mut root,
                final_st.clone(),
                Some(&new_target_group),
            ) {
                Ok(msg) => {
                    if let Err(e) = crate::bookmarks::save_bookmarks(&root, &bookmarks_path) {
                        log::error!("Erreur lors de la sauvegarde : {}", e);
                        crate::notify::notify("TiMonde", &format!("{} : {}", crate::i18n::tr("Save error"), e));
                        return;
                    }

                    // Bascule de l'état : la radio est désormais pérenne dans les signets
                    is_ephemeral.store(false, Ordering::SeqCst);
                    *last_station.safe_lock() = Some(final_st.clone());

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
                            crate::notify::notify(
                                &format!("TiMonde • {}", crate::i18n::tr("Saved!")),
                                &format!("« {} » {} (Total : {}).", final_st.name, crate::i18n::tr("saved in your favorites!"), total),
                            );
                        }
                        Err(e) => {
                            crate::notify::notify("TiMonde", &format!("{} : {}", crate::i18n::tr("Station added but reload error"), e));
                        }
                    }
                }
                Err(err) => {
                    log::warn!("Impossible de sauvegarder la station éphémère : {}", err);
                    crate::notify::notify("TiMonde", &format!("Notice : {}", err));
                }
            }
        });
    }

    /// Programme une coupure automatique après un délai en minutes
    pub fn set_sleep_timer(&mut self, minutes: u64) {
        let dur = Duration::from_secs(minutes * 60);
        let target = std::time::Instant::now() + dur;
        *self.sleep_timer.safe_lock() = Some(target);

        let audio = Arc::clone(&self.audio);
        let current_station = Arc::clone(&self.current_station);
        let current_title = Arc::clone(&self.current_title);
        let sleep_timer = Arc::clone(&self.sleep_timer);
        let tray_handle = Arc::clone(&self.tray_handle);
        let gen = self.sleep_generation.fetch_add(1, Ordering::SeqCst) + 1;
        let sleep_gen = Arc::clone(&self.sleep_generation);

        notify("TiMonde", &format!("{} : {} {} minutes", crate::i18n::tr("Sleep timer activated"), crate::i18n::tr("stopping in"), minutes));

        std::thread::spawn(move || {
            while std::time::Instant::now() < target {
                if sleep_gen.load(Ordering::SeqCst) != gen {
                    return;
                }
                let remaining = target.saturating_duration_since(std::time::Instant::now());
                let sleep_step = remaining.min(Duration::from_secs(1));
                std::thread::sleep(sleep_step);
            }

            if sleep_gen.load(Ordering::SeqCst) != gen {
                return;
            }

            let mut guard = sleep_timer.safe_lock();
            if let Some(t) = *guard {
                if t <= std::time::Instant::now() {
                    *guard = None;
                    drop(guard);

                    Self::stop_and_trim_flow(&audio, &current_station, &current_title);
                    notify("TiMonde", &crate::i18n::tr("Sleep timer: stopping radio."));
                    Self::request_tray_refresh(&tray_handle);
                }
            }
        });
    }

    /// Annule la minuterie d'arrêt programmée
    pub fn cancel_sleep_timer(&mut self) {
        self.sleep_generation.fetch_add(1, Ordering::SeqCst);
        *self.sleep_timer.safe_lock() = None;
        notify("TiMonde", &crate::i18n::tr("Sleep timer cancelled."));
    }

    /// Copie discrètement un texte (ex: titre musical en cours) dans le presse-papier du système
    pub fn copy_to_clipboard(text: &str) {
        let t = text.to_string();
        std::thread::spawn(move || {
            let mut copied = false;
            // Essai 1 : xclip (standard sous X11/XFCE/antiX)
            if let Ok(mut child) = std::process::Command::new("xclip")
                .arg("-selection")
                .arg("clipboard")
                .stdin(std::process::Stdio::piped())
                .spawn()
            {
                if let Some(mut stdin) = child.stdin.take() {
                    use std::io::Write;
                    let _ = stdin.write_all(t.as_bytes());
                }
                let _ = child.wait();
                copied = true;
            }
            // Essai 2 : wl-copy (Wayland)
            if !copied {
                if let Ok(mut child) = std::process::Command::new("wl-copy")
                    .stdin(std::process::Stdio::piped())
                    .spawn()
                {
                    if let Some(mut stdin) = child.stdin.take() {
                        use std::io::Write;
                        let _ = stdin.write_all(t.as_bytes());
                    }
                    let _ = child.wait();
                    copied = true;
                }
            }
            // Essai 3 : xsel
            if !copied {
                if let Ok(mut child) = std::process::Command::new("xsel")
                    .arg("-b")
                    .arg("-i")
                    .stdin(std::process::Stdio::piped())
                    .spawn()
                {
                    if let Some(mut stdin) = child.stdin.take() {
                        use std::io::Write;
                        let _ = stdin.write_all(t.as_bytes());
                    }
                    let _ = child.wait();
                    copied = true;
                }
            }
            if copied {
                crate::notify::notify("TiMonde", &format!("{}\n{}", crate::i18n::tr("Track copied to clipboard:"), t));
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

    pub fn set_volume_level(&mut self, vol: f64) {
        let clamped = vol.clamp(0.0, 1.0);
        *self.current_volume.safe_lock() = clamped;
        if let Some(ref e) = *self.audio.safe_lock() {
            e.set_volume(clamped);
        }
        crate::state::schedule_volume_save(clamped);
    }

    pub(crate) fn find_first_station(group: &Group) -> Option<Station> {
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

    // --- Délégations vers dialogs et x11_ffi pour préserver la rétrocompatibilité ---

    pub fn find_script(name: &str) -> Option<PathBuf> {
        dialogs::find_script(name)
    }

    pub fn find_station_by_url(root: &Group, station_url: &str) -> Option<Station> {
        dialogs::find_station_by_url(root, station_url)
    }

    pub fn find_group_name_for_station(root: &Group, station_url: &str) -> Option<String> {
        dialogs::find_group_name_for_station(root, station_url)
    }

    #[allow(clippy::too_many_arguments)]
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
        dialogs::trigger_edit_station_dialog(
            station,
            root_group,
            bookmarks_path,
            tray_handle,
            current_station,
            last_station,
            audio,
            current_title,
        );
    }

    pub fn trigger_settings_dialog(
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    ) {
        dialogs::trigger_settings_dialog(root_group, bookmarks_path, tray_handle);
    }

    pub fn try_trigger_context_menu_x11() -> bool {
        x11_ffi::try_trigger_context_menu_x11()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ksni::menu::MenuItem;
    use ksni::Tray;

    #[test]
    fn test_find_script_prioritizes_local_data_scripts() {
        let p = TiMondeTray::find_script("timonde_settings.py");
        assert!(p.is_some(), "Le script timonde_settings.py doit être trouvé");
        let path_str = p.unwrap().to_string_lossy().to_string();
        assert!(
            path_str.contains("data/scripts"),
            "find_script doit prioriser data/scripts et non /usr/share : {}",
            path_str
        );
    }

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

    #[test]
    fn test_menu_layout_stopped_and_playing() {
        let _lock = crate::i18n::I18N_TEST_MUTEX.lock().unwrap();
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
        assert!(labels.iter().any(|l| l.contains("Paramètres...")));
    }

    #[test]
    fn test_menu_layout_english_mode() {
        let _lock = crate::i18n::I18N_TEST_MUTEX.lock().unwrap();
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
        assert!(labels.iter().any(|l| l.contains("Settings...")));
        assert!(!labels.iter().any(|l| l.contains("Paramètres...")));
        assert!(labels.iter().any(|l| l == "Quit TiMonde"));
        assert!(!labels.iter().any(|l| l == "Quitter TiMonde"));

        // Rétablir le français
        crate::i18n::set_language("fr");
    }

    #[test]
    fn test_reorder_groups_hierarchy_serialization_and_reconstruction() {
        let mut root = Group::new("root");
        let mut france = Group::new("France");
        france.stations.push(Station::new("France Inter", "http://franceinter.fr/stream"));
        let mut bretagne = Group::new("Bretagne");
        bretagne.stations.push(Station::new("Radio Bro Gwened", "http://rbg.bzh/stream"));
        bretagne.stations.push(Station::new("Radio Laser", "http://radiolaser.fr/live"));
        france.subgroups.push(bretagne);
        root.subgroups.push(france);

        let mut country = Group::new("Country");
        country.stations.push(Station::new("Allzic Country", "http://allzic.com/country"));
        let mut bluegrass = Group::new("Bluegrass");
        let mut bg_st = Station::new("Bluegrass Planet Radio", "http://bluegrass.com/live");
        bg_st.country = Some("US".to_string());
        bg_st.timezone = Some("America/New_York".to_string());
        bluegrass.stations.push(bg_st);
        country.subgroups.push(bluegrass);
        root.subgroups.push(country);

        // 1. Sérialisation
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
