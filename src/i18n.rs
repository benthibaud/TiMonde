//! Module d'internationalisation natif pour TiMonde (Rust)
//! Détecte la locale de l'environnement (Français par défaut si `LANG` commence par "fr", Anglais sinon).

use std::sync::atomic::{AtomicBool, Ordering};

static IS_FRENCH: AtomicBool = AtomicBool::new(true);

/// Initialise la locale au démarrage de l'application
pub fn init_locale() {
    let lang = std::env::var("LC_ALL")
        .or_else(|_| std::env::var("LC_MESSAGES"))
        .or_else(|_| std::env::var("LANG"))
        .unwrap_or_default()
        .to_lowercase();
    let fr = lang.starts_with("fr");
    IS_FRENCH.store(fr, Ordering::SeqCst);
}

/// Force une locale pour les tests unitaires
#[allow(dead_code)]
pub fn set_french(fr: bool) {
    IS_FRENCH.store(fr, Ordering::SeqCst);
}

/// Indique si l'interface est en français
pub fn is_french() -> bool {
    IS_FRENCH.load(Ordering::SeqCst)
}

/// Traduit un texte statique selon la langue active
pub fn tr(msg: &'static str) -> &'static str {
    if is_french() {
        return msg;
    }
    match msg {
        // Actions principales & Menu racine
        "▶ Écouter" => "▶ Play",
        "⏹ Éteindre" => "⏹ Stop",
        "⏳ Connexion..." => "⏳ Connecting...",
        "✏️ Éditer" => "✏️ Edit",
        "🗑️ Supprimer" => "🗑️ Delete",
        "🎲 Zapper vers une autre radio au hasard" => "🎲 Zap to another random station",
        "🎲 Écouter une radio au hasard (Découverte éphémère)" => "🎲 Play random radio (Ephemeral discovery)",
        " [🎲 Éphémère]" => " [🎲 Ephemeral]",

        // Options et sous-menus
        "⚙️ Options" => "⚙️ Options",
        "➕ Ajouter une radio..." => "➕ Add a station...",
        "📻 Découvrir & Importer des radios..." => "📻 Discover & Import stations...",
        "📥 Importer mes fichiers (XML, CSV, JSON, M3U)..." => "📥 Import my files (XML, CSV, JSON, M3U)...",
        "↕️ Classer groupes et radios..." => "↕️ Manage groups and stations...",
        "📝 Ouvrir bookmarks.xml" => "📝 Open bookmarks.xml",
        "Quitter TiMonde" => "Quit TiMonde",

        // Volume & Veille
        "Muet (0%)" => "Mute (0%)",
        "🌙 Minuteur de veille" => "🌙 Sleep timer",
        "💤 Minuteur de mise en veille" => "💤 Sleep timer",
        "⏱️ Dans 15 minutes" => "⏱️ In 15 minutes",
        "⏱️ Dans 30 minutes" => "⏱️ In 30 minutes",
        "⏱️ Dans 45 minutes" => "⏱️ In 45 minutes",
        "⏱️ Dans 60 minutes (1h)" => "⏱️ In 60 minutes (1h)",
        "❌ Annuler la mise en veille" => "❌ Cancel sleep timer",

        // Périodes astronomiques & fuseaux
        "Aube" => "Dawn",
        "Matin" => "Morning",
        "Journée" => "Daytime",
        "Après-midi" => "Afternoon",
        "Soirée" => "Evening",
        "Nuit" => "Night",
        "Demain" => "Tomorrow",
        "Hier" => "Yesterday",
        "Aujourd'hui" => "Today",
        "Même heure" => "Same time",

        // Notifications & alertes
        "Impossible d'initialiser l'audio" => "Unable to initialize audio",
        "Minuteur de mise en veille annulé." => "Sleep timer canceled.",
        "💤 Minuteur écoulé : mise en veille et arrêt de la lecture." => "💤 Sleep timer expired: pausing and entering standby.",
        "Aucune radio n'est en cours d'écoute." => "No station currently playing.",
        "Outil de bouquets introuvable" => "Bouquets discovery tool not found",
        "Impossible d'ouvrir l'outil de bouquets" => "Unable to open bouquets discovery tool",
        "Aucun groupe de radios à classer" => "No radio groups to organize",
        "Outil de réorganisation introuvable" => "Reorder tool not found",
        "Impossible d'ouvrir l'outil de réorganisation" => "Unable to open reorder tool",

        _ => msg,
    }
}

/// Libellé dynamique pour le lancement d'une station
pub fn play_station_label(station_name: &str) -> String {
    if is_french() {
        format!("▶ Écouter    « {} »", station_name)
    } else {
        format!("▶ Play    « {} »", station_name)
    }
}

/// Libellé dynamique pour l'arrêt d'une station
pub fn stop_station_label(station_name: &str, is_ephemeral: bool) -> String {
    let tag = if is_ephemeral {
        if is_french() { " [🎲 Éphémère]" } else { " [🎲 Ephemeral]" }
    } else {
        ""
    };
    if is_french() {
        format!("⏹ Éteindre    « {} »{}", station_name, tag)
    } else {
        format!("⏹ Stop    « {} »{}", station_name, tag)
    }
}

/// Libellé dynamique pour l'état de connexion d'une station
pub fn connecting_station_label(station_name: &str, is_ephemeral: bool) -> String {
    let tag = if is_ephemeral {
        if is_french() { " [🎲 Éphémère]" } else { " [🎲 Ephemeral]" }
    } else {
        ""
    };
    if is_french() {
        format!("⏳ Connexion...    « {} »{}", station_name, tag)
    } else {
        format!("⏳ Connecting...    « {} »{}", station_name, tag)
    }
}

/// Libellé de sauvegarde de radio éphémère
pub fn save_ephemeral_label(station_name: &str) -> String {
    if is_french() {
        format!("⭐ Sauvegarder « {} » dans mes favoris...", station_name)
    } else {
        format!("⭐ Save « {} » to favorites...", station_name)
    }
}

/// Libellé pour le minuteur de veille actif
pub fn sleep_timer_active_label(remaining_mins: u64) -> String {
    if is_french() {
        format!("💤 Veille active (arrêt dans ~{} min)", remaining_mins)
    } else {
        format!("💤 Active timer (stop in ~{} min)", remaining_mins)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_i18n_toggle() {
        set_french(true);
        assert_eq!(tr("▶ Écouter"), "▶ Écouter");
        assert_eq!(tr("⏹ Éteindre"), "⏹ Éteindre");
        assert_eq!(play_station_label("FIP"), "▶ Écouter    « FIP »");

        set_french(false);
        assert_eq!(tr("▶ Écouter"), "▶ Play");
        assert_eq!(tr("⏹ Éteindre"), "⏹ Stop");
        assert_eq!(play_station_label("FIP"), "▶ Play    « FIP »");
        assert_eq!(stop_station_label("FIP", true), "⏹ Stop    « FIP » [🎲 Ephemeral]");

        // Remettre en français pour ne pas affecter les autres tests
        set_french(true);
    }
}
