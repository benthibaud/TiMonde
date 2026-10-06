pub mod import;
pub mod playlist;
pub mod mpris;
pub mod audio;
pub mod bookmarks;
pub mod models;
pub mod radio_browser;
pub mod tray;

use bookmarks::load_bookmarks;
use ksni::blocking::TrayMethods;
use log::{error, info};
use models::Group;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

/// Localise le fichier bookmarks.xml de l'utilisateur
fn find_bookmarks_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());

    // 1. Emplacement officiel TiMonde
    let timonde_path = PathBuf::from(&home).join(".config/timonde/bookmarks.xml");
    if timonde_path.exists() {
        return timonde_path;
    }

    // 2. Ancien emplacement radiotray-lite
    let rt_lite_path = PathBuf::from(&home).join(".config/radiotray-lite/bookmarks.xml");
    if rt_lite_path.exists() {
        return rt_lite_path;
    }

    // 3. Ancien emplacement radiotray classique
    let rt_path = PathBuf::from(&home).join(".config/radiotray/bookmarks.xml");
    if rt_path.exists() {
        return rt_path;
    }

    // 4. Dossier de sauvegarde des documents de l'utilisateur
    let docs_path = PathBuf::from("/mnt/Donnees/Docs_systeme/bookmarks.xml");
    if docs_path.exists() {
        return docs_path;
    }

    timonde_path
}

/// Génère un jeu de signets minimal par défaut si aucun fichier n'existe
fn create_default_bookmarks(path: &Path) -> Group {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }

    let default_xml = r#"<bookmarks>
	<group name="Sélection nationale">
		<bookmark name="France Inter" url="https://icecast.radiofrance.fr/franceinter-hifi.aac"/>
		<bookmark name="France Info" url="https://icecast.radiofrance.fr/franceinfo-hifi.aac"/>
		<bookmark name="France Culture" url="https://icecast.radiofrance.fr/franceculture-hifi.aac"/>
		<bookmark name="FIP" url="https://icecast.radiofrance.fr/fip-hifi.aac"/>
		<bookmark name="RTL" url="https://streaming.Radio.rtl.fr/rtl-1-44-128"/>
	</group>
</bookmarks>"#;

    let _ = std::fs::write(path, default_xml);
    bookmarks::parse_bookmarks_reader(default_xml.as_bytes()).unwrap_or_else(|_| Group::new("root"))
}

