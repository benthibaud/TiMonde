//! Module système de notification de bureau pour TiMonde
//! Centralise l'envoi de messages non intrusifs (sans interrompre la musique).

use std::process::Command;

/// Envoie une notification discrète et silencieuse sur le bureau via notify-send
pub fn notify(title: &str, body: &str) {
    let title_owned = title.to_string();
    let body_owned = body.to_string();
    std::thread::spawn(move || {
        if let Ok(mut child) = Command::new("notify-send")
            .arg("-a")
            .arg("TiMonde")
            .arg("-i")
            .arg("audio-speakers")
            .arg("-h")
            .arg("boolean:suppress-sound:true")
            .arg(&title_owned)
            .arg(&body_owned)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
        {
            let _ = child.wait();
        }
    });
}
