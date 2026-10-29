//! Gestion et lancement des boîtes de dialogue et outils auxiliaires (Python/GTK3).

use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::{Arc, Mutex};

use crate::audio::AudioEngine;
use crate::models::{Group, Station};
use crate::tray::TiMondeTray;

/// Recherche unifiée d'un script Python compagnon (archive portable, deb/rpm, local ou dev)
pub fn find_script(script_name: &str) -> Option<PathBuf> {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());

    // 1. Relatif au binaire en cours d'exécution (dossier dev target/release ou target/debug, ou archive portable)
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            // Cas standard du binaire de test compilé dans target/release ou target/debug
            let candidate_dev_root = exe_dir.join("../../data/scripts").join(script_name);
            if candidate_dev_root.exists() {
                return Some(candidate_dev_root);
            }
            let candidate_parent_data = exe_dir.join("../data/scripts").join(script_name);
            if candidate_parent_data.exists() {
                return Some(candidate_parent_data);
            }
            let candidate_rel_data = exe_dir.join("data/scripts").join(script_name);
            if candidate_rel_data.exists() {
                return Some(candidate_rel_data);
            }
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
        }
    }

    // 2. Dossier relatif au répertoire courant de travail
    let dev_path = PathBuf::from("data/scripts").join(script_name);
    if dev_path.exists() {
        return Some(dev_path);
    }

    // 3. Emplacement utilisateur XDG ~/.local/share/timonde/scripts/
    let user_share = PathBuf::from(&home).join(".local/share/timonde/scripts").join(script_name);
    if user_share.exists() {
        return Some(user_share);
    }

    // 4. Emplacement système officiel du paquet (.deb, .rpm)
    let sys_share = PathBuf::from("/usr/share/timonde/scripts").join(script_name);
    if sys_share.exists() {
        return Some(sys_share);
    }
    let local_sys_share = PathBuf::from("/usr/local/share/timonde/scripts").join(script_name);
    if local_sys_share.exists() {
        return Some(local_sys_share);
    }

    None
}

/// Prépare une commande Python en nettoyant l'environnement GTK/IBus
pub fn prepare_python_command<P: AsRef<Path>>(program: P) -> Command {
    let mut cmd = Command::new(program.as_ref());
    // Neutralisation absolue des variables de méthodes de saisie orphelines (ex: socket IBus manquante)
    // qui bloquent la saisie des touches clavier dans GTK3.
    cmd.env_remove("GTK_IM_MODULE");
    cmd.env_remove("XMODIFIERS");
    cmd.env_remove("QT_IM_MODULE");
    cmd
}

/// Recherche récursive d'une station par son URL dans l'arbre des groupes
pub fn find_station_by_url(root: &Group, station_url: &str) -> Option<Station> {
    let norm = crate::import::normalize_url(station_url);
    for s in &root.stations {
        if !s.is_separator() && (s.url == station_url || crate::import::normalize_url(&s.url) == norm) {
            return Some(s.clone());
        }
    }
    for sub in &root.subgroups {
        if let Some(found) = find_station_by_url(sub, station_url) {
            return Some(found);
        }
    }
    None
}

/// Recherche récursive du chemin hiérarchique du groupe contenant une station donnée (ex: "France/Bretagne")
pub fn find_group_name_for_station(root: &Group, station_url: &str) -> Option<String> {
    let norm = crate::import::normalize_url(station_url);
    fn find_rec(group: &Group, prefix: &str, url: &str, norm: &str) -> Option<String> {
        for sub in &group.subgroups {
            if sub.is_separator() {
                continue;
            }
            let current_path = if prefix.is_empty() {
                sub.name.clone()
            } else {
                format!("{}/{}", prefix, sub.name)
            };
            for s in &sub.stations {
                if !s.is_separator() && (s.url == url || crate::import::normalize_url(&s.url) == norm) {
                    return Some(current_path);
                }
            }
            if let Some(found) = find_rec(sub, &current_path, url, norm) {
                return Some(found);
            }
        }
        None
    }
    find_rec(root, "", station_url, &norm)
}

