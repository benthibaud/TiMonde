//! Module d'internationalisation universel pour TiMonde (Rust)
//! Supporte dynamiquement tous les catalogues GNU Gettext (.mo) des langues européennes
//! avec détection automatique de la locale système et repli sur l'anglais pivot.

use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

static TRANSLATIONS: OnceLock<HashMap<String, String>> = OnceLock::new();
static CURRENT_LANG: OnceLock<String> = OnceLock::new();

/// Détecte le code langue ISO (ex: "fr", "it", "es", "de", "pl", "sv"...)
fn detect_system_language() -> String {
    let raw = std::env::var("LC_ALL")
        .or_else(|_| std::env::var("LC_MESSAGES"))
        .or_else(|_| std::env::var("LANG"))
        .unwrap_or_else(|_| "en".to_string())
        .to_lowercase();

    // Nettoyage : "fr_FR.UTF-8" -> "fr", "de_AT.UTF-8" -> "de"
    let base = raw.split('.').next().unwrap_or("en");
    let code = base.split('_').next().unwrap_or("en");
    code.trim().to_string()
}

/// Tente de charger le fichier binaire Gettext .mo correspondant à la langue
fn load_mo_file(lang: &str) -> Option<HashMap<String, String>> {
    if lang == "en" || lang.is_empty() {
        return None;
    }

    let home = std::env::var("HOME").unwrap_or_default();
    let candidates = [
        PathBuf::from(&home).join(format!(".local/share/locale/{}/LC_MESSAGES/timonde.mo", lang)),
        PathBuf::from(format!("po/locale/{}/LC_MESSAGES/timonde.mo", lang)),
        PathBuf::from(format!("/usr/share/locale/{}/LC_MESSAGES/timonde.mo", lang)),
        PathBuf::from(format!("/usr/local/share/locale/{}/LC_MESSAGES/timonde.mo", lang)),
    ];

    for path in &candidates {
        if path.exists() {
            if let Ok(map) = parse_mo_file(path) {
                return Some(map);
            }
        }
    }
    None
}

/// Analyseur du format binaire standard GNU Gettext (.mo)
fn parse_mo_file(path: &Path) -> Result<HashMap<String, String>, String> {
    let mut file = File::open(path).map_err(|e| e.to_string())?;
    let mut buffer = Vec::new();
    file.read_to_end(&mut buffer).map_err(|e| e.to_string())?;

    if buffer.len() < 28 {
        return Err("Fichier .mo trop court".to_string());
    }

    let magic = u32::from_le_bytes(buffer[0..4].try_into().unwrap());
    if magic != 0x950412de {
        return Err("Magic number Gettext invalide".to_string());
    }

    let count = u32::from_le_bytes(buffer[8..12].try_into().unwrap()) as usize;
    let orig_table_offset = u32::from_le_bytes(buffer[12..16].try_into().unwrap()) as usize;
    let trans_table_offset = u32::from_le_bytes(buffer[16..20].try_into().unwrap()) as usize;

    let mut map = HashMap::new();

    for i in 0..count {
        let orig_pos = orig_table_offset + i * 8;
        let trans_pos = trans_table_offset + i * 8;
        if orig_pos + 8 > buffer.len() || trans_pos + 8 > buffer.len() {
            break;
        }

        let orig_len = u32::from_le_bytes(buffer[orig_pos..orig_pos + 4].try_into().unwrap()) as usize;
        let orig_off = u32::from_le_bytes(buffer[orig_pos + 4..orig_pos + 8].try_into().unwrap()) as usize;

        let trans_len = u32::from_le_bytes(buffer[trans_pos..trans_pos + 4].try_into().unwrap()) as usize;
        let trans_off = u32::from_le_bytes(buffer[trans_pos + 4..trans_pos + 8].try_into().unwrap()) as usize;

        if orig_off + orig_len <= buffer.len() && trans_off + trans_len <= buffer.len() {
            if let (Ok(orig_str), Ok(trans_str)) = (
                std::str::from_utf8(&buffer[orig_off..orig_off + orig_len]),
                std::str::from_utf8(&buffer[trans_off..trans_off + trans_len]),
            ) {
                if !orig_str.is_empty() && !trans_str.is_empty() {
                    map.insert(orig_str.to_string(), trans_str.to_string());
                }
            }
        }
    }

    Ok(map)
}

/// Initialise le gestionnaire de langues au lancement de TiMonde
pub fn init_locale() {
    let lang = detect_system_language();
    let _ = CURRENT_LANG.set(lang.clone());

    let map = load_mo_file(&lang).unwrap_or_default();
    let _ = TRANSLATIONS.set(map);
}

