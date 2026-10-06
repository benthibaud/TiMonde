pub mod audio;
pub mod bookmarks;
pub mod models;
pub mod tray;

use audio::AudioEngine;
use bookmarks::load_bookmarks;
use ksni::blocking::TrayMethods;
use log::{error, info};
use models::Group;
use std::path::{Path, PathBuf};
use std::sync::Arc;

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

    // Fallback : on retourne le chemin standard de TiMonde
    timonde_path
}

/// Génère un jeu de signets minimal par défaut si aucun fichier n'existe
fn create_default_bookmarks(path: &Path) -> Group {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }

    let default_xml = r#"<bookmarks>
	<group name="root">
		<group name="Sélection nationale">
			<bookmark name="France Inter" url="https://icecast.radiofrance.fr/franceinter-hifi.aac"/>
			<bookmark name="France Info" url="https://icecast.radiofrance.fr/franceinfo-hifi.aac"/>
			<bookmark name="France Culture" url="https://icecast.radiofrance.fr/franceculture-hifi.aac"/>
			<bookmark name="FIP" url="https://icecast.radiofrance.fr/fip-hifi.aac"/>
			<bookmark name="RTL" url="https://streaming.Radio.rtl.fr/rtl-1-44-128"/>
		</group>
		<group name="Musique & Jazz">
			<bookmark name="FIP Jazz" url="https://icecast.radiofrance.fr/fipjazz-hifi.aac"/>
			<bookmark name="TSF Jazz" url="https://tsfjazz.ice.infomaniak.ch/tsfjazz-high.mp3"/>
			<bookmark name="Radio Nova" url="https://radionova.ice.infomaniak.ch/radionova-256.aac"/>
		</group>
	</group>
</bookmarks>"#;

    let _ = std::fs::write(path, default_xml);
    bookmarks::parse_bookmarks_reader(default_xml.as_bytes()).unwrap_or_else(|_| Group::new("root"))
}

fn main() {
    // Initialisation des logs
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    info!("========================================================");
    info!("📻 Démarrage de TiMonde (Mode barre des tâches direct)");
    info!("========================================================");

    // 1. Chargement des favoris
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
        info!("Aucun fichier existant trouvé -> création de {:?}", bookmarks_path);
        create_default_bookmarks(&bookmarks_path)
    };

    // 2. Initialisation du moteur audio (GStreamer)
    let audio = match AudioEngine::new() {
        Ok(engine) => Arc::new(engine),
        Err(e) => {
            error!("Impossible d'initialiser GStreamer : {}", e);
            std::process::exit(1);
        }
    };

    // 3. Initialisation du plateau système (StatusNotifierItem)
    let tray = tray::TiMondeTray::new(Arc::clone(&audio), root_group);

    // Lancement du tray D-Bus en tâche de fond (zéro fenêtre graphique ouverte)
    let _handle = match tray.spawn() {
        Ok(h) => {
            info!("✅ Icône StatusNotifierItem enregistrée sur le bureau hôte !");
            h
        }
        Err(e) => {
            error!("Erreur enregistrement Tray : {:?}", e);
            std::process::exit(1);
        }
    };

    info!("✨ TiMonde est actif et discret dans la barre des tâches.");

    // 4. Boucle d'événements GLib pour le bus GStreamer (maintient le processus en vie)
    let main_loop = gstreamer::glib::MainLoop::new(None, false);
    main_loop.run();
}
