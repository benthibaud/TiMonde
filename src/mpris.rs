use std::sync::{Arc, Mutex};
use std::collections::HashMap;
use zbus::interface;
use zbus::zvariant::{ObjectPath, Value, OwnedValue};
use crate::audio::{AudioEngine, PlaybackState};
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
    pub audio: Arc<Mutex<Option<AudioEngine>>>,
    pub current_volume: Arc<Mutex<f64>>,
    pub current_station: Arc<Mutex<Option<Station>>>,
    pub current_title: Arc<Mutex<Option<String>>>,
    pub last_station: Arc<Mutex<Option<Station>>>,
    pub root_group: Arc<Mutex<Group>>,
    pub on_play: Arc<dyn Fn(Station) + Send + Sync>,
    pub on_stop: Arc<dyn Fn() + Send + Sync>,
    pub on_update: Arc<dyn Fn() + Send + Sync>,
}

#[interface(name = "org.mpris.MediaPlayer2.Player")]
impl MprisPlayer {
    fn next(&self) {
        let all_stations = get_all_stations(&self.root_group.lock().unwrap());
        if all_stations.is_empty() { return; }

        let cur = self.current_station.lock().unwrap().clone();
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
        let all_stations = get_all_stations(&self.root_group.lock().unwrap());
        if all_stations.is_empty() { return; }

        let cur = self.current_station.lock().unwrap().clone();
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
        let guard = self.audio.lock().unwrap();
        if let Some(ref e) = *guard {
            let _ = e.pause();
        }
        drop(guard);
        (self.on_update)();
    }

    fn play_pause(&self) {
        let guard = self.audio.lock().unwrap();
        if let Some(ref e) = *guard {
            match e.state() {
                PlaybackState::Playing => {
                    let _ = e.pause();
                    drop(guard);
                    (self.on_update)();
                    return;
                }
                PlaybackState::Paused => {
                    let _ = e.resume();
                    drop(guard);
                    (self.on_update)();
                    return;
                }
                _ => {}
            }
        }
        drop(guard);

        if let Some(st) = self.last_station.lock().unwrap().clone() {
            (self.on_play)(st);
        }
    }

    fn stop(&self) {
        (self.on_stop)();
    }

    fn play(&self) {
        let guard = self.audio.lock().unwrap();
        if let Some(ref e) = *guard {
            if e.state() == PlaybackState::Paused {
                let _ = e.resume();
                drop(guard);
                (self.on_update)();
                return;
            }
        }
        drop(guard);

        if let Some(st) = self.last_station.lock().unwrap().clone() {
            (self.on_play)(st);
        }
    }

    fn seek(&self, _offset: i64) {}
    fn set_position(&self, _track_id: ObjectPath<'_>, _position: i64) {}
    fn open_uri(&self, uri: String) {
        (self.on_play)(Station::new(uri.clone(), uri));
    }

    #[zbus(property)]
    fn playback_status(&self) -> String {
        let guard = self.audio.lock().unwrap();
        match guard.as_ref().map(|e| e.state()) {
            Some(PlaybackState::Playing) => "Playing".to_string(),
            Some(PlaybackState::Paused) => "Paused".to_string(),
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
        map.insert(
            "mpris:trackid".to_string(),
            Value::ObjectPath(ObjectPath::from_static_str("/org/mpris/MediaPlayer2/CurrentTrack").unwrap())
        );

        let st_guard = self.current_station.lock().unwrap();
        let title_guard = self.current_title.lock().unwrap();

        let track_title = if let Some(ref t) = *title_guard {
            t.clone()
        } else if let Some(ref s) = *st_guard {
            s.name.clone()
        } else {
            "TiMonde".to_string()
        };

        map.insert("xesam:title".to_string(), Value::Str(track_title.into()));

        if let Some(ref s) = *st_guard {
            map.insert("xesam:artist".to_string(), Value::Str(s.name.clone().into()));
            map.insert("xesam:url".to_string(), Value::Str(s.url.clone().into()));
        }

        map
    }

    #[zbus(property)]
    fn volume(&self) -> f64 {
        *self.current_volume.lock().unwrap()
    }

    #[zbus(property)]
    fn set_volume(&self, vol: f64) {
        let mut v_guard = self.current_volume.lock().unwrap();
        *v_guard = vol.clamp(0.0, 1.5);
        let a_guard = self.audio.lock().unwrap();
        if let Some(ref e) = *a_guard {
            e.set_volume(*v_guard);
        }
        drop(a_guard);
        drop(v_guard);
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
    audio: Arc<Mutex<Option<AudioEngine>>>,
    current_volume: Arc<Mutex<f64>>,
    current_station: Arc<Mutex<Option<Station>>>,
    current_title: Arc<Mutex<Option<String>>>,
    last_station: Arc<Mutex<Option<Station>>>,
    root_group: Arc<Mutex<Group>>,
    on_play: Arc<dyn Fn(Station) + Send + Sync>,
    on_stop: Arc<dyn Fn() + Send + Sync>,
    on_update: Arc<dyn Fn() + Send + Sync>,
) {
    std::thread::spawn(move || {
        let res = zbus::blocking::connection::Builder::session()
            .and_then(|b| b.name("org.mpris.MediaPlayer2.timonde"))
            .and_then(|b| b.serve_at("/org/mpris/MediaPlayer2", MprisRoot))
            .and_then(|b| {
                b.serve_at(
                    "/org/mpris/MediaPlayer2",
                    MprisPlayer {
                        audio,
                        current_volume,
                        current_station,
                        current_title,
                        last_station,
                        root_group,
                        on_play,
                        on_stop,
                        on_update,
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