/// Ouvre la boîte de dialogue pour modifier le nom, l'URL, le groupe et le code pays de la station
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
    std::thread::spawn(move || {
        // Rapatriement infaillible de la station réelle dans les signets par son URL
        let (real_name, real_country, real_tz) = {
            let guard = root_group.lock().unwrap();
            if let Some(found) = find_station_by_url(&guard, &station.url) {
                (
                    if station.name.trim().is_empty() {
                        found.name
                    } else {
                        station.name.clone()
                    },
                    station.country.clone().or(found.country),
                    station.timezone.clone().or(found.timezone),
                )
            } else {
                (
                    station.name.clone(),
                    station.country.clone(),
                    station.timezone.clone(),
                )
            }
        };

        let current_group_name = {
            let guard = root_group.lock().unwrap();
            find_group_name_for_station(&guard, &station.url)
        }
        .unwrap_or_else(|| "Sélection".to_string());

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
            crate::timezone::get_local_time_for_station(
                None,
                &real_name,
                Some(&current_group_name),
                real_tz.as_deref(),
            )
            .map(|t| t.country_code)
            .unwrap_or_default()
        };

        let deduced_tz = if let Some(ref tz) = real_tz {
            tz.clone()
        } else {
            crate::timezone::get_local_time_for_station(
                Some(&deduced_country),
                &real_name,
                Some(&current_group_name),
                None,
            )
            .map(|t| t.timezone)
            .unwrap_or_default()
        };

        let (new_name, new_url, new_country, new_timezone, new_target_group) =
            if let Some(script_path) = find_script("edit_station.py") {
                let out = match prepare_python_command(&script_path)
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
                            cur.as_ref()
                                .map(|c| {
                                    crate::import::normalize_url(&c.url)
                                        == crate::import::normalize_url(&station.url)
                                })
                                .unwrap_or(false)
                        };
                        if is_current {
                            TiMondeTray::stop_and_trim_flow(&audio, &current_station, &current_title);
                        }
                        {
                            let mut last = last_station.lock().unwrap();
                            if last
                                .as_ref()
                                .map(|l| {
                                    crate::import::normalize_url(&l.url)
                                        == crate::import::normalize_url(&station.url)
                                })
                                .unwrap_or(false)
                            {
                                *last = None;
                                let mut state =
                                    crate::state::AppState::load(&crate::state::AppState::default_path());
                                state.last_station = None;
                                let _ = state.save(&crate::state::AppState::default_path());
                            }
                        }
                        crate::radio_browser::notify(
                            "TiMonde",
                            &format!("« {} » {}", station.name, crate::i18n::tr("deleted from your favorites.")),
                        );
                        crate::tray::request_tray_refresh(&tray_handle);
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
            crate::radio_browser::notify("TiMonde", &format!("{} : {}", crate::i18n::tr("Save error"), e));
            return;
        }

        // Mettre à jour current_station si elle était en cours
        {
            let mut cur = current_station.lock().unwrap();
            if let Some(ref mut c) = *cur {
                if crate::import::normalize_url(&c.url) == crate::import::normalize_url(&station.url)
                    || c.name == station.name
                {
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
                if crate::import::normalize_url(&l.url) == crate::import::normalize_url(&station.url)
                    || l.name == station.name
                {
                    l.name = new_name.clone();
                    l.url = new_url.clone();
                    if let Some(nc) = &new_country {
                        l.country = nc.clone();
                    }
                    if let Some(ntz) = &new_timezone {
                        l.timezone = ntz.clone();
                    }
                }
            }
        }

        let _ = TiMondeTray::reload_bookmarks_and_update_tray(&root_group, &bookmarks_path, &tray_handle);
        log::info!("Station modifiée : {} -> {}", station.name, new_name);
        crate::radio_browser::notify("TiMonde", &format!("« {} » {}", new_name, crate::i18n::tr("updated successfully!")));
    });
}

/// Ouvre la Console de Paramètres TiMonde unifiée (timonde_settings.py)
pub fn trigger_settings_dialog(
    root_group: Arc<Mutex<Group>>,
    bookmarks_path: PathBuf,
    tray_handle: Arc<Mutex<Option<ksni::blocking::Handle<TiMondeTray>>>>,
) {
    std::thread::spawn(move || {
        let script_path = match find_script("timonde_settings.py") {
            Some(p) => p,
            None => {
                log::error!("Script timonde_settings.py introuvable");
                crate::radio_browser::notify("TiMonde", crate::i18n::tr("Settings console not found"));
                return;
            }
        };

        let bookmarks_str = bookmarks_path.to_string_lossy().to_string();
        let mut cmd = prepare_python_command("python3");
        cmd.arg(&script_path);
        cmd.arg(&bookmarks_str);

        let output = match cmd.output() {
            Ok(out) => out,
            Err(e) => {
                log::error!("Impossible d'exécuter timonde_settings.py : {}", e);
                return;
            }
        };

        if output.status.success() {
            let stdout_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(&stdout_str) {
                if json_val["reload"].as_bool().unwrap_or(false) {
                    let total = TiMondeTray::reload_bookmarks_and_update_tray(&root_group, &bookmarks_path, &tray_handle)
                        .unwrap_or(0);
                    log::info!(
                        "Signets rechargés suite aux modifications des paramètres. Total : {} stations",
                        total
                    );
                }
            }
        }
    });
}
