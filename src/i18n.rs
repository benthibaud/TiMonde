use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::{OnceLock, RwLock};

static TRANSLATIONS: OnceLock<RwLock<HashMap<String, String>>> = OnceLock::new();
static CURRENT_LANG: OnceLock<RwLock<String>> = OnceLock::new();

/// Normalise le code langue système en identifiant POSIX/Gettext
/// Gère la distinction entre Mandarin (zh_CN) et Cantonais/Traditionnel (zh_TW)
pub fn normalize_lang_code(raw: &str) -> String {
    let base = raw.split('.').next().unwrap_or("en").trim();
    let lower = base.to_lowercase();

    if lower.starts_with("zh_tw")
        || lower.starts_with("zh_hk")
        || lower.starts_with("zh_mo")
        || lower.starts_with("yue")
    {
        return "zh_TW".to_string();
    }
    if lower.starts_with("zh_cn")
        || lower.starts_with("zh_sg")
        || lower == "zh"
    {
        return "zh_CN".to_string();
    }

    let code = base.split('_').next().unwrap_or("en").to_lowercase();
    code.trim().to_string()
}

/// Détecte le code langue ISO du système
fn detect_system_language() -> String {
    let raw = std::env::var("LC_ALL")
        .or_else(|_| std::env::var("LC_MESSAGES"))
        .or_else(|_| std::env::var("LANG"))
        .unwrap_or_else(|_| "en".to_string());

    normalize_lang_code(&raw)
}

/// Tente de charger le fichier binaire Gettext .mo correspondant à la langue
fn load_mo_file(lang: &str) -> Option<HashMap<String, String>> {
    if lang == "en" || lang.is_empty() {
        return None;
    }

    let home = std::env::var("HOME").unwrap_or_default();
    let mut candidates = Vec::new();
    #[cfg(debug_assertions)]
    {
        candidates.push(
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join(format!("po/locale/{}/LC_MESSAGES/timonde.mo", lang)),
        );
    }
    candidates.extend([
        PathBuf::from(&home).join(format!(".local/share/locale/{}/LC_MESSAGES/timonde.mo", lang)),
        PathBuf::from(format!("po/locale/{}/LC_MESSAGES/timonde.mo", lang)),
        PathBuf::from(format!("/usr/share/locale/{}/LC_MESSAGES/timonde.mo", lang)),
        PathBuf::from(format!("/usr/local/share/locale/{}/LC_MESSAGES/timonde.mo", lang)),
    ]);

    for path in &candidates {
        if path.exists() {
            if let Ok(map) = parse_mo_file(path) {
                return Some(map);
            }
        }
    }
    None
}

fn read_u32_le(buf: &[u8], offset: usize) -> Option<u32> {
    buf.get(offset..offset + 4)?
        .try_into()
        .ok()
        .map(u32::from_le_bytes)
}

