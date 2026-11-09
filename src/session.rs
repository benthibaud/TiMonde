//! Module de gestion unifiée de la session de lecture et du cycle de vie audio (TiMonde).
//!
//! Regroupe l'état de lecture (station, titre, volume, éphémère, moteur GStreamer)
//! sous une structure unique et cohérente. Applique la Règle d'Or GStreamer :
//! aucun appel bloquant au pipeline audio n'est exécuté sous verrou partagé.

use std::sync::{Arc, Mutex};
use crate::audio::{AudioEngine, PlaybackState};
use crate::models::Station;
use crate::sync_util::SafeLock;

/// État unifié de la session de lecture
pub struct PlaybackSession {
    pub engine: Option<AudioEngine>,
    pub current_station: Option<Station>,
    pub current_title: Option<String>,
    pub is_ephemeral: bool,
    pub volume: f64,
}

impl PlaybackSession {
    pub fn new(initial_volume: f64) -> Self {
        Self {
            engine: None,
            current_station: None,
            current_title: None,
            is_ephemeral: false,
            volume: initial_volume.clamp(0.0, 1.0),
        }
    }

    /// Retourne l'état de lecture actuel du moteur (ou Stopped si aucun moteur)
    pub fn state(&self) -> PlaybackState {
        match self.engine.as_ref() {
            Some(e) => e.state(),
            None => PlaybackState::Stopped,
        }
    }

    /// Réinitialise les métadonnées de lecture et extrait le moteur audio
    /// afin de permettre son arrêt et son drop hors du verrou de session.
    pub fn take_engine(&mut self) -> Option<AudioEngine> {
        self.current_station = None;
        self.current_title = None;
        self.is_ephemeral = false;
        self.engine.take()
    }

    /// Applique le volume à la session et au moteur sous-jacent s'il est alloué
    pub fn set_volume(&mut self, vol: f64) {
        let clamped = vol.clamp(0.0, 1.0);
        self.volume = clamped;
        if let Some(ref e) = self.engine {
            e.set_volume(clamped);
        }
    }
}

/// Arrête la session de lecture de façon déterministe, détruit le moteur audio hors verrou
/// et restitue immédiatement la mémoire physique au système d'exploitation via malloc_trim (Option A).
pub fn stop_session(session: &Arc<Mutex<PlaybackSession>>) {
    let engine_to_drop = {
        let mut guard = session.safe_lock();
        guard.take_engine()
    };
    if let Some(engine) = engine_to_drop {
        let _ = engine.stop();
        drop(engine);
    }
    #[cfg(target_os = "linux")]
    unsafe {
        libc::malloc_trim(0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_playback_session_lifecycle() {
        let session = Arc::new(Mutex::new(PlaybackSession::new(0.75)));
        {
            let mut s = session.safe_lock();
            assert_eq!(s.volume, 0.75);
            assert_eq!(s.state(), PlaybackState::Stopped);
            assert!(s.current_station.is_none());

            s.current_station = Some(Station::new("Test Radio", "http://test.stream"));
            s.current_title = Some("Artist - Title".to_string());
            s.is_ephemeral = true;
        }

        // Arrêt déterministe
        stop_session(&session);

        {
            let s = session.safe_lock();
            assert!(s.current_station.is_none());
            assert!(s.current_title.is_none());
            assert!(!s.is_ephemeral);
            assert_eq!(s.state(), PlaybackState::Stopped);
        }

        // Idempotence : un second arrêt ne panique pas et ne bloque pas
        stop_session(&session);
    }

    #[test]
    fn test_volume_clamping() {
        let mut s = PlaybackSession::new(1.5);
        assert_eq!(s.volume, 1.0);

        s.set_volume(-0.5);
        assert_eq!(s.volume, 0.0);

        s.set_volume(0.42);
        assert!((s.volume - 0.42).abs() < 1e-6);
    }
}
