use crate::sync_util::SafeLock;
use std::sync::{Arc, Mutex};
use std::collections::HashMap;
use zbus::interface;
use zbus::zvariant::{ObjectPath, Value, OwnedValue};
use crate::audio::PlaybackState;
use crate::models::{Group, Station};

pub struct MprisRoot;

#[interface(name = "org.mpris.MediaPlayer2")]
impl MprisRoot {
    fn raise(&self) {}
    fn quit(&self) {
        std::process::exit(0);
    }

    #[zbus(property)]
    fn can_quit(&self) -> bool { true }
    #[zbus(property)]
    fn can_raise(&self) -> bool { false }
    #[zbus(property)]
    fn has_track_list(&self) -> bool { false }
    #[zbus(property)]
    fn identity(&self) -> String { "TiMonde".to_string() }
    #[zbus(property)]
    fn supported_uri_schemes(&self) -> Vec<String> { vec!["http".into(), "https".into()] }
    #[zbus(property)]
    fn supported_mime_types(&self) -> Vec<String> {
        vec!["audio/mpeg".into(), "audio/aac".into(), "audio/ogg".into(), "audio/flac".into()]
    }
}

pub struct MprisPlayer {
    pub session: Arc<Mutex<crate::session::PlaybackSession>>,
    pub last_station: Arc<Mutex<Option<Station>>>,
    pub root_group: Arc<Mutex<Group>>,
    pub on_play: Arc<dyn Fn(Station) + Send + Sync>,
    pub on_preview_play: Arc<dyn Fn(Station) + Send + Sync>,
    pub on_stop: Arc<dyn Fn() + Send + Sync>,
    pub on_update: Arc<dyn Fn() + Send + Sync>,
    pub on_reload: Arc<dyn Fn() + Send + Sync>,
}

#[interface(name = "org.mpris.MediaPlayer2.Player")]
impl MprisPlayer {
    fn next(&self) {
        let all_stations = get_all_stations(&self.root_group.safe_lock());
        if all_stations.is_empty() { return; }

        let cur = self.session.safe_lock().current_station.clone();
        let next_station = if let Some(st) = cur {
            if let Some(pos) = all_stations.iter().position(|s| s.name == st.name) {
                all_stations[(pos + 1) % all_stations.len()].clone()
            } else {
                all_stations[0].clone()
            }
        } else {
            all_stations[0].clone()
        };

        (self.on_play)(next_station);
    }

    fn previous(&self) {
        let all_stations = get_all_stations(&self.root_group.safe_lock());
        if all_stations.is_empty() { return; }

        let cur = self.session.safe_lock().current_station.clone();
        let prev_station = if let Some(st) = cur {
            if let Some(pos) = all_stations.iter().position(|s| s.name == st.name) {
                let prev_idx = if pos == 0 { all_stations.len() - 1 } else { pos - 1 };
                all_stations[prev_idx].clone()
            } else {
                all_stations[0].clone()
            }
        } else {
            all_stations[0].clone()
        };

        (self.on_play)(prev_station);
    }

    fn pause(&self) {
        let engine = {
            let s = self.session.safe_lock();
            s.engine.clone()
        };
        if let Some(ref e) = engine {
            let _ = e.pause();
        }
        (self.on_update)();
    }

    fn play_pause(&self) {
        let (action, current_st) = {
            let s = self.session.safe_lock();
            match s.state() {
                PlaybackState::Playing => (Some(false), None),
                PlaybackState::Paused => (Some(true), None),
                _ => (None, s.current_station.clone()),
            }
        };

        if let Some(resume) = action {
            let engine = {
                let s = self.session.safe_lock();
                s.engine.clone()
            };
            if let Some(ref e) = engine {
                if resume {
                    let _ = e.resume();
                } else {
                    let _ = e.pause();
                }
            }
            (self.on_update)();
            return;
        }

        if let Some(st) = self.last_station.safe_lock().clone().or(current_st) {
            (self.on_play)(st);
        }
    }

    fn stop(&self) {
        (self.on_stop)();
    }