fn main() {
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());

    // 1. Gestion des arguments en ligne de commande (mode contrôle CLI et importation)
    let args: Vec<String> = std::env::args().collect();
    if args.len() > 1 {
        match args[1].as_str() {
            "--help" | "-h" => {
                println!("TiMonde - Lecteur de flux radio ultra-léger pour la barre des tâches");
                println!("\nUsage : timonde [OPTION]");
                println!("\nOptions de contrôle (agissent sur l'instance en cours d'exécution) :");
                println!("  -p, --play-pause   Bascule Lecture / Pause");
                println!("  -n, --next         Station suivante");
                println!("      --prev         Station précédente");
                println!("  -s, --stop         Arrêter la lecture");
                println!("      --status       Afficher l'état et le morceau en cours");
                println!("  -q, --quit         Quitter TiMonde");
                println!("\nOptions d'importation :");
                println!("  -i, --import <FICHIER> [--group <GROUPE>]");
                println!("                     Importer des radios (.json radiotray-ng, .m3u, .csv, .xml)");
                println!("                     Si --group n'est pas spécifié, les radios vont à la racine.");
                println!("                     Gestion automatique des doublons (URL et nom).");
                println!("\nOptions générales :");
                println!("  -h, --help         Afficher cette aide");
                println!("  -v, --version      Afficher la version");
                return;
            }
            "--version" | "-v" => {
                println!("TiMonde 0.1.0");
                return;
            }
            "-i" | "--import" => {
                if args.len() < 3 {
                    eprintln!("Usage : timonde --import <chemin_fichier> [--group <nom_du_groupe>]");
                    std::process::exit(1);
                }
                let file_path = PathBuf::from(&args[2]);
                let mut target_group = None;
                if args.len() >= 5 && (args[3] == "--group" || args[3] == "-g") {
                    target_group = Some(args[4].as_str());
                }

                let bookmarks_path = find_bookmarks_path();
                let mut root = if bookmarks_path.exists() {
                    bookmarks::load_bookmarks(&bookmarks_path).unwrap_or_else(|_| Group::new("root"))
                } else {
                    create_default_bookmarks(&bookmarks_path)
                };

                println!("📦 Importation depuis : {:?}", file_path);
                if let Some(tg) = target_group {
                    println!("📁 Groupe cible       : {}", tg);
                } else {
                    println!("📁 Groupe cible       : (Racine par défaut)");
                }

                match import::import_file(&mut root, &file_path, target_group) {
                    Ok(report) => {
                        if let Err(e) = bookmarks::save_bookmarks(&root, &bookmarks_path) {
                            eprintln!("Erreur lors de la sauvegarde : {}", e);
                            std::process::exit(1);
                        }
                        println!("✅ Importation terminée avec succès dans {:?} :", bookmarks_path);
                        println!("   - {} nouvelle(s) station(s) ajoutée(s)", report.stations_added);
                        println!("   - {} doublon(s) ignoré(s)", report.duplicates_skipped);
                        println!("   - {} groupe(s) créé(s)", report.groups_created);
                    }
                    Err(e) => {
                        eprintln!("Erreur lors de l'importation : {}", e);
                        std::process::exit(1);
                    }
                }
                return;
            }
            "-p" | "--play-pause" => {
                if let Err(e) = mpris::send_command("PlayPause") {
                    eprintln!("Erreur : {}", e);
                    std::process::exit(1);
                }
                return;
            }
            "-n" | "--next" => {
                if let Err(e) = mpris::send_command("Next") {
                    eprintln!("Erreur : {}", e);
                    std::process::exit(1);
                }
                return;
            }
            "--prev" => {
                if let Err(e) = mpris::send_command("Previous") {
                    eprintln!("Erreur : {}", e);
                    std::process::exit(1);
                }
                return;
            }
            "-s" | "--stop" => {
                if let Err(e) = mpris::send_command("Stop") {
                    eprintln!("Erreur : {}", e);
                    std::process::exit(1);
                }
                return;
            }
            "-q" | "--quit" => {
                let _ = mpris::send_command("Quit");
                println!("Fermeture de TiMonde.");
                return;
            }
            "--status" => {
                match mpris::get_status_info() {
                    Ok(info) => print!("{}", info),
                    Err(e) => {
                        eprintln!("{}", e);
                        std::process::exit(1);
                    }
                }
                return;
            }
            other => {
                eprintln!("Option inconnue : {}", other);
                eprintln!("Consultez 'timonde --help' pour afficher les options disponibles.");
                std::process::exit(1);
            }
        }
    }

    // 2. Protection instance unique (évite les doublons d'icônes dans la barre des tâches)
    if mpris::is_instance_running() {
        println!("ℹ️ TiMonde est déjà actif dans la barre des tâches.");
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
    info!("📻 Démarrage de TiMonde (Mode barre des tâches direct)");
    info!("========================================================");

    // 3. Chargement des favoris (avec migration transparente si seul radiotray-ng est présent)
    let bookmarks_path = find_bookmarks_path();
    let root_group = if bookmarks_path.exists() {
        info!("Chargement des signets depuis : {:?}", bookmarks_path);
        match load_bookmarks(&bookmarks_path) {
            Ok(group) => {
                info!("✅ {} stations chargées avec succès !", group.total_stations());
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
                info!("✅ {} stations migrées depuis radiotray-ng !", report.stations_added);
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

    // Clones des Arcs partagés avec le serveur MPRIS2
    let audio = Arc::clone(&tray.audio);
    let current_volume = Arc::clone(&tray.current_volume);
    let current_station = Arc::clone(&tray.current_station);
    let last_station = Arc::clone(&tray.last_station);
    let current_title = Arc::clone(&tray.current_title);
    let root_group_clone = Arc::clone(&tray.root_group);
    let bookmarks_path_clone = tray.bookmarks_path.clone();
    let play_generation = Arc::clone(&tray.play_generation);

    let tray_handle_cell: Arc<Mutex<Option<ksni::blocking::Handle<tray::TiMondeTray>>>> =
        Arc::new(Mutex::new(None));

    // Fonction de rafraîchissement asynchrone non-bloquante du tray
    let trigger_tray_update = {
        let handle_cell = Arc::clone(&tray_handle_cell);
        Arc::new(move || {
            let handle_cell = Arc::clone(&handle_cell);
            std::thread::spawn(move || {
                if let Some(ref h) = *handle_cell.lock().unwrap() {
                    h.update(|_| {});
                }
            });
        })
    };

    let trigger_for_play = Arc::clone(&trigger_tray_update);
    let trigger_for_stop = Arc::clone(&trigger_tray_update);
    let trigger_for_mpris = Arc::clone(&trigger_tray_update);

    let on_play = {
        let audio = Arc::clone(&audio);
        let current_volume = Arc::clone(&current_volume);
        let current_station = Arc::clone(&current_station);
        let last_station = Arc::clone(&last_station);
        let current_title = Arc::clone(&current_title);
        let root_group = Arc::clone(&root_group_clone);
        let play_generation = Arc::clone(&play_generation);
        let bpath = bookmarks_path_clone.clone();

        Arc::new(move |station: models::Station| {
            tray::TiMondeTray::play_station_flow(
                station,
                &audio,
                &current_volume,
                &current_station,
                &last_station,
                &current_title,
                &play_generation,
                &root_group,
                &bpath,
            );
            trigger_for_play();
        })
    };

    let on_stop = {
        let audio = Arc::clone(&audio);
        let current_station = Arc::clone(&current_station);
        let current_title = Arc::clone(&current_title);

        Arc::new(move || {
            tray::TiMondeTray::stop_and_trim_flow(&audio, &current_station, &current_title);
            trigger_for_stop();
        })
    };

    let on_update = Arc::new(move || {
        trigger_for_mpris();
    });

    // 5. Enregistrement du service D-Bus MPRIS2 (org.mpris.MediaPlayer2.timonde)
    mpris::spawn_mpris_server(
        audio,
        current_volume,
        current_station,
        current_title,
        last_station,
        root_group_clone,
        on_play,
        on_stop,
        on_update,
    );

    // 6. Enregistrement de l'icône dans la zone de notification (SNI)
    let handle = match tray.spawn() {
        Ok(h) => {
            info!("✅ Icône StatusNotifierItem enregistrée sur le bureau hôte !");
            h
        }
        Err(e) => {
            error!("Erreur enregistrement Tray : {:?}", e);
            std::process::exit(1);
        }
    };
    *tray_handle_cell.lock().unwrap() = Some(handle);

    info!("✨ TiMonde est actif et discret dans la barre des tâches.");

    // 7. Boucle d'événements GLib (maintient le processus actif et léger)
    let main_loop = gstreamer::glib::MainLoop::new(None, false);
    main_loop.run();
}
