use crate::bookmarks::{self, create_default_bookmarks, find_bookmarks_path};
use crate::import;
use crate::models::{self, Group};
use crate::mpris;
use crate::radio_browser;
use crate::timezone;
use crate::probe;
use std::path::PathBuf;

/// Traite les arguments passés en ligne de commande.
/// Retourne `true` si une commande CLI a été exécutée et terminée, ou `false` s'il faut démarrer l'application tray.
pub fn handle_cli(args: &[String]) -> bool {
    if args.len() <= 1 {
        return false;
    }

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
                println!("      --reload       Recharger les favoris depuis bookmarks.xml");
                println!("      --preview-play <URL> [NOM]  Pré-écouter un flux via le moteur Rust");
                println!("      --preview-stop              Arrêter la pré-écoute");
                println!("      --save-bookmarks-json <FICHIER|->  Enregistrer atomiquement les favoris depuis un JSON");
                println!("  -q, --quit         Quitter TiMonde");
                println!("\nOptions de gestion des stations et groupes :");
                println!("      --search <TERME> [--tag <GENRE>] [--country <PAYS>] [--lang <LANG>] [--limit <N>]");
                println!("                         Rechercher des radios sur l'annuaire mondial Radio-Browser");
                println!("      --add <NOM> <URL> [--group <GROUPE>] [--country <PAYS>] [--timezone <FUSEAU>]");
                println!("                         Ajouter une radio manuellement (avec pays et fuseau horaire optionnels)");
                println!("      --sort-groups      Trier tous les groupes de radios de A à Z");
                println!("      --move-group <NOM> <--up|--down|--top>");
                println!("                         Déplacer un groupe vers le haut, le bas ou en premier");
                println!("  -e, --export-csv [FICHIER]");
                println!("                     Exporter toutes vos radios au format CSV (tableur)");
                println!("  -i, --import <FICHIER> [--group <GROUPE>]");
                println!("                     Importer des radios (.json radiotray-ng, .m3u, .csv, .xml)");
                println!("                     Si --group n'est pas spécifié, les radios vont à la racine.");
                println!("                     Gestion automatique des doublons (URL et nom).");
                println!("\nOptions générales :");
                println!("  -h, --help         Afficher cette aide");
                println!("  -v, --version      Afficher la version");
                true
            }
            "--version" | "-v" => {
                println!("TiMonde {}", env!("CARGO_PKG_VERSION"));
                true
            }
            "--search" => {
                let mut filter = radio_browser::SearchFilter::default();
                let mut as_json = false;
                let mut i = 2;
                while i < args.len() {
                    match args[i].as_str() {
                        "--json" => {
                            as_json = true;
                        }
                        "--tag" | "-t" => {
                            if i + 1 < args.len() { filter.tag = Some(args[i + 1].clone()); i += 1; }
                        }
                        "--country" | "-c" => {
                            if i + 1 < args.len() { filter.country = Some(args[i + 1].clone()); i += 1; }
                        }
                        "--lang" | "-l" => {
                            if i + 1 < args.len() { filter.language = Some(args[i + 1].clone()); i += 1; }
                        }
                        "--limit" => {
                            if i + 1 < args.len() {
                                filter.limit = args[i + 1].parse().unwrap_or(20);
                                i += 1;
                            }
                        }
                        other if !other.starts_with('-') && filter.name.is_none() => {
                            filter.name = Some(other.to_string());
                        }
                        _ => {}
                    }
                    i += 1;
                }

                if filter.name.is_none() && filter.tag.is_none() && filter.country.is_none() && filter.language.is_none() {
                    if as_json {
                        println!("[]");
                        return true;
                    }
                    eprintln!("Usage : timonde --search [NOM] [--tag GENRE] [--country PAYS] [--lang LANGUE] [--limit N] [--json]");
                    std::process::exit(1);
                }

                if !as_json {
                    println!("Recherche multicritères sur Radio-Browser...");
                }
                let results = radio_browser::search_advanced(&filter);
                if as_json {
                    let json_str = serde_json::to_string_pretty(&results).unwrap_or_else(|_| "[]".to_string());
                    println!("{}", json_str);
                    return true;
                }
                if results.is_empty() {
                    println!("Aucune station trouvée pour ces critères");
                } else {
                    println!("{} station(s) trouvée(s) :", results.len());
                    println!("--------------------------------------------------------------------------------");
                    for (idx, r) in results.iter().enumerate() {
                        let codec = if r.codec.is_empty() { "-" } else { &r.codec };
                        let rate = if r.bitrate > 0 { format!("{}k", r.bitrate) } else { "-".to_string() };
                        let country = if r.country.is_empty() { "-" } else { &r.country };
                        let tags = if r.tags.is_empty() { "-" } else { &r.tags };
                        println!("{:2}. {:<30} | {:<12} | {:<16} | {:>4} {:>4} | {} votes",
                            idx + 1, r.name, country, tags, codec, rate, r.votes);
                        println!("    URL: {}", r.url_resolved);
                    }
                    println!("--------------------------------------------------------------------------------");
                    println!("Pour ajouter une station : timonde --add \"<NOM>\" \"<URL>\" [--group \"<GROUPE>\"]");
                }
                true
            }
            "--sort-groups" => {
                let bookmarks_path = find_bookmarks_path();
                let mut root = if bookmarks_path.exists() {
                    bookmarks::load_bookmarks(&bookmarks_path).unwrap_or_else(|_| Group::new("root"))
                } else {
                    create_default_bookmarks(&bookmarks_path)
                };
                root.sort_subgroups_alphabetically();
                if let Err(e) = bookmarks::save_bookmarks(&root, &bookmarks_path) {
                    eprintln!("Erreur lors de la sauvegarde : {}", e);
                    std::process::exit(1);
                }
                println!("Tous les groupes ont été triés par ordre alphabétique (A-Z) dans {:?}", bookmarks_path);
                true
            }
            "--move-group" => {
                if args.len() < 4 {
                    eprintln!("Usage : timonde --move-group <NOM_DU_GROUPE> <--up|--down|--top>");
                    std::process::exit(1);
                }
                let group_name = &args[2];
                let direction = &args[3];

                let bookmarks_path = find_bookmarks_path();
                let mut root = if bookmarks_path.exists() {
                    bookmarks::load_bookmarks(&bookmarks_path).unwrap_or_else(|_| Group::new("root"))
                } else {
                    create_default_bookmarks(&bookmarks_path)
                };

                let changed = match direction.as_str() {
                    "--up" => root.move_subgroup_up(group_name),
                    "--down" => root.move_subgroup_down(group_name),
                    "--top" => root.move_subgroup_to_top(group_name),
                    _ => {
                        eprintln!("Option de déplacement inconnue : {}", direction);
                        std::process::exit(1);
                    }
                };

                if changed {
                    if let Err(e) = bookmarks::save_bookmarks(&root, &bookmarks_path) {
                        eprintln!("Erreur lors de la sauvegarde : {}", e);
                        std::process::exit(1);
                    }
                    println!("Groupe '{}' déplacé avec succès !", group_name);
                } else {
                    println!("Le groupe '{}' n'a pas pu être déplacé (déjà en bordure ou introuvable).", group_name);
                }
                true
            }
            "--add" => {
                if args.len() < 4 {
                    eprintln!("Usage : timonde --add <NOM> <URL> [--group <GROUPE>] [--country <PAYS>] [--timezone <FUSEAU>]");
                    std::process::exit(1);
                }
                let name = &args[2];
                let url = &args[3];
                let mut target_group = None;
                let mut country_code = None;
                let mut timezone_iana = None;

                let mut i = 4;
                while i < args.len() {
                    match args[i].as_str() {
                        "--group" | "-g" => {
                            if i + 1 < args.len() {
                                target_group = Some(args[i + 1].as_str());
                                i += 2;
                            } else { i += 1; }
                        }
                        "--country" | "-c" if i + 1 < args.len() => {
                            country_code = Some(args[i + 1].as_str());
                            i += 2;
                        }
                        "--timezone" | "--tz" | "-t" if i + 1 < args.len() => {
                            timezone_iana = Some(args[i + 1].as_str());
                            i += 2;
                        }
                        _ => { i += 1; }
                    }
                }

                let bookmarks_path = find_bookmarks_path();
                let mut root = if bookmarks_path.exists() {
                    bookmarks::load_bookmarks(&bookmarks_path).unwrap_or_else(|_| Group::new("root"))
                } else {
                    create_default_bookmarks(&bookmarks_path)
                };

                let mut st = models::Station::new(name, url);
                if let Some(c) = country_code {
                    st.country = Some(c.trim().to_ascii_uppercase());
                }
                if let Some(tz) = timezone_iana {
                    st.timezone = Some(tz.trim().to_string());
                }

                match import::add_station_to_group(&mut root, st, target_group) {
                    Ok(msg) => {
                        if let Err(e) = bookmarks::save_bookmarks(&root, &bookmarks_path) {
                            eprintln!("Erreur lors de la sauvegarde : {}", e);
                            std::process::exit(1);
                        }
                        println!("{}", msg);
                    }
                    Err(e) => {
                        eprintln!("Erreur : {}", e);
                        std::process::exit(1);
                    }
                }
                true
            }
            "-e" | "--export-csv" => {
                let mut out_path = PathBuf::from("radios_timonde.csv");
                let mut json_source: Option<String> = None;

                let mut i = 2;
                while i < args.len() {
                    match args[i].as_str() {
                        "--from-json" if i + 1 < args.len() => {
                            json_source = Some(args[i + 1].clone());
                            i += 2;
                        }
                        other if !other.starts_with('-') && out_path.as_os_str() == "radios_timonde.csv" => {
                            out_path = PathBuf::from(other);
                            i += 1;
                        }
                        _ => { i += 1; }
                    }
                }

                let root = if let Some(src) = json_source {
                    let json_str = if src == "-" {
                        use std::io::Read;
                        let mut buffer = String::new();
                        if let Err(e) = std::io::stdin().read_to_string(&mut buffer) {
                            eprintln!("Erreur lecture stdin : {}", e);
                            std::process::exit(1);
                        }
                        buffer
                    } else {
                        match std::fs::read_to_string(&src) {
                            Ok(c) => c,
                            Err(e) => {
                                eprintln!("Erreur lecture JSON {:?} : {}", src, e);
                                std::process::exit(1);
                            }
                        }
                    };
                    match bookmarks::rebuild_root_from_json(&json_str) {
                        Ok(r) => r,
                        Err(e) => {
                            eprintln!("Erreur reconstruction de l'arbre depuis le JSON : {}", e);
                            std::process::exit(1);
                        }
                    }
                } else {
                    let bookmarks_path = find_bookmarks_path();
                    if bookmarks_path.exists() {
                        match bookmarks::load_bookmarks(&bookmarks_path) {
                            Ok(r) => r,
                            Err(e) => {
                                eprintln!("Erreur lecture bookmarks ({:?}) : {}", bookmarks_path, e);
                                std::process::exit(1);
                            }
                        }
                    } else {
                        eprintln!("Aucun fichier de favoris trouvé à l'emplacement {:?}", bookmarks_path);
                        std::process::exit(1);
                    }
                };

                match import::export_to_csv(&root, &out_path) {
                    Ok(count) => {
                        println!("{} station(s) exportée(s) avec succès dans {:?}", count, out_path);
                    }
                    Err(e) => {
                        eprintln!("Erreur lors de l'exportation CSV : {}", e);
                        std::process::exit(1);
                    }
                }
                true
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

                println!("Importation depuis : {:?}", file_path);
                if let Some(tg) = target_group {
                    println!("Groupe cible       : {}", tg);
                } else {
                    println!("Groupe cible       : (Racine par défaut)");
                }

                match import::import_file(&mut root, &file_path, target_group) {
                    Ok(report) => {
                        if let Err(e) = bookmarks::save_bookmarks(&root, &bookmarks_path) {
                            eprintln!("Erreur lors de la sauvegarde : {}", e);
                            std::process::exit(1);
                        }
                        println!("Importation terminée avec succès dans {:?} :", bookmarks_path);
                        println!("   - {} nouvelle(s) station(s) ajoutée(s)", report.stations_added);
                        println!("   - {} doublon(s) ignoré(s)", report.duplicates_skipped);
                        println!("   - {} groupe(s) créé(s)", report.groups_created);
                    }
                    Err(e) => {
                        eprintln!("Erreur lors de l'importation : {}", e);
                        std::process::exit(1);
                    }
                }
                true
            }
            "-p" | "--play-pause" => {
                if let Err(e) = mpris::send_command("PlayPause") {
                    eprintln!("Erreur : {}", e);
                    std::process::exit(1);
                }
                true
            }
            "-n" | "--next" => {
                if let Err(e) = mpris::send_command("Next") {
                    eprintln!("Erreur : {}", e);
                    std::process::exit(1);
                }
                true
            }
            "--prev" => {
                if let Err(e) = mpris::send_command("Previous") {
                    eprintln!("Erreur : {}", e);
                    std::process::exit(1);
                }
                true
            }
            "-s" | "--stop" => {
                if let Err(e) = mpris::send_command("Stop") {
                    eprintln!("Erreur : {}", e);
                    std::process::exit(1);
                }
                true
            }
            "-q" | "--quit" => {
                let _ = mpris::send_command("Quit");
                println!("Fermeture de TiMonde.");
                true
            }
            "--status" => {
                match mpris::get_status_info() {
                    Ok(info) => print!("{}", info),
                    Err(e) => {
                        eprintln!("{}", e);
                        std::process::exit(1);
                    }
                }
                true
            }
            "--reload" => {
                if let Err(e) = mpris::send_reload_bookmarks() {
                    eprintln!("Erreur rechargement : {}", e);
                    std::process::exit(1);
                }
                println!("Signal de rechargement des favoris envoyé.");
                true
            }
            "--preview-play" => {
                if args.len() < 3 {
                    eprintln!("Usage : timonde --preview-play <URL> [NOM]");
                    std::process::exit(1);
                }
                let url = &args[2];
                let name = if args.len() >= 4 { &args[3] } else { url };
                if let Err(e) = mpris::send_play_preview(url, name) {
                    eprintln!("Erreur lancement pré-écoute : {}", e);
                    std::process::exit(1);
                }
                true
            }
            "--preview-stop" => {
                let _ = mpris::send_command("StopPreview");
                let _ = mpris::send_command("Stop");
                true
            }
            "--save-bookmarks-json" => {
                if args.len() < 3 {
                    eprintln!("Usage : timonde --save-bookmarks-json <FICHIER_JSON|-> [DEST_XML]");
                    std::process::exit(1);
                }
                let json_content = if args[2] == "-" {
                    use std::io::Read;
                    let mut buffer = String::new();
                    if let Err(e) = std::io::stdin().read_to_string(&mut buffer) {
                        eprintln!(r#"{{"status":"error","message":"Erreur lecture stdin : {}"}}"#, e);
                        std::process::exit(1);
                    }
                    buffer
                } else {
                    match std::fs::read_to_string(&args[2]) {
                        Ok(c) => c,
                        Err(e) => {
                            eprintln!(r#"{{"status":"error","message":"Erreur lecture fichier : {}"}}"#, e);
                            std::process::exit(1);
                        }
                    }
                };

                let bookmarks_path = if args.len() >= 4 && !args[3].is_empty() {
                    PathBuf::from(&args[3])
                } else {
                    find_bookmarks_path()
                };

                match bookmarks::save_bookmarks_from_json(&json_content, &bookmarks_path) {
                    Ok(total) => {
                        let _ = mpris::send_reload_bookmarks();
                        println!(r#"{{"status":"ok","stations":{}}}"#, total);
                    }
                    Err(e) => {
                        eprintln!(r#"{{"status":"error","message":"{}"}}"#, e);
                        std::process::exit(1);
                    }
                }
                true
            }
            "--dump-bookmarks-json" => {
                let target_path = if args.len() >= 3 && !args[2].starts_with('-') {
                    PathBuf::from(&args[2])
                } else {
                    find_bookmarks_path()
                };

                if !target_path.exists() {
                    println!("[]");
                    return true;
                }

                match bookmarks::load_bookmarks_as_json(&target_path) {
                    Ok(json) => {
                        println!("{}", json);
                        true
                    }
                    Err(e) => {
                        eprintln!(r#"{{"status":"error","message":"{}"}}"#, e);
                        std::process::exit(1);
                    }
                }
            }
            "--parse-file-json" => {
                if args.len() < 3 {
                    eprintln!("Usage : timonde --parse-file-json <FICHIER>");
                    std::process::exit(1);
                }
                let file_path = PathBuf::from(&args[2]);
                match import::parse_file_to_json(&file_path) {
                    Ok(json_str) => {
                        println!("{}", json_str);
                        true
                    }
                    Err(e) => {
                        eprintln!(r#"{{"error":"{}"}}"#, e);
                        std::process::exit(1);
                    }
                }
            }
            "--dump-countries-json" => {
                println!("{}", timezone::dump_countries_json());
                true
            }
            "--infer-timezone" => {
                let mut country: Option<String> = None;
                let mut name: String = String::new();
                let mut group: Option<String> = None;
                let mut explicit_tz: Option<String> = None;

                let mut pos = 0;
                let mut i = 2;
                while i < args.len() {
                    if args[i] == "--tz" && i + 1 < args.len() {
                        explicit_tz = Some(args[i + 1].clone());
                        i += 2;
                        continue;
                    }
                    match pos {
                        0 => country = Some(args[i].clone()),
                        1 => name = args[i].clone(),
                        2 => group = Some(args[i].clone()),
                        _ => {}
                    }
                    pos += 1;
                    i += 1;
                }

                println!(
                    "{}",
                    timezone::infer_timezone_json(
                        country.as_deref(),
                        &name,
                        group.as_deref(),
                        explicit_tz.as_deref(),
                    )
                );
                true
            }
            "--probe-stream" => {
                if args.len() < 3 {
                    eprintln!("Usage : timonde --probe-stream <URL> [--timeout <SECS>] [--json]");
                    std::process::exit(1);
                }
                let mut url = String::new();
                let mut timeout_secs = 3;
                let mut as_json = false;

                let mut i = 2;
                while i < args.len() {
                    match args[i].as_str() {
                        "--json" => {
                            as_json = true;
                            i += 1;
                        }
                        "--timeout" if i + 1 < args.len() => {
                            timeout_secs = args[i + 1].parse().unwrap_or(3);
                            i += 2;
                        }
                        other if !other.starts_with("--") && url.is_empty() => {
                            url = other.to_string();
                            i += 1;
                        }
                        _ => {
                            i += 1;
                        }
                    }
                }

                if as_json {
                    println!("{}", probe::probe_stream_json(&url, timeout_secs));
                } else {
                    let res = probe::probe_stream_url(&url, timeout_secs);
                    if res.ok {
                        println!("Statut : OK ({})", res.message);
                        if let Some(r) = res.redirected_url {
                            println!("Redirection : {}", r);
                        }
                        if !res.meta.icy_name.is_empty() {
                            println!("Nom ICY : {}", res.meta.icy_name);
                        }
                    } else if res.is_geo {
                        println!("Statut : GÉOBLOQUÉ ({})", res.message);
                    } else {
                        println!("Statut : ERREUR ({})", res.message);
                    }
                }
                true
            }
            other => {
                eprintln!("Option inconnue : {}", other);
                eprintln!("Consultez 'timonde --help' pour afficher les options disponibles.");
                std::process::exit(1);
            }
        }
}