    fn play(&self) {
        let (is_paused, current_st) = {
            let s = self.session.safe_lock();
            (s.state() == PlaybackState::Paused, s.current_station.clone())
        };

        if is_paused {
            let engine = {
                let s = self.session.safe_lock();
                s.engine.clone()
            };
            if let Some(ref e) = engine {
                let _ = e.resume();
            }
            (self.on_update)();
            return;
        }

        if let Some(st) = self.last_station.safe_lock().clone().or(current_st) {
            (self.on_play)(st);
        }
    }

    fn seek(&self, _offset: i64) {}
    fn set_position(&self, _track_id: ObjectPath<'_>, _position: i64) {}
    fn open_uri(&self, uri: String) {
        (self.on_play)(Station::new(uri.clone(), uri));
    }

    /// Lance une pré-écoute temporaire d'un flux audio
    fn play_preview(&self, uri: String, name: String) {
        let display_name = if name.trim().is_empty() { uri.clone() } else { name };
        (self.on_preview_play)(Station::new(display_name, uri));
    }

    /// Arrête la pré-écoute uniquement si la session active est éphémère
    fn stop_preview(&self) {
        let is_ephemeral = {
            let s = self.session.safe_lock();
            s.is_ephemeral
        };
        if is_ephemeral {
            (self.on_stop)();
        } else {
            log::info!("StopPreview ignoré : la session active n'est pas une pré-écoute.");
        }
    }

    /// Déclenche le rechargement immédiat de l'arbre des favoris depuis bookmarks.xml
    fn reload_bookmarks(&self) {
        (self.on_reload)();
    }

    /// Retourne l'arborescence des favoris actuellement chargée au format JSON
    fn get_bookmarks_json(&self) -> String {
        let bookmarks_path = crate::find_bookmarks_path();
        crate::bookmarks::load_bookmarks_as_json(&bookmarks_path).unwrap_or_else(|_| "[]".to_string())
    }

    #[zbus(property)]
    fn playback_status(&self) -> String {
        match self.session.safe_lock().state() {
            PlaybackState::Playing => "Playing".to_string(),
            PlaybackState::Paused => "Paused".to_string(),
            _ => "Stopped".to_string(),
        }
    }

    #[zbus(property)]
    fn loop_status(&self) -> String { "None".to_string() }
    #[zbus(property)]
    fn rate(&self) -> f64 { 1.0 }
    #[zbus(property)]
    fn shuffle(&self) -> bool { false }

    #[zbus(property)]
    fn metadata(&self) -> HashMap<String, Value<'static>> {
        let mut map = HashMap::new();
        if let Ok(track_id) = ObjectPath::try_from("/org/mpris/MediaPlayer2/CurrentTrack") {
            map.insert("mpris:trackid".to_string(), Value::ObjectPath(track_id));
        }

        let (st_opt, title_opt) = {
            let s = self.session.safe_lock();
            (s.current_station.clone(), s.current_title.clone())
        };

        let track_title = if let Some(ref t) = title_opt {
            t.clone()
        } else if let Some(ref s) = st_opt {
            s.name.clone()
        } else {
            "TiMonde".to_string()
        };

        map.insert("xesam:title".to_string(), Value::Str(track_title.into()));

        if let Some(ref s) = st_opt {
            map.insert("xesam:artist".to_string(), Value::Str(s.name.clone().into()));
            map.insert("xesam:url".to_string(), Value::Str(s.url.clone().into()));
        }

        map
    }

    #[zbus(property)]
    fn volume(&self) -> f64 {
        self.session.safe_lock().volume
    }

    #[zbus(property)]
    fn set_volume(&self, vol: f64) {
        let clamped = vol.clamp(0.0, 1.0);
        {
            let mut s = self.session.safe_lock();
            s.set_volume(clamped);
        }
        crate::state::schedule_volume_save(clamped);
        (self.on_update)();
    }

    #[zbus(property)]
    fn position(&self) -> i64 { 0 }
    #[zbus(property)]
    fn minimum_rate(&self) -> f64 { 1.0 }
    #[zbus(property)]
    fn maximum_rate(&self) -> f64 { 1.0 }
    #[zbus(property)]
    fn can_go_next(&self) -> bool { true }
    #[zbus(property)]
    fn can_go_previous(&self) -> bool { true }
    #[zbus(property)]
    fn can_play(&self) -> bool { true }
    #[zbus(property)]
    fn can_pause(&self) -> bool { true }
    #[zbus(property)]
    fn can_seek(&self) -> bool { false }
    #[zbus(property)]
    fn can_control(&self) -> bool { true }
}