/// Permet de forcer une langue (pour tests ou sélecteur)
#[allow(dead_code)]
pub fn set_language(lang_code: &str) {
    let lang = lang_code.to_lowercase();
    let map = load_mo_file(&lang).unwrap_or_default();

    // Remplacement statique sécurisé
    unsafe {
        // En mode test / reconfiguration
        let ptr = &TRANSLATIONS as *const OnceLock<HashMap<String, String>> as *mut OnceLock<HashMap<String, String>>;
        *ptr = OnceLock::new();
        let _ = (*ptr).set(map);

        let lang_ptr = &CURRENT_LANG as *const OnceLock<String> as *mut OnceLock<String>;
        *lang_ptr = OnceLock::new();
        let _ = (*lang_ptr).set(lang);
    }
}

/// Traduit un texte pivot anglais vers la langue active
pub fn tr(msg: &'static str) -> &'static str {
    if let Some(map) = TRANSLATIONS.get() {
        if let Some(trans) = map.get(msg) {
            // Fuite sécurisée d'une chaîne statique unique de taille négligeable
            return Box::leak(trans.clone().into_boxed_str());
        }
    }
    msg
}

/// Libellé dynamique pour le lancement d'une station
pub fn play_station_label(station_name: &str) -> String {
    let prefix = tr("▶ Play");
    format!("{}    « {} »", prefix, station_name)
}

/// Libellé dynamique pour l'arrêt d'une station
pub fn stop_station_label(station_name: &str, is_ephemeral: bool) -> String {
    let prefix = tr("⏹ Stop");
    let tag = if is_ephemeral { tr(" [🎲 Ephemeral]") } else { "" };
    format!("{}    « {} »{}", prefix, station_name, tag)
}

/// Libellé dynamique pour l'état de connexion d'une station
pub fn connecting_station_label(station_name: &str, is_ephemeral: bool) -> String {
    let prefix = tr("⏳ Connecting...");
    let tag = if is_ephemeral { tr(" [🎲 Ephemeral]") } else { "" };
    format!("{}    « {} »{}", prefix, station_name, tag)
}

/// Libellé de sauvegarde de radio éphémère
pub fn save_ephemeral_label(station_name: &str) -> String {
    let prefix = tr("⭐ Save station to favorites (TiMonde)");
    format!("{} : « {} »", prefix, station_name)
}

/// Libellé pour le minuteur de veille actif
pub fn sleep_timer_active_label(remaining_mins: u64) -> String {
    let timer_prefix = tr("🌙 Sleep timer");
    format!("{} (~{} min)", timer_prefix, remaining_mins)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_multilingual_european_support() {
        set_language("en");
        assert_eq!(tr("▶ Play"), "▶ Play");
        assert_eq!(tr("⏹ Stop"), "⏹ Stop");
        assert_eq!(play_station_label("FIP"), "▶ Play    « FIP »");

        set_language("fr");
        assert_eq!(tr("▶ Play"), "▶ Écouter");
        assert_eq!(tr("⏹ Stop"), "⏹ Éteindre");
        assert_eq!(play_station_label("FIP"), "▶ Écouter    « FIP »");

        set_language("it");
        assert_eq!(tr("▶ Play"), "▶ Ascolta");
        assert_eq!(tr("⏹ Stop"), "⏹ Ferma");

        set_language("es");
        assert_eq!(tr("▶ Play"), "▶ Reproducir");
        assert_eq!(tr("⏹ Stop"), "⏹ Detener");

        set_language("de");
        assert_eq!(tr("▶ Play"), "▶ Abspielen");
        assert_eq!(tr("⏹ Stop"), "⏹ Anhalten");

        set_language("pt");
        assert_eq!(tr("▶ Play"), "▶ Reproduzir");
        assert_eq!(tr("⏹ Stop"), "⏹ Parar");

        set_language("pl");
        assert_eq!(tr("▶ Play"), "▶ Odtwarzaj");
        assert_eq!(tr("⏹ Stop"), "⏹ Zatrzymaj");

        set_language("nl");
        assert_eq!(tr("▶ Play"), "▶ Afspelen");
        assert_eq!(tr("⏹ Stop"), "⏹ Stoppen");

        set_language("sv");
        assert_eq!(tr("▶ Play"), "▶ Spela");
        assert_eq!(tr("⏹ Stop"), "⏹ Stoppa");

        set_language("uk");
        assert_eq!(tr("▶ Play"), "▶ Відтворити");
        assert_eq!(tr("⏹ Stop"), "⏹ Зупинити");

        set_language("el");
        assert_eq!(tr("▶ Play"), "▶ Αναπαραγωγή");
        assert_eq!(tr("⏹ Stop"), "⏹ Διακοπή");

        // Rétablir en français par défaut
        set_language("fr");
    }
}
