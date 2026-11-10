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

static REFRESH_RUNNING: AtomicBool = AtomicBool::new(false);
static REFRESH_REQUESTED: AtomicBool = AtomicBool::new(false);

/// Déclenche un rafraîchissement asynchrone non-bloquant de l'icône du plateau.
/// Intègre un coalescing / debouncing de 40 ms pour agréger les rafales de requêtes
/// (ex: fermeture de dialogue + arrêt flux + rechargement) en une seule mise à jour ksni/D-Bus,
/// évitant l'invalidation répétée d'item_id_offset et la désynchronisation du plugin XFCE.
pub fn request_tray_refresh(handle_cell: &Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>) {
    let handle_opt = {
        let guard = handle_cell.safe_lock();
        guard.clone()
    };
    if let Some(h) = handle_opt {
        REFRESH_REQUESTED.store(true, Ordering::SeqCst);
        if REFRESH_RUNNING.compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst).is_ok() {
            std::thread::spawn(move || {
                loop {
                    REFRESH_REQUESTED.store(false, Ordering::SeqCst);
                    std::thread::sleep(std::time::Duration::from_millis(40));
                    h.update(|_| {});
                    if !REFRESH_REQUESTED.load(Ordering::SeqCst) {
                        REFRESH_RUNNING.store(false, Ordering::SeqCst);
                        if REFRESH_REQUESTED.load(Ordering::SeqCst)
                            && REFRESH_RUNNING.compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst).is_ok()
                        {
                            continue;
                        }
                        break;
                    }
                }
            });
        }
    }
}

pub struct TiMondeTray {
    pub(crate) session: Arc<Mutex<crate::session::PlaybackSession>>,
    pub(crate) root_group: Arc<Mutex<Group>>,
    pub(crate) bookmarks_path: PathBuf,
    pub(crate) last_station: Arc<Mutex<Option<Station>>>,
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
        let session = Arc::new(Mutex::new(crate::session::PlaybackSession::new(initial_volume)));

        Self {
            session,
            root_group: Arc::new(Mutex::new(root_group)),
            bookmarks_path,
            last_station: Arc::new(Mutex::new(initial_last_station)),
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
        self.session.safe_lock().state()
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
        session: Arc<Mutex<crate::session::PlaybackSession>>,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
        on_success: impl FnOnce() + Send + 'static,
    ) {
        std::thread::spawn(move || {
            let resolved_url = resolve_stream_url(&raw_url);
            if play_generation.load(Ordering::SeqCst) != gen {
                return;
            }

            // 1. Extraire et arrêter l'ancien moteur hors de tout verrou applicatif
            let old_engine = {
                let mut s = session.safe_lock();
                s.engine.take()
            };
            if let Some(engine) = old_engine {
                let _ = engine.stop();
                drop(engine);
            }

            // 2. Définir le callback de tag Titre découplé
            let session_for_title = Arc::clone(&session);
            let handle_for_title = Arc::clone(&tray_handle);
            let on_title = Arc::new(move |title: String| {
                let changed = {
                    let mut s = session_for_title.safe_lock();
                    let is_new = s.current_title.as_deref() != Some(&title);
                    if is_new {
                        s.current_title = Some(title.clone());
                    }
                    is_new
                };
                if changed {
                    crate::notify::notify("TiMonde", &title);
                    Self::request_tray_refresh(&handle_for_title);
                }
            });

            let handle_for_tray = Arc::clone(&tray_handle);
            let tray_notifier = Some(Arc::new(move || {
                Self::request_tray_refresh(&handle_for_tray);
            }) as Arc<dyn Fn() + Send + Sync>);

            let vol = {
                let s = session.safe_lock();
                s.volume
            };

            // 3. Instancier le moteur audio et démarrer le flux (hors verrou)
            let engine = match AudioEngine::new(Some(on_title), tray_notifier) {
                Ok(e) => e,
                Err(e) => {
                    error!("{}", e);
                    notify("TiMonde", &crate::i18n::tr("Unable to initialize audio"));
                    return;
                }
            };
            engine.set_volume(vol);

            if play_generation.load(Ordering::SeqCst) != gen {
                return;
            }

            if let Err(e) = engine.play(&resolved_url) {
                error!("Échec initial de lecture : {}", e);
                notify("TiMonde", &format!("{} {}", crate::i18n::tr("Unable to play"), station_name));
                return;
            }

            // 4. Stocker le moteur dans la session SI ET SEULEMENT SI la génération est toujours valide
            let still_valid = {
                let mut s = session.safe_lock();
                if play_generation.load(Ordering::SeqCst) != gen {
                    false
                } else {
                    s.engine = Some(Arc::new(engine));
                    true
                }
            };

            if !still_valid {
                info!("Abandon du démarrage : génération expirée pendant l'init pour '{}'", station_name);
                return;
            }

            on_success();
        });
    }