fn get_all_stations(group: &Group) -> Vec<Station> {
    let mut list = Vec::new();
    for s in &group.stations {
        if !s.is_separator() {
            list.push(s.clone());
        }
    }
    for sub in &group.subgroups {
        list.extend(get_all_stations(sub));
    }
    list
}

#[allow(clippy::too_many_arguments)]
pub fn spawn_mpris_server(
    session: Arc<Mutex<crate::session::PlaybackSession>>,
    last_station: Arc<Mutex<Option<Station>>>,
    root_group: Arc<Mutex<Group>>,
    on_play: Arc<dyn Fn(Station) + Send + Sync>,
    on_preview_play: Arc<dyn Fn(Station) + Send + Sync>,
    on_stop: Arc<dyn Fn() + Send + Sync>,
    on_update: Arc<dyn Fn() + Send + Sync>,
    on_reload: Arc<dyn Fn() + Send + Sync>,
) {
    std::thread::spawn(move || {
        let res = zbus::blocking::connection::Builder::session()
            .and_then(|b| b.name("org.mpris.MediaPlayer2.timonde"))
            .and_then(|b| b.serve_at("/org/mpris/MediaPlayer2", MprisRoot))
            .and_then(|b| {
                b.serve_at(
                    "/org/mpris/MediaPlayer2",
                    MprisPlayer {
                        session,
                        last_station,
                        root_group,
                        on_play,
                        on_preview_play,
                        on_stop,
                        on_update,
                        on_reload,
                    },
                )
            })
            .and_then(|b| b.build());

        match res {
            Ok(_conn) => {
                log::info!("Serveur D-Bus MPRIS2 enregistré : org.mpris.MediaPlayer2.timonde");
                loop {
                    std::thread::park();
                }
            }
            Err(e) => {
                log::warn!("Impossible d'enregistrer le serveur MPRIS2 : {}", e);
            }
        }
    });
}

/// Vérifie si une instance de TiMonde est déjà enregistrée sur D-Bus
pub fn is_instance_running() -> bool {
    if let Ok(conn) = zbus::blocking::Connection::session() {
        if let Ok(reply) = conn.call_method(
            Some("org.freedesktop.DBus"),
            "/org/freedesktop/DBus",
            Some("org.freedesktop.DBus"),
            "NameHasOwner",
            &("org.mpris.MediaPlayer2.timonde",),
        ) {
            if let Ok(has_owner) = reply.body().deserialize::<bool>() {
                return has_owner;
            }
        }
    }
    false
}

/// Envoie une commande de contrôle D-Bus à l'instance TiMonde active
pub fn send_command(method: &str) -> Result<(), String> {
    let conn = zbus::blocking::Connection::session().map_err(|e| e.to_string())?;
    let iface = if method == "Quit" || method == "Raise" {
        "org.mpris.MediaPlayer2"
    } else {
        "org.mpris.MediaPlayer2.Player"
    };
    conn.call_method(
        Some("org.mpris.MediaPlayer2.timonde"),
        "/org/mpris/MediaPlayer2",
        Some(iface),
        method,
        &(),
    ).map_err(|e| format!("Impossible de joindre TiMonde : {}", e))?;
    Ok(())
}

/// Envoie l'ordre de jouer une URI spécifique à l'instance TiMonde active
pub fn send_open_uri(uri: &str) -> Result<(), String> {
    let conn = zbus::blocking::Connection::session().map_err(|e| e.to_string())?;
    conn.call_method(
        Some("org.mpris.MediaPlayer2.timonde"),
        "/org/mpris/MediaPlayer2",
        Some("org.mpris.MediaPlayer2.Player"),
        "OpenUri",
        &(uri,),
    ).map_err(|e| format!("Impossible de joindre TiMonde : {}", e))?;
    Ok(())
}

