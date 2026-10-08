//! Gestion de l'état persistant de TiMonde (dernière station écoutée, état de veille)
//! Persists the last played station to ~/.config/timonde/state.json for instant recall.

use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::{BufReader, BufWriter};
use std::path::{Path, PathBuf};
use crate::models::Station;

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq)]
pub struct AppState {
    /// Dernière station favorite écoutée (utilisée au démarrage pour "Allumer la radio")
    pub last_station: Option<Station>,
    /// Dernière station éphémère jouée (mémorisée pour un ajout ultérieur éventuel)
    pub last_ephemeral: Option<Station>,
}

impl AppState {
    pub fn new() -> Self {
        Self::default()
    }

    /// Chemin par défaut du fichier d'état dans ~/.config/timonde/state.json
    pub fn default_path() -> PathBuf {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(home).join(".config").join("timonde").join("state.json")
    }

    /// Charge l'état depuis le fichier JSON spécifié (tolérant aux erreurs)
    pub fn load(path: &Path) -> Self {
        if !path.exists() {
            return Self::default();
        }
        match File::open(path) {
            Ok(file) => {
                let reader = BufReader::new(file);
                serde_json::from_reader(reader).unwrap_or_default()
            }
            Err(e) => {
                log::warn!("Impossible de lire {:?} : {}", path, e);
                Self::default()
            }
        }
    }

    /// Sauvegarde atomique de l'état pour résister à une extinction brutale du PC
    pub fn save(&self, path: &Path) -> std::io::Result<()> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let temp_path = path.with_extension("tmp");
        {
            let file = File::create(&temp_path)?;
            let writer = BufWriter::new(file);
            serde_json::to_writer_pretty(writer, self)?;
        }
        fs::rename(temp_path, path)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_app_state_roundtrip() {
        let temp_dir = std::env::temp_dir();
        let state_path = temp_dir.join("timonde_test_state.json");

        let mut state = AppState::new();
        let mut st = Station::new("Bluegrass Planet Radio", "http://65.108.105.26:7966/stream");
        st.country = Some("US".to_string());
        st.timezone = Some("America/New_York".to_string());
        state.last_station = Some(st);

        state.save(&state_path).expect("Sauvegarde d'état");

        let loaded = AppState::load(&state_path);
        assert_eq!(state, loaded);

        let _ = std::fs::remove_file(&state_path);
    }
}
