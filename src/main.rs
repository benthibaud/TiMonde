pub mod i18n;
pub mod state;
pub mod import;
pub mod playlist;
pub mod mpris;
pub mod audio;
pub mod bookmarks;
pub mod models;
pub mod radio_browser;
pub mod tray;
pub mod timezone;
pub mod discovery;
pub mod cli;
pub mod sync_util;
pub mod probe;
pub mod notify;
pub mod session;

use bookmarks::{create_default_bookmarks, ensure_config_examples, find_bookmarks_path, load_bookmarks};
use ksni::blocking::TrayMethods;
use log::{error, info};
use models::Group;
use std::path::PathBuf;
use std::sync::Arc;
use sync_util::SafeLock;

/// Vérifie si un démon StatusNotifierWatcher est actif sur D-Bus (sans aucun sous-processus).
fn has_status_notifier_watcher() -> bool {
    if let Ok(connection) = zbus::blocking::Connection::session() {
        if let Ok(proxy) = zbus::blocking::Proxy::new(
            &connection,
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
        ) {
            let res: Result<bool, _> = proxy.call(
                "NameHasOwner",
                &("org.kde.StatusNotifierWatcher",),
            );
            return res.unwrap_or(false);
        }
    }
    false
}

/// Détecte si les descripteurs d'environnement graphique correspondent à GNOME Shell pur.
fn is_gnome_shell_env(desktop: &str, session: &str) -> bool {
    let d = desktop.to_uppercase();
    let s = session.to_uppercase();

    // Exclure formellement les environnements disposant de leur propre barre native
    for other in &["XFCE", "CINNAMON", "MATE", "KDE", "LXQT", "PANTHEON", "COSMIC", "ICEWM", "FLUXBOX"] {
        if d.contains(other) || s.contains(other) {
            return false;
        }
    }

    d.contains("GNOME") || s.contains("GNOME")
}

/// Détecte nativement si l'environnement graphique de session est GNOME Shell.
fn is_gnome_shell() -> bool {
    let desktop = std::env::var("XDG_CURRENT_DESKTOP").unwrap_or_default();
    let session = std::env::var("DESKTOP_SESSION").unwrap_or_default();
    is_gnome_shell_env(&desktop, &session)
}

/// Vérifie si un démon StatusNotifierWatcher est actif sur D-Bus.
/// S'il est absent (ex: bureau IceWM ou Fluxbox sous antiX), démarre automatiquement
/// le pont léger timonde_xembed_bridge.py pour créer une icône XEmbed compatible.
fn ensure_sni_host() -> Option<std::process::Child> {
    if !has_status_notifier_watcher() {
        info!("Aucun StatusNotifierWatcher détecté sur le bureau hôte (IceWM/Fluxbox).");
        if let Some(script_path) = crate::tray::TiMondeTray::find_script("timonde_xembed_bridge.py") {
            info!("Activation du pont XEmbed natif : {:?}", script_path);
            if let Ok(child) = std::process::Command::new("python3")
                .arg(&script_path)
                .spawn()
            {
                // Laisse le temps au script d'enregistrer le nom de service sur D-Bus
                std::thread::sleep(std::time::Duration::from_millis(200));
                return Some(child);
            }
        }
    }
    None
}

/// Vérifie l'intégration du bureau hôte.
/// Si l'environnement actif est GNOME Shell et que le support AppIndicator est manquant,
/// propose l'assistant graphique d'installation. Si l'utilisateur refuse ou annule,
/// retourne false pour interrompre le démarrage sans laisser tourner d'application invisible.
fn ensure_desktop_integration() -> bool {
    // Évaluation native sans aucun sous-processus Python
    if is_gnome_shell() && !has_status_notifier_watcher() {
        info!("Environnement GNOME Shell détecté sans support AppIndicator.");
        if let Some(script_path) = crate::tray::TiMondeTray::find_script("gnome_tray_helper.py") {
            info!("Lancement de l'assistant d'intégration GNOME...");
            if let Ok(prompt_st) = std::process::Command::new("python3")
                .arg(&script_path)
                .arg("--prompt")
                .status()
            {
                if !prompt_st.success() {
                    info!("Installation de l'intégration GNOME ignorée ou annulée. Arrêt propre de TiMonde.");
                    return false;
                }
            } else {
                return false;
            }
        }
    }
    true
}