/// Analyseur du format binaire standard GNU Gettext (.mo)
fn parse_mo_file(path: &Path) -> Result<HashMap<String, String>, String> {
    let mut file = File::open(path).map_err(|e| e.to_string())?;
    let mut buffer = Vec::new();
    file.read_to_end(&mut buffer).map_err(|e| e.to_string())?;

    if buffer.len() < 28 {
        return Err("Fichier .mo trop court".to_string());
    }

    let magic = match read_u32_le(&buffer, 0) {
        Some(m) => m,
        None => return Err("Impossible de lire l'en-tête .mo".to_string()),
    };
    if magic != 0x950412de {
        return Err("Magic number Gettext invalide".to_string());
    }

    let count = match read_u32_le(&buffer, 8) {
        Some(c) => c as usize,
        None => return Err("Nombre de traductions manquant".to_string()),
    };
    let orig_table_offset = match read_u32_le(&buffer, 12) {
        Some(off) => off as usize,
        None => return Err("Offset table originale manquant".to_string()),
    };
    let trans_table_offset = match read_u32_le(&buffer, 16) {
        Some(off) => off as usize,
        None => return Err("Offset table traduite manquant".to_string()),
    };

    let mut map = HashMap::new();

    for i in 0..count {
        let orig_pos = orig_table_offset + i * 8;
        let trans_pos = trans_table_offset + i * 8;
        if orig_pos + 8 > buffer.len() || trans_pos + 8 > buffer.len() {
            break;
        }

        let orig_len = match read_u32_le(&buffer, orig_pos) {
            Some(l) => l as usize,
            None => break,
        };
        let orig_off = match read_u32_le(&buffer, orig_pos + 4) {
            Some(off) => off as usize,
            None => break,
        };

        let trans_len = match read_u32_le(&buffer, trans_pos) {
            Some(l) => l as usize,
            None => break,
        };
        let trans_off = match read_u32_le(&buffer, trans_pos + 4) {
            Some(off) => off as usize,
            None => break,
        };

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
    let map = load_mo_file(&lang).unwrap_or_default();

    if let Some(lock) = CURRENT_LANG.get() {
        if let Ok(mut guard) = lock.write() {
            *guard = lang;
        }
    } else {
        let _ = CURRENT_LANG.set(RwLock::new(lang));
    }

    if let Some(lock) = TRANSLATIONS.get() {
        if let Ok(mut guard) = lock.write() {
            *guard = map;
        }
    } else {
        let _ = TRANSLATIONS.set(RwLock::new(map));
    }
}

/// Permet de forcer une langue (pour tests ou sélecteur)
#[allow(dead_code)]
pub fn set_language(lang_code: &str) {
    let lang = normalize_lang_code(lang_code);
    let map = load_mo_file(&lang).unwrap_or_default();

    let lock = TRANSLATIONS.get_or_init(|| RwLock::new(HashMap::new()));
    if let Ok(mut guard) = lock.write() {
        *guard = map;
    }

    let lang_lock = CURRENT_LANG.get_or_init(|| RwLock::new(String::new()));
    if let Ok(mut guard) = lang_lock.write() {
        *guard = lang;
    }
}

/// Traduit un texte pivot anglais vers la langue active
pub fn tr(msg: &str) -> String {
    if let Some(lock) = TRANSLATIONS.get() {
        if let Ok(map) = lock.read() {
            if let Some(trans) = map.get(msg) {
                return trans.clone();
            }
        }
    }
    msg.to_string()
}

/// Libellé dynamique pour le lancement d'une station
pub fn play_station_label(station_name: &str) -> String {
    let prefix = tr("Play");
    format!("{} : « {} »", prefix, station_name)
}

/// Libellé dynamique pour l'arrêt d'une station
pub fn stop_station_label(station_name: &str, is_ephemeral: bool) -> String {
    let prefix = tr("Stop");
    let tag = if is_ephemeral {
        format!(" {}", tr("[Ephemeral]"))
    } else {
        String::new()
    };
    format!("{} : « {} »{}", prefix, station_name, tag)
}

/// Libellé dynamique pour l'état de connexion d'une station
pub fn connecting_station_label(station_name: &str, is_ephemeral: bool) -> String {
    let prefix = tr("Connecting...");
    let tag = if is_ephemeral {
        format!(" {}", tr("[Ephemeral]"))
    } else {
        String::new()
    };
    format!("{} : « {} »{}", prefix, station_name, tag)
}

/// Libellé de sauvegarde de radio éphémère
pub fn save_ephemeral_label(station_name: &str) -> String {
    let prefix = tr("Save station to favorites (TiMonde)");
    format!("{} : « {} »", prefix, station_name)
}

/// Libellé pour le minuteur de veille actif
pub fn sleep_timer_active_label(remaining_mins: u64) -> String {
    let timer_prefix = tr("Sleep timer");
    format!("{} (~{} min)", timer_prefix, remaining_mins)
}

#[cfg(test)]
pub static I18N_TEST_MUTEX: std::sync::Mutex<()> = std::sync::Mutex::new(());

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_chinese_mandarin_and_cantonese_distinction() {
        let _lock = I18N_TEST_MUTEX.lock().unwrap();
        assert_eq!(normalize_lang_code("zh_CN.UTF-8"), "zh_CN");
        assert_eq!(normalize_lang_code("zh_SG.UTF-8"), "zh_CN");
        assert_eq!(normalize_lang_code("zh.UTF-8"), "zh_CN");
        assert_eq!(normalize_lang_code("zh_TW.UTF-8"), "zh_TW");
        assert_eq!(normalize_lang_code("zh_HK.UTF-8"), "zh_TW");
        assert_eq!(normalize_lang_code("yue_HK.UTF-8"), "zh_TW");

        // Mandarin
        set_language("zh_CN");
        assert_eq!(tr("Play"), "播放");
        assert_eq!(tr("Edit"), "编辑");
        assert_eq!(tr("Delete"), "删除");

        // Cantonais / Traditionnel
        set_language("zh_TW");
        assert_eq!(tr("Play"), "播放");
        assert_eq!(tr("Edit"), "編輯");
        assert_eq!(tr("Delete"), "刪除");
        assert_eq!(tr("Zap to another random station"), "隨機切換到其他電台");
    }

    #[test]
    fn test_multilingual_european_and_world_support() {
        let _lock = I18N_TEST_MUTEX.lock().unwrap();
        set_language("en");
        assert_eq!(tr("Play"), "Play");
        assert_eq!(tr("Stop"), "Stop");
        assert_eq!(play_station_label("FIP"), "Play : « FIP »");

        set_language("fr");
        assert_eq!(tr("Play"), "Écouter");
        assert_eq!(tr("Stop"), "Éteindre");
        assert_eq!(play_station_label("FIP"), "Écouter : « FIP »");

        set_language("it");
        assert_eq!(tr("Play"), "Ascolta");

        set_language("es");
        assert_eq!(tr("Play"), "Reproducir");

        set_language("de");
        assert_eq!(tr("Play"), "Abspielen");

        set_language("ja");
        assert_eq!(tr("Play"), "再生");

        set_language("ko");
        assert_eq!(tr("Play"), "재생");

        set_language("ar");
        assert_eq!(tr("Play"), "تشغيل");

        set_language("tr");
        assert_eq!(tr("Play"), "Oynat");

        // Rétablir en français par défaut
        set_language("fr");
    }
}