/// Envoie l'ordre de pré-écouter un flux à l'instance TiMonde active
pub fn send_play_preview(uri: &str, name: &str) -> Result<(), String> {
    let conn = zbus::blocking::Connection::session().map_err(|e| e.to_string())?;
    conn.call_method(
        Some("org.mpris.MediaPlayer2.timonde"),
        "/org/mpris/MediaPlayer2",
        Some("org.mpris.MediaPlayer2.Player"),
        "PlayPreview",
        &(uri, name),
    ).map_err(|e| format!("Impossible de joindre TiMonde : {}", e))?;
    Ok(())
}

/// Envoie l'ordre de recharger les signets depuis bookmarks.xml
pub fn send_reload_bookmarks() -> Result<(), String> {
    let conn = zbus::blocking::Connection::session().map_err(|e| e.to_string())?;
    conn.call_method(
        Some("org.mpris.MediaPlayer2.timonde"),
        "/org/mpris/MediaPlayer2",
        Some("org.mpris.MediaPlayer2.Player"),
        "ReloadBookmarks",
        &(),
    ).map_err(|e| format!("Impossible de joindre TiMonde : {}", e))?;
    Ok(())
}

/// Récupère l'état et les métadonnées de l'instance TiMonde active
pub fn get_status_info() -> Result<String, String> {
    let conn = zbus::blocking::Connection::session().map_err(|e| e.to_string())?;

    let status_reply = conn.call_method(
        Some("org.mpris.MediaPlayer2.timonde"),
        "/org/mpris/MediaPlayer2",
        Some("org.freedesktop.DBus.Properties"),
        "Get",
        &("org.mpris.MediaPlayer2.Player", "PlaybackStatus"),
    ).map_err(|e| format!("TiMonde n'est pas actif ({})", e))?;

    let status_val: OwnedValue = status_reply.body().deserialize().map_err(|e| e.to_string())?;
    let status_str = match &*status_val {
        Value::Str(s) => s.as_str(),
        _ => "Inconnu",
    };

    let meta_reply = conn.call_method(
        Some("org.mpris.MediaPlayer2.timonde"),
        "/org/mpris/MediaPlayer2",
        Some("org.freedesktop.DBus.Properties"),
        "Get",
        &("org.mpris.MediaPlayer2.Player", "Metadata"),
    ).map_err(|e| format!("Métadonnées inaccessibles ({})", e))?;

    let meta_val: OwnedValue = meta_reply.body().deserialize().map_err(|e| e.to_string())?;

    let mut title = None;
    let mut artist = None;

    if let Value::Dict(dict) = &*meta_val {
        for (k, v) in dict.iter() {
            if let Value::Str(ks) = k {
                if ks.as_str() == "xesam:title" {
                    if let Value::Str(ts) = v {
                        title = Some(ts.to_string());
                    }
                } else if ks.as_str() == "xesam:artist" {
                    if let Value::Str(as_val) = v {
                        artist = Some(as_val.to_string());
                    }
                }
            }
        }
    }

    let mut out = format!("État    : {}\n", match status_str {
        "Playing" => "En lecture",
        "Paused" => "En pause",
        "Stopped" => "Arrêté (en veille)",
        _ => status_str,
    });

    if let Some(st) = artist {
        out.push_str(&format!("Station : {}\n", st));
    }
    if let Some(t) = title {
        out.push_str(&format!("Titre   : {}\n", t));
    }

    Ok(out)
}

/// Récupère l'arbre des favoris JSON depuis l'instance active via D-Bus
pub fn send_get_bookmarks_json() -> Result<String, String> {
    let conn = zbus::blocking::Connection::session().map_err(|e| format!("Connexion D-Bus impossible ({})", e))?;
    let reply = conn.call_method(
        Some("org.mpris.MediaPlayer2.timonde"),
        "/org/mpris/MediaPlayer2",
        Some("org.mpris.MediaPlayer2.Player"),
        "GetBookmarksJson",
        &(),
    ).map_err(|e| format!("Échec appel D-Bus GetBookmarksJson ({})", e))?;

    let json_str: String = reply.body().deserialize().map_err(|e| e.to_string())?;
    Ok(json_str)
}
