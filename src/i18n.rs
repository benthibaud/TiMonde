//! Module d'internationalisation universel pour TiMonde (Rust)
//! Clés de référence en Anglais (pivot international).
//! Supporte le Français (fr), l'Espagnol (es), l'Allemand (de), le Portugais (pt)
//! et l'Anglais par défaut (en) pour toutes les autres langues.

use std::sync::atomic::{AtomicU8, Ordering};

const LANG_EN: u8 = 0;
const LANG_FR: u8 = 1;
const LANG_ES: u8 = 2;
const LANG_DE: u8 = 3;
const LANG_PT: u8 = 4;

static CURRENT_LANG: AtomicU8 = AtomicU8::new(LANG_FR);

/// Initialise la langue active à partir des variables d'environnement système
pub fn init_locale() {
    let lang = std::env::var("LC_ALL")
        .or_else(|_| std::env::var("LC_MESSAGES"))
        .or_else(|_| std::env::var("LANG"))
        .unwrap_or_default()
        .to_lowercase();

    let code = if lang.starts_with("fr") {
        LANG_FR
    } else if lang.starts_with("es") {
        LANG_ES
    } else if lang.starts_with("de") {
        LANG_DE
    } else if lang.starts_with("pt") {
        LANG_PT
    } else {
        LANG_EN
    };
    CURRENT_LANG.store(code, Ordering::SeqCst);
}

/// Force une langue spécifique (utile pour les tests et la sélection manuelle)
#[allow(dead_code)]
pub fn set_language(lang_code: &str) {
    let code = match lang_code.to_lowercase().as_str() {
        "fr" | "fr_fr" => LANG_FR,
        "es" | "es_es" => LANG_ES,
        "de" | "de_de" => LANG_DE,
        "pt" | "pt_pt" | "pt_br" => LANG_PT,
        _ => LANG_EN,
    };
    CURRENT_LANG.store(code, Ordering::SeqCst);
}