    #[allow(clippy::too_many_arguments)]
    pub fn play_station_flow(
        station: Station,
        session: &Arc<Mutex<crate::session::PlaybackSession>>,
        last_station: &Arc<Mutex<Option<Station>>>,
        play_generation: &Arc<AtomicU64>,
        root_group: &Arc<Mutex<Group>>,
        _bookmarks_path: &Path,
        tray_handle: &Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    ) {
        let station_name = station.name.clone();
        let raw_url = station.url.clone();
        info!("Sélection de la station : {} ({})", station_name, raw_url);

        *last_station.safe_lock() = Some(station.clone());
        {
            let mut s = session.safe_lock();
            s.current_station = Some(station.clone());
            s.current_title = None;
            s.is_ephemeral = false;
        }

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
        let session_clone = Arc::clone(session);
        let name_for_watchdog = station_name.clone();
        let handle_for_init = Arc::clone(tray_handle);
        let handle_for_watchdog = Arc::clone(tray_handle);

        Self::spawn_engine_play_thread(
            raw_url,
            station_name,
            gen,
            Arc::clone(play_generation),
            Arc::clone(session),
            Arc::clone(tray_handle),
            move || {
                Self::request_tray_refresh(&handle_for_init);
                std::thread::sleep(Duration::from_secs(5));

                if gen_clone.load(Ordering::SeqCst) != gen {
                    return;
                }

                let st = session_clone.safe_lock().state();

                if st == PlaybackState::Buffering || st == PlaybackState::Error {
                    info!("Watchdog : flux muet pour {}", name_for_watchdog);
                    notify(
                        "TiMonde",
                        &format!("{} {}", name_for_watchdog, crate::i18n::tr("is not responding. Searching for a backup stream...")),
                    );

                    if let Some((found_name, backup_url)) = find_backup_stream(&name_for_watchdog) {
                        if gen_clone.load(Ordering::SeqCst) != gen {
                            return;
                        }
                        let direct_backup = resolve_stream_url(&backup_url);
                        info!("Watchdog : bascule temporaire sur flux alternatif : {} ({})", found_name, direct_backup);
                        let engine_opt = {
                            let s = session_clone.safe_lock();
                            s.engine.clone()
                        };
                        let played = if let Some(ref engine) = engine_opt {
                            engine.play(&direct_backup).is_ok()
                        } else {
                            false
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
                        crate::session::stop_session(&session_clone);
                        Self::request_tray_refresh(&handle_for_watchdog);
                    }
                }
            },
        );
    }

    pub fn play_station(&mut self, station: Station) {
        Self::play_station_flow(
            station,
            &self.session,
            &self.last_station,
            &self.play_generation,
            &self.root_group,
            &self.bookmarks_path,
            &self.tray_handle,
        );
        Self::request_tray_refresh(&self.tray_handle);
    }

    /// Arrête la lecture et restitue immédiatement la mémoire vers le système d'exploitation
    pub fn stop_and_trim_flow(session: &Arc<Mutex<crate::session::PlaybackSession>>) {
        crate::session::stop_session(session);
    }

    pub fn stop_and_trim(&mut self) {
        self.play_generation.fetch_add(1, Ordering::SeqCst);
        Self::stop_and_trim_flow(&self.session);
        Self::request_tray_refresh(&self.tray_handle);
    }

    /// Lance la lecture d'une station éphémère ou d'une pré-écoute sans écraser last_station ni state.json
    #[allow(clippy::too_many_arguments)]
    pub fn play_ephemeral_flow(
        station: Station,
        session: &Arc<Mutex<crate::session::PlaybackSession>>,
        play_generation: &Arc<AtomicU64>,
        root_group: &Arc<Mutex<Group>>,
        _bookmarks_path: &Path,
        tray_handle: &Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
    ) {
        let station_name = station.name.clone();
        let raw_url = station.url.clone();
        info!("Écoute éphémère / pré-écoute : {} ({})", station_name, raw_url);

        let group_name = {
            let guard = root_group.safe_lock();
            Self::find_group_name_for_station(&guard, &station.url)
        };
        Self::notify_station_local_time(&station, group_name.as_deref(), true);

        {
            let mut s = session.safe_lock();
            s.current_station = Some(station.clone());
            s.current_title = None;
            s.is_ephemeral = true;
        }

        let gen = play_generation.fetch_add(1, Ordering::SeqCst) + 1;
        let handle_for_init = Arc::clone(tray_handle);

        Self::spawn_engine_play_thread(
            raw_url,
            station_name,
            gen,
            Arc::clone(play_generation),
            Arc::clone(session),
            Arc::clone(tray_handle),
            move || {
                Self::request_tray_refresh(&handle_for_init);
            },
        );

        Self::request_tray_refresh(tray_handle);
    }

    pub fn play_ephemeral_station(&self, station: Station) {
        Self::play_ephemeral_flow(
            station,
            &self.session,
            &self.play_generation,
            &self.root_group,
            &self.bookmarks_path,
            &self.tray_handle,
        );
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
        let station_opt = self.session.safe_lock().current_station.clone();
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
        let session = Arc::clone(&self.session);
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
                    session.safe_lock().is_ephemeral = false;
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

        let session = Arc::clone(&self.session);
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

                    Self::stop_and_trim_flow(&session);
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
        self.session.safe_lock().set_volume(clamped);
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
        session: Arc<Mutex<crate::session::PlaybackSession>>,
        last_station: Arc<Mutex<Option<Station>>>,
        play_generation: Arc<AtomicU64>,
    ) {
        dialogs::trigger_edit_station_dialog(
            station,
            root_group,
            bookmarks_path,
            tray_handle,
            session,
            last_station,
            play_generation,
        );
    }

    #[allow(clippy::too_many_arguments)]
    pub fn trigger_settings_dialog(
        root_group: Arc<Mutex<Group>>,
        bookmarks_path: PathBuf,
        tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
        session: Arc<Mutex<crate::session::PlaybackSession>>,
        play_generation: Arc<AtomicU64>,
    ) {
        dialogs::trigger_settings_dialog(
            root_group,
            bookmarks_path,
            tray_handle,
            session,
            play_generation,
        );
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
        {
            let mut s = tray.session.lock().unwrap();
            s.current_station = Some(Station::new("Bluegrass Planet Radio", "http://65.108.105.26:7966/stream"));
            s.current_title = Some("Matt Combs - Fifty Years of Clown School".to_string());
        }

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
        {
            let mut s = tray.session.lock().unwrap();
            s.current_station = Some(Station::new("Bluegrass Planet Radio", "http://65.108.105.26:7966/stream"));
            s.current_title = Some("Country Song".to_string());
        }

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
    fn test_menu_layout_ephemeral_preview_and_stop_coherence() {
        let _lock = crate::i18n::I18N_TEST_MUTEX.lock().unwrap();
        crate::i18n::set_language("fr");

        let xml = r#"
        <bookmarks>
            <group name="Musique">
                <bookmark name="FIP" url="http://direct.fipradio.fr/live/fip-midfi.mp3"/>
            </group>
        </bookmarks>
        "#;
        let root = crate::bookmarks::parse_bookmarks_reader(xml.as_bytes()).unwrap();
        let bpath = std::path::PathBuf::from("/tmp/bookmarks_test_preview.xml");
        let mut tray = TiMondeTray::new(root, bpath);

        // Radio permanente habituelle de l'utilisateur
        let fip_station = Station::new("FIP", "http://direct.fipradio.fr/live/fip-midfi.mp3");
        *tray.last_station.lock().unwrap() = Some(fip_station.clone());

        // 1. Initialement éteint : le menu propose d'écouter FIP
        let menu_initial = tray.menu();
        match &menu_initial[0] {
            MenuItem::Standard(item) => {
                assert!(item.label.contains("Écouter") && item.label.contains("FIP"));
            }
            _ => panic!("Le premier élément doit être le bouton Écouter"),
        }

        // 2. Simulation d'une pré-écoute éphémère dans les paramètres (Radio Test)
        let preview_station = Station::new("Radio Test", "http://stream.test/live.mp3");
        tray.play_ephemeral_station(preview_station);

        assert!(tray.session.lock().unwrap().is_ephemeral, "Le mode éphémère doit être activé");
        assert_eq!(tray.session.lock().unwrap().current_station.as_ref().unwrap().name, "Radio Test");
        // Règle d'or : last_station n'a PAS été écrasé par la pré-écoute
        assert_eq!(tray.last_station.lock().unwrap().as_ref().unwrap().name, "FIP");

        // 3. Arrêt de la pré-écoute
        tray.stop_and_trim();

        assert!(!tray.session.lock().unwrap().is_ephemeral, "Le mode éphémère doit être désactivé");
        assert!(tray.session.lock().unwrap().current_station.is_none(), "current_station doit être None après arrêt");
        assert_eq!(tray.last_station.lock().unwrap().as_ref().unwrap().name, "FIP", "last_station reste FIP");

        // 4. Vérification du menu après arrêt : il doit afficher « Écouter : « FIP » » sans nécessiter de clic éteindre préalable
        let menu_after_stop = tray.menu();
        match &menu_after_stop[0] {
            MenuItem::Standard(item) => {
                assert!(item.label.contains("Écouter") && item.label.contains("FIP"),
                    "Après arrêt de la pré-écoute, le menu doit immédiatement proposer d'écouter la station permanente : {}", item.label);
                assert!(!item.label.contains("Éteindre"), "Le menu ne doit en aucun cas afficher Éteindre après arrêt");
            }
            _ => panic!("Le premier élément doit être le bouton Écouter"),
        }
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
                    { "name": "Bluegrass Planet Radio", "url": "http://bluegrass.com/live", "country": "US", "timezone": "America/New_York" }
                ]
            }
        ]"#;

        let new_root = crate::bookmarks::rebuild_root_from_json(returned_json).unwrap();

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