fn main() {
    i18n::init_locale();
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());

    // 1. Gestion des arguments en ligne de commande (mode contrôle CLI et importation)
    let args: Vec<String> = std::env::args().collect();
    if cli::handle_cli(&args) {
        return;
    }

    // 2. Protection instance unique (évite les doublons d'icônes dans la barre des tâches)
    if mpris::is_instance_running() {
        println!("TiMonde est déjà actif dans la barre des tâches.");
        return;
    }

    // 3. Vérification de l'intégration du bureau (assistant interactif sous GNOME si AppIndicator manque)
    if !ensure_desktop_integration() {
        return;
    }

    // Optimisation stricte de la mémoire glibc :
    // - Limiter le nombre d arènes malloc à 1 pour éviter la multiplication des tas par thread
    // - Réduire le seuil de restitution mémoire au noyau (trim threshold)
    unsafe {
        libc::mallopt(-8, 1); // M_ARENA_MAX = 1
        libc::mallopt(-1, 64 * 1024); // M_TRIM_THRESHOLD = 64 Ko
        libc::mallopt(-3, 64 * 1024); // M_MMAP_THRESHOLD = 64 Ko
    }

    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    info!("========================================================");
    info!("Démarrage de TiMonde (Mode barre des tâches direct)");
    info!("========================================================");

    // 3. Chargement des favoris (avec migration transparente si seul radiotray-ng est présent)
    let bookmarks_path = find_bookmarks_path();
    ensure_config_examples(&PathBuf::from(&home).join(".config/timonde"));
    let root_group = if bookmarks_path.exists() {
        info!("Chargement des signets depuis : {:?}", bookmarks_path);
        match load_bookmarks(&bookmarks_path) {
            Ok(group) => {
                info!("{} stations chargées avec succès !", group.total_stations());
                group
            }
            Err(e) => {
                error!("Erreur lecture bookmarks ({}) -> création fallback", e);
                create_default_bookmarks(&bookmarks_path)
            }
        }
    } else {
        // Vérifier si un bookmarks.json de radiotray-ng existe pour conversion automatique
        let rtng_json = PathBuf::from(&home).join(".config/radiotray-ng/bookmarks.json");
        if rtng_json.exists() {
            info!("Migration automatique depuis radiotray-ng : {:?}", rtng_json);
            let mut new_root = Group::new("root");
            if let Ok(report) = import::import_file(&mut new_root, &rtng_json, None) {
                info!("{} stations migrées depuis radiotray-ng !", report.stations_added);
                let _ = bookmarks::save_bookmarks(&new_root, &bookmarks_path);
                new_root
            } else {
                create_default_bookmarks(&bookmarks_path)
            }
        } else {
            info!("Aucun fichier existant trouvé -> création de {:?}", bookmarks_path);
            create_default_bookmarks(&bookmarks_path)
        }
    };

    // 4. Initialisation du plateau système
    let tray = tray::TiMondeTray::new(root_group, bookmarks_path);

    // Restitution immédiate de la mémoire tas après parsing de bookmarks.xml
    #[cfg(target_os = "linux")]
    unsafe {
        libc::malloc_trim(0);
    }

    // Clones des Arcs partagés avec le serveur MPRIS2
    let session = Arc::clone(&tray.session);
    let last_station = Arc::clone(&tray.last_station);
    let root_group_clone = Arc::clone(&tray.root_group);
    let bookmarks_path_clone = tray.bookmarks_path.clone();
    let play_generation = Arc::clone(&tray.play_generation);

    let tray_handle_cell = Arc::clone(&tray.tray_handle);

    // Fonction de rafraîchissement asynchrone non-bloquante du tray
    let trigger_tray_update = {
        let handle_cell = Arc::clone(&tray_handle_cell);
        Arc::new(move || {
            tray::request_tray_refresh(&handle_cell);
        })
    };

    let trigger_for_play = Arc::clone(&trigger_tray_update);
    let trigger_for_stop = Arc::clone(&trigger_tray_update);
    let trigger_for_mpris = Arc::clone(&trigger_tray_update);

    let on_play = {
        let session = Arc::clone(&session);
        let last_station = Arc::clone(&last_station);
        let root_group = Arc::clone(&root_group_clone);
        let play_generation = Arc::clone(&play_generation);
        let bpath = bookmarks_path_clone.clone();
        let tray_handle = Arc::clone(&tray_handle_cell);

        Arc::new(move |station: models::Station| {
            tray::TiMondeTray::play_station_flow(
                station,
                &session,
                &last_station,
                &play_generation,
                &root_group,
                &bpath,
                &tray_handle,
            );
            trigger_for_play();
        })
    };

    let on_preview_play = {
        let session = Arc::clone(&session);
        let root_group = Arc::clone(&root_group_clone);
        let play_generation = Arc::clone(&play_generation);
        let bpath = bookmarks_path_clone.clone();
        let tray_handle = Arc::clone(&tray_handle_cell);
        let trigger_for_preview = Arc::clone(&trigger_tray_update);

        Arc::new(move |station: models::Station| {
            tray::TiMondeTray::play_ephemeral_flow(
                station,
                &session,
                &play_generation,
                &root_group,
                &bpath,
                &tray_handle,
            );
            trigger_for_preview();
        })
    };

    let on_stop = {
        let session = Arc::clone(&session);
        let play_generation = Arc::clone(&play_generation);

        Arc::new(move || {
            play_generation.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            tray::TiMondeTray::stop_and_trim_flow(&session);
            trigger_for_stop();
        })
    };

    let on_update = Arc::new(move || {
        trigger_for_mpris();
    });

    let on_reload = {
        let root_group = Arc::clone(&root_group_clone);
        let bpath = bookmarks_path_clone.clone();
        let tray_handle = Arc::clone(&tray_handle_cell);
        Arc::new(move || {
            let _ = tray::TiMondeTray::reload_bookmarks_and_update_tray(&root_group, &bpath, &tray_handle);
        })
    };

    // 5. Enregistrement du service D-Bus MPRIS2 (org.mpris.MediaPlayer2.timonde)
    mpris::spawn_mpris_server(
        Arc::clone(&session),
        last_station,
        Arc::clone(&root_group_clone),
        on_play,
        on_preview_play,
        on_stop,
        on_update,
        on_reload,
    );

    // 6. Détection du plateau hôte et pont XEmbed de secours (pour IceWM, Fluxbox, antiX)
    let _bridge_child = ensure_sni_host();

    // Enregistrement de l'icône dans la zone de notification (SNI)
    let handle = match tray.assume_sni_available(true).spawn() {
        Ok(h) => {
            info!("Icône StatusNotifierItem enregistrée sur le bureau hôte !");
            Some(h)
        }
        Err(e) => {
            log::warn!("Avertissement enregistrement Tray : {:?}. TiMonde reste actif en arrière-plan via MPRIS2/CLI.", e);
            None
        }
    };
    if let Some(h) = handle {
        *tray_handle_cell.safe_lock() = Some(h);
    }

    info!("TiMonde est actif et discret dans la barre des tâches.");

    // 7. Surveillance automatique de bookmarks.xml (rechargement si modification externe)
    {
        let root_watcher = Arc::clone(&root_group_clone);
        let bpath_watcher = bookmarks_path_clone.clone();
        let handle_watcher = Arc::clone(&tray_handle_cell);

        std::thread::spawn(move || {
            let mut last_modified = std::fs::metadata(&bpath_watcher)
                .and_then(|m| m.modified())
                .ok();

            loop {
                std::thread::sleep(std::time::Duration::from_secs(2));

                if let Ok(meta) = std::fs::metadata(&bpath_watcher) {
                    if let Ok(modified) = meta.modified() {
                        let cur_millis = modified
                            .duration_since(std::time::UNIX_EPOCH)
                            .map(|d| d.as_millis() as u64)
                            .unwrap_or(0);
                        let last_internal = tray::LAST_RELOAD_MTIME_MILLIS.load(std::sync::atomic::Ordering::SeqCst);

                        if Some(modified) != last_modified && cur_millis != last_internal {
                            last_modified = Some(modified);
                            info!("Fichier bookmarks.xml modifié, rechargement automatique...");
                            let _ = tray::TiMondeTray::reload_bookmarks_and_update_tray(
                                &root_watcher,
                                &bpath_watcher,
                                &handle_watcher,
                            );
                        } else if cur_millis == last_internal {
                            last_modified = Some(modified);
                        }
                    }
                }
            }
        });
    }

    // 8. Ticker low-tech d'actualisation de l'heure locale (1 fois par minute, calé sur la seconde 00)
    {
        let handle_clock = Arc::clone(&tray_handle_cell);
        let session_clock = Arc::clone(&session);

        if let Err(e) = std::thread::Builder::new()
            .name("timonde-clock-tick".to_string())
            .spawn(move || {
                loop {
                    let now_epoch = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .map(|d| d.as_secs())
                        .unwrap_or(0);
                    let rem = 60 - (now_epoch % 60);
                    // Dormir jusqu'à la seconde 00 de la prochaine minute (0% CPU, 0 allocation)
                    std::thread::sleep(std::time::Duration::from_secs(rem.max(1)));

                    // Rafraîchir l'heure uniquement si une radio est en cours d'écoute
                    let is_active = {
                        let s = session_clock.safe_lock();
                        s.current_station.is_some() && s.state() == audio::PlaybackState::Playing
                    };

                    if is_active {
                        tray::request_tray_refresh(&handle_clock);
                    }
                }
            })
        {
            log::error!("Impossible de lancer le ticker d'horloge : {}", e);
        }
    }

    // 9. Boucle d'événements GLib (maintient le processus actif et léger)
    let main_loop = gstreamer::glib::MainLoop::new(None, false);
    main_loop.run();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gnome_shell_detection() {
        assert!(is_gnome_shell_env("GNOME", "gnome"));
        assert!(is_gnome_shell_env("ubuntu:GNOME", "ubuntu"));
        assert!(!is_gnome_shell_env("XFCE", "xfce"));
        assert!(!is_gnome_shell_env("X-Cinnamon", "cinnamon"));
        assert!(!is_gnome_shell_env("KDE", "plasma"));
        assert!(!is_gnome_shell_env("antiX", "icewm"));
        assert!(!is_gnome_shell_env("Fluxbox", "fluxbox"));
        assert!(!is_gnome_shell_env("MATE", "mate"));
    }
}