/// Traduit un texte pivot anglais vers la langue système active
pub fn tr(msg: &'static str) -> &'static str {
    let lang = CURRENT_LANG.load(Ordering::SeqCst);
    if lang == LANG_EN {
        return msg;
    }

    match (msg, lang) {
        // --- Actions de lecture & plateau ---
        ("▶ Play", LANG_FR) => "▶ Écouter",
        ("▶ Play", LANG_ES) => "▶ Reproducir",
        ("▶ Play", LANG_DE) => "▶ Abspielen",
        ("▶ Play", LANG_PT) => "▶ Reproduzir",

        ("⏹ Stop", LANG_FR) => "⏹ Éteindre",
        ("⏹ Stop", LANG_ES) => "⏹ Detener",
        ("⏹ Stop", LANG_DE) => "⏹ Anhalten",
        ("⏹ Stop", LANG_PT) => "⏹ Parar",

        ("⏳ Connecting...", LANG_FR) => "⏳ Connexion...",
        ("⏳ Connecting...", LANG_ES) => "⏳ Conectando...",
        ("⏳ Connecting...", LANG_DE) => "⏳ Verbinden...",
        ("⏳ Connecting...", LANG_PT) => "⏳ Conectando...",

        ("✏️ Edit", LANG_FR) => "✏️ Éditer",
        ("✏️ Edit", LANG_ES) => "✏️ Editar",
        ("✏️ Edit", LANG_DE) => "✏️ Bearbeiten",
        ("✏️ Edit", LANG_PT) => "✏️ Editar",

        ("🗑️ Delete", LANG_FR) => "🗑️ Supprimer",
        ("🗑️ Delete", LANG_ES) => "🗑️ Eliminar",
        ("🗑️ Delete", LANG_DE) => "🗑️ Löschen",
        ("🗑️ Delete", LANG_PT) => "🗑️ Eliminar",

        ("🎲 Zap to another random station", LANG_FR) => "🎲 Zapper vers une autre radio au hasard",
        ("🎲 Zap to another random station", LANG_ES) => "🎲 Cambiar a otra radio al azar",
        ("🎲 Zap to another random station", LANG_DE) => "🎲 Zu einem anderen Zufallssender wechseln",
        ("🎲 Zap to another random station", LANG_PT) => "🎲 Mudar para outra estação aleatória",

        ("🎲 Play random radio (Ephemeral discovery)", LANG_FR) => "🎲 Écouter une radio au hasard (Découverte éphémère)",
        ("🎲 Play random radio (Ephemeral discovery)", LANG_ES) => "🎲 Escuchar una radio al azar (Descubrimiento efímero)",
        ("🎲 Play random radio (Ephemeral discovery)", LANG_DE) => "🎲 Zufälligen Sender hören (Flüchtige Entdeckung)",
        ("🎲 Play random radio (Ephemeral discovery)", LANG_PT) => "🎲 Ouvir uma rádio aleatória (Descoberta efémera)",

        (" [🎲 Ephemeral]", LANG_FR) => " [🎲 Éphémère]",
        (" [🎲 Ephemeral]", LANG_ES) => " [🎲 Efímero]",
        (" [🎲 Ephemeral]", LANG_DE) => " [🎲 Flüchtig]",
        (" [🎲 Ephemeral]", LANG_PT) => " [🎲 Efémero]",

        // --- Menu Options & Gestion ---
        ("⚙️ Options", LANG_FR) => "⚙️ Options",
        ("⚙️ Options", LANG_ES) => "⚙️ Opciones",
        ("⚙️ Options", LANG_DE) => "⚙️ Optionen",
        ("⚙️ Options", LANG_PT) => "⚙️ Opções",

        ("➕ Add a station...", LANG_FR) => "➕ Ajouter une radio...",
        ("➕ Add a station...", LANG_ES) => "➕ Añadir una radio...",
        ("➕ Add a station...", LANG_DE) => "➕ Sender hinzufügen...",
        ("➕ Add a station...", LANG_PT) => "➕ Adicionar uma estação...",

        ("📻 Discover & Import stations...", LANG_FR) => "📻 Découvrir & Importer des radios...",
        ("📻 Discover & Import stations...", LANG_ES) => "📻 Descubrir e importar radios...",
        ("📻 Discover & Import stations...", LANG_DE) => "📻 Sender entdecken & importieren...",
        ("📻 Discover & Import stations...", LANG_PT) => "📻 Descobrir e importar estações...",

        ("📥 Import my files (XML, CSV, JSON, M3U)...", LANG_FR) => "📥 Importer mes fichiers (XML, CSV, JSON, M3U)...",
        ("📥 Import my files (XML, CSV, JSON, M3U)...", LANG_ES) => "📥 Importar mis archivos (XML, CSV, JSON, M3U)...",
        ("📥 Import my files (XML, CSV, JSON, M3U)...", LANG_DE) => "📥 Meine Dateien importieren (XML, CSV, JSON, M3U)...",
        ("📥 Import my files (XML, CSV, JSON, M3U)...", LANG_PT) => "📥 Importar os meus ficheiros (XML, CSV, JSON, M3U)...",

        ("↕️ Manage groups and stations...", LANG_FR) => "↕️ Classer groupes et radios...",
        ("↕️ Manage groups and stations...", LANG_ES) => "↕️ Organizar grupos y radios...",
        ("↕️ Manage groups and stations...", LANG_DE) => "↕️ Gruppen und Sender verwalten...",
        ("↕️ Manage groups and stations...", LANG_PT) => "↕️ Gerir grupos e estações...",

        ("📝 Open bookmarks.xml", LANG_FR) => "📝 Ouvrir bookmarks.xml",
        ("📝 Open bookmarks.xml", LANG_ES) => "📝 Abrir bookmarks.xml",
        ("📝 Open bookmarks.xml", LANG_DE) => "📝 bookmarks.xml öffnen",
        ("📝 Open bookmarks.xml", LANG_PT) => "📝 Abrir bookmarks.xml",

        ("Quit TiMonde", LANG_FR) => "Quitter TiMonde",
        ("Quit TiMonde", LANG_ES) => "Salir de TiMonde",
        ("Quit TiMonde", LANG_DE) => "TiMonde beenden",
        ("Quit TiMonde", LANG_PT) => "Sair do TiMonde",

        // --- Volume & Veille ---
        ("Mute (0%)", LANG_FR) => "Muet (0%)",
        ("Mute (0%)", LANG_ES) => "Silencio (0%)",
        ("Mute (0%)", LANG_DE) => "Stumm (0%)",
        ("Mute (0%)", LANG_PT) => "Mudo (0%)",

        ("🌙 Sleep timer", LANG_FR) => "🌙 Minuteur de veille",
        ("🌙 Sleep timer", LANG_ES) => "🌙 Temporizador de apagado",
        ("🌙 Sleep timer", LANG_DE) => "🌙 Schlummermodus",
        ("🌙 Sleep timer", LANG_PT) => "🌙 Temporizador de suspensão",

        ("⏱️ In 15 minutes", LANG_FR) => "⏱️ Dans 15 minutes",
        ("⏱️ In 15 minutes", LANG_ES) => "⏱️ En 15 minutos",
        ("⏱️ In 15 minutes", LANG_DE) => "⏱️ In 15 Minuten",
        ("⏱️ In 15 minutes", LANG_PT) => "⏱️ Em 15 minutos",

        ("⏱️ In 30 minutes", LANG_FR) => "⏱️ Dans 30 minutes",
        ("⏱️ In 30 minutes", LANG_ES) => "⏱️ En 30 minutos",
        ("⏱️ In 30 minutes", LANG_DE) => "⏱️ In 30 Minuten",
        ("⏱️ In 30 minutes", LANG_PT) => "⏱️ Em 30 minutos",

        ("⏱️ In 45 minutes", LANG_FR) => "⏱️ Dans 45 minutes",
        ("⏱️ In 45 minutes", LANG_ES) => "⏱️ En 45 minutos",
        ("⏱️ In 45 minutes", LANG_DE) => "⏱️ In 45 Minuten",
        ("⏱️ In 45 minutes", LANG_PT) => "⏱️ Em 45 minutos",

        ("⏱️ In 60 minutes (1h)", LANG_FR) => "⏱️ Dans 60 minutes (1h)",
        ("⏱️ In 60 minutes (1h)", LANG_ES) => "⏱️ En 60 minutos (1h)",
        ("⏱️ In 60 minutes (1h)", LANG_DE) => "⏱️ In 60 Minuten (1 Std.)",
        ("⏱️ In 60 minutes (1h)", LANG_PT) => "⏱️ Em 60 minutos (1h)",

        ("❌ Cancel sleep timer", LANG_FR) => "❌ Annuler la mise en veille",
        ("❌ Cancel sleep timer", LANG_ES) => "❌ Cancelar temporizador",
        ("❌ Cancel sleep timer", LANG_DE) => "❌ Schlummermodus abbrechen",
        ("❌ Cancel sleep timer", LANG_PT) => "❌ Cancelar temporizador",

        // --- Périodes astronomiques & Décalage horaire ---
        ("Dawn", LANG_FR) => "Aube",
        ("Dawn", LANG_ES) => "Amanecer",
        ("Dawn", LANG_DE) => "Morgengrauen",
        ("Dawn", LANG_PT) => "Madrugada",

        ("Morning", LANG_FR) => "Matin",
        ("Morning", LANG_ES) => "Mañana",
        ("Morning", LANG_DE) => "Morgen",
        ("Morning", LANG_PT) => "Manhã",

        ("Daytime", LANG_FR) => "Journée",
        ("Daytime", LANG_ES) => "Día",
        ("Daytime", LANG_DE) => "Tag",
        ("Daytime", LANG_PT) => "Dia",

        ("Evening", LANG_FR) => "Soirée",
        ("Evening", LANG_ES) => "Tarde",
        ("Evening", LANG_DE) => "Abend",
        ("Evening", LANG_PT) => "Tarde",

        ("Night", LANG_FR) => "Nuit",
        ("Night", LANG_ES) => "Noche",
        ("Night", LANG_DE) => "Nacht",
        ("Night", LANG_PT) => "Noite",

        ("Tomorrow", LANG_FR) => "Demain",
        ("Tomorrow", LANG_ES) => "Mañana",
        ("Tomorrow", LANG_DE) => "Morgen",
        ("Tomorrow", LANG_PT) => "Amanhã",

        ("Yesterday", LANG_FR) => "Hier",
        ("Yesterday", LANG_ES) => "Ayer",
        ("Yesterday", LANG_DE) => "Gestern",
        ("Yesterday", LANG_PT) => "Ontem",

        ("Today", LANG_FR) => "Aujourd'hui",
        ("Today", LANG_ES) => "Hoy",
        ("Today", LANG_DE) => "Heute",
        ("Today", LANG_PT) => "Hoje",

        ("Same time", LANG_FR) => "Même heure",
        ("Same time", LANG_ES) => "Misma hora",
        ("Same time", LANG_DE) => "Gleiche Zeit",
        ("Same time", LANG_PT) => "Mesma hora",

        _ => msg,
    }
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
    match CURRENT_LANG.load(Ordering::SeqCst) {
        LANG_FR => format!("⭐ Sauvegarder « {} » dans mes favoris...", station_name),
        LANG_ES => format!("⭐ Guardar « {} » en favoritos...", station_name),
        LANG_DE => format!("⭐ « {} » in Favoriten speichern...", station_name),
        LANG_PT => format!("⭐ Guardar « {} » nos favoritos...", station_name),
        _ => format!("⭐ Save « {} » to favorites...", station_name),
    }
}

/// Libellé pour le minuteur de veille actif
pub fn sleep_timer_active_label(remaining_mins: u64) -> String {
    match CURRENT_LANG.load(Ordering::SeqCst) {
        LANG_FR => format!("💤 Veille active (arrêt dans ~{} min)", remaining_mins),
        LANG_ES => format!("💤 Temporizador activo (apagado en ~{} min)", remaining_mins),
        LANG_DE => format!("💤 Timer aktiv (Stopp in ~{} Min.)", remaining_mins),
        LANG_PT => format!("💤 Temporizador ativo (parar em ~{} min)", remaining_mins),
        _ => format!("💤 Active timer (stop in ~{} min)", remaining_mins),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_multilingual_support() {
        set_language("en");
        assert_eq!(tr("▶ Play"), "▶ Play");
        assert_eq!(tr("⏹ Stop"), "⏹ Stop");
        assert_eq!(play_station_label("FIP"), "▶ Play    « FIP »");

        set_language("fr");
        assert_eq!(tr("▶ Play"), "▶ Écouter");
        assert_eq!(tr("⏹ Stop"), "⏹ Éteindre");
        assert_eq!(play_station_label("FIP"), "▶ Écouter    « FIP »");

        set_language("es");
        assert_eq!(tr("▶ Play"), "▶ Reproducir");
        assert_eq!(tr("⏹ Stop"), "⏹ Detener");

        set_language("de");
        assert_eq!(tr("▶ Play"), "▶ Abspielen");
        assert_eq!(tr("⏹ Stop"), "⏹ Anhalten");

        set_language("pt");
        assert_eq!(tr("▶ Play"), "▶ Reproduzir");
        assert_eq!(tr("⏹ Stop"), "⏹ Parar");

        // Rétablir la langue par défaut (français)
        set_language("fr");
    }
}
