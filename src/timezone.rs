//! Gestion des fuseaux horaires, calcul de l'heure locale et inférence multi-fuseaux
//! Timezone management, local time calculation and multi-timezone inference for TiMonde
//
// Ce module permet de convertir un code pays ISO (ex: "FR", "JP", "SN", "CA", "US", "AU")
// ou une sous-région/province (ex: "CA-NB", "US-CA", "America/Moncton") en heure locale exacte
// avec son fuseau IANA réel et sa période de la journée.

use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

/// Informations complètes sur l'heure locale d'un pays ou d'une région
#[derive(Debug, Clone, PartialEq)]
pub struct CountryTimeInfo {
    pub country_code: String,
    pub country_name: String,
    pub flag: String,
    pub timezone: String,
    pub hour: u32,
    pub minute: u32,
    pub formatted_time: String,
    pub icon: &'static str,
    pub period_label: &'static str,
    pub offset_hours: f32,
    pub user_diff_hours: i32,
    pub user_diff_label: String,
    pub day_diff: i32,
    pub day_diff_label: &'static str,
}

impl CountryTimeInfo {
    /// Badge synthétique combinant la ligne de changement de date et le décalage (ex: "Demain, +11h" ou "-5h")
    pub fn relative_badge(&self) -> String {
        if !self.day_diff_label.is_empty() {
            format!("{}, {}", self.day_diff_label, self.user_diff_label)
        } else {
            self.user_diff_label.clone()
        }
    }
}

/// Base statique de référence pour les pays : (Code ISO, Nom FR, Drapeau, Timezone IANA par défaut, Offset standard de secours)
const COUNTRY_REGISTRY: &[(&str, &str, &str, &str, i32)] = &[
    ("AD", "Andorre", "", "Europe/Andorra", 3600),
    ("AE", "Émirats Arabes Unis", "", "Asia/Dubai", 14400),
    ("AL", "Albanie", "", "Europe/Tirane", 3600),
    ("AM", "Arménie", "", "Asia/Yerevan", 14400),
    ("AO", "Angola", "", "Africa/Luanda", 3600),
    ("AR", "Argentine", "", "America/Argentina/Buenos_Aires", -10800),
    ("AT", "Autriche", "", "Europe/Vienna", 3600),
    ("AU", "Australie", "", "Australia/Sydney", 36000),
    ("AZ", "Azerbaïdjan", "", "Asia/Baku", 14400),
    ("BA", "Bosnie-Herzégovine", "", "Europe/Sarajevo", 3600),
    ("BD", "Bangladesh", "", "Asia/Dhaka", 21600),
    ("BE", "Belgique", "", "Europe/Brussels", 3600),
    ("BF", "Burkina Faso", "", "Africa/Ouagadougou", 0),
    ("BG", "Bulgarie", "", "Europe/Sofia", 7200),
    ("BI", "Burundi", "", "Africa/Bujumbura", 7200),
    ("BJ", "Bénin", "", "Africa/Porto-Novo", 3600),
    ("BL", "Saint-Barthélemy", "", "America/St_Barthelemy", -14400),
    ("BN", "Brunei", "", "Asia/Brunei", 28800),
    ("BO", "Bolivie", "", "America/La_Paz", -14400),
    ("BR", "Brésil", "", "America/Sao_Paulo", -10800),
    ("CA", "Canada", "", "America/Toronto", -18000),
    ("CD", "RD Congo", "", "Africa/Kinshasa", 3600),
    ("CG", "Congo", "", "Africa/Brazzaville", 3600),
    ("CH", "Suisse", "", "Europe/Zurich", 3600),
    ("CI", "Côte d'Ivoire", "", "Africa/Abidjan", 0),
    ("CL", "Chili", "", "America/Santiago", -14400),
    ("CM", "Cameroun", "", "Africa/Douala", 3600),
    ("CN", "Chine", "", "Asia/Shanghai", 28800),
    ("CO", "Colombie", "", "America/Bogota", -18000),
    ("CR", "Costa Rica", "", "America/Costa_Rica", -21600),
    ("CU", "Cuba", "", "America/Havana", -18000),
    ("CV", "Cap-Vert", "", "Atlantic/Cape_Verde", -3600),
    ("CY", "Chypre", "", "Asia/Nicosia", 7200),
    ("CZ", "Tchéquie", "", "Europe/Prague", 3600),
    ("DE", "Allemagne", "", "Europe/Berlin", 3600),
    ("DJ", "Djibouti", "", "Africa/Djibouti", 10800),
    ("DK", "Danemark", "", "Europe/Copenhagen", 3600),
    ("DO", "Rép. Dominicaine", "", "America/Santo_Domingo", -14400),
    ("DZ", "Algérie", "", "Africa/Algiers", 3600),
    ("EC", "Équateur", "", "America/Guayaquil", -18000),
    ("EE", "Estonie", "", "Europe/Tallinn", 7200),
    ("EG", "Égypte", "", "Africa/Cairo", 7200),
    ("ES", "Espagne", "", "Europe/Madrid", 3600),
    ("ET", "Éthiopie", "", "Africa/Addis_Ababa", 10800),
    ("FI", "Finlande", "", "Europe/Helsinki", 7200),
    ("FJ", "Fidji", "", "Pacific/Fiji", 43200),
    ("FR", "France", "", "Europe/Paris", 3600),
    ("GA", "Gabon", "", "Africa/Libreville", 3600),
    ("GB", "Royaume-Uni", "", "Europe/London", 0),
    ("GE", "Géorgie", "", "Asia/Tbilisi", 14400),
    ("GF", "Guyane", "", "America/Cayenne", -10800),
    ("GH", "Ghana", "", "Africa/Accra", 0),
    ("GN", "Guinée", "", "Africa/Conakry", 0),
    ("GP", "Guadeloupe", "", "America/Guadeloupe", -14400),
    ("GR", "Grèce", "", "Europe/Athens", 7200),
    ("GT", "Guatemala", "", "America/Guatemala", -21600),
    ("HK", "Hong Kong", "", "Asia/Hong_Kong", 28800),
    ("HN", "Honduras", "", "America/Tegucigalpa", -21600),
    ("HR", "Croatie", "", "Europe/Zagreb", 3600),
    ("HT", "Haïti", "", "America/Port-au-Prince", -18000),
    ("HU", "Hongrie", "", "Europe/Budapest", 3600),
    ("ID", "Indonésie", "", "Asia/Jakarta", 25200),
    ("IE", "Irlande", "", "Europe/Dublin", 0),
    ("IL", "Israël", "", "Asia/Jerusalem", 7200),
    ("IN", "Inde", "", "Asia/Kolkata", 19800),
    ("IS", "Islande", "", "Atlantic/Reykjavik", 0),
    ("IT", "Italie", "", "Europe/Rome", 3600),
    ("JM", "Jamaïque", "", "America/Jamaica", -18000),
    ("JO", "Jordanie", "", "Asia/Amman", 10800),
    ("JP", "Japon", "", "Asia/Tokyo", 32400),
    ("KE", "Kenya", "", "Africa/Nairobi", 10800),
    ("KG", "Kirghizistan", "", "Asia/Bishkek", 21600),
    ("KH", "Cambodge", "", "Asia/Phnom_Penh", 25200),
    ("KR", "Corée du Sud", "", "Asia/Seoul", 32400),
    ("KZ", "Kazakhstan", "", "Asia/Almaty", 18000),
    ("LA", "Laos", "", "Asia/Vientiane", 25200),
    ("LB", "Liban", "", "Asia/Beirut", 7200),
    ("LI", "Liechtenstein", "", "Europe/Vaduz", 3600),
    ("LK", "Sri Lanka", "", "Asia/Colombo", 19800),
    ("LT", "Lituanie", "", "Europe/Vilnius", 7200),
    ("LU", "Luxembourg", "", "Europe/Luxembourg", 3600),
    ("LV", "Lettonie", "", "Europe/Riga", 7200),
    ("MA", "Maroc", "", "Africa/Casablanca", 3600),
    ("MC", "Monaco", "", "Europe/Monaco", 3600),
    ("MD", "Moldavie", "", "Europe/Chisinau", 7200),
    ("ME", "Monténégro", "", "Europe/Podgorica", 3600),
    ("MF", "Saint-Martin", "", "America/Marigot", -14400),
    ("MG", "Madagascar", "", "Indian/Antananarivo", 10800),
    ("MK", "Macédoine du Nord", "", "Europe/Skopje", 3600),
    ("ML", "Mali", "", "Africa/Bamako", 0),
    ("MM", "Birmanie", "", "Asia/Yangon", 23400),
    ("MN", "Mongolie", "", "Asia/Ulaanbaatar", 28800),
    ("MQ", "Martinique", "", "America/Martinique", -14400),
    ("MR", "Mauritanie", "", "Africa/Nouakchott", 0),
    ("MT", "Malte", "", "Europe/Malta", 3600),
    ("MU", "Maurice", "", "Indian/Mauritius", 14400),
    ("MX", "Mexique", "", "America/Mexico_City", -21600),
    ("MY", "Malaisie", "", "Asia/Kuala_Lumpur", 28800),
    ("MZ", "Mozambique", "", "Africa/Maputo", 7200),
    ("NA", "Namibie", "", "Africa/Windhoek", 7200),
    ("NC", "Nouvelle-Calédonie", "", "Pacific/Noumea", 39600),
    ("NE", "Niger", "", "Africa/Niamey", 3600),
    ("NG", "Nigéria", "", "Africa/Lagos", 3600),
    ("NI", "Nicaragua", "", "America/Managua", -21600),
    ("NL", "Pays-Bas", "", "Europe/Amsterdam", 3600),
    ("NO", "Norvège", "", "Europe/Oslo", 3600),
    ("NP", "Népal", "", "Asia/Kathmandu", 20700),
    ("NZ", "Nouvelle-Zélande", "", "Pacific/Auckland", 43200),
    ("PA", "Panama", "", "America/Panama", -18000),
    ("PE", "Pérou", "", "America/Lima", -18000),
    ("PF", "Polynésie française", "", "Pacific/Tahiti", -36000),
    ("PG", "Papouasie-Nouvelle-Guinée", "", "Pacific/Port_Moresby", 36000),
    ("PH", "Philippines", "", "Asia/Manila", 28800),
    ("PK", "Pakistan", "", "Asia/Karachi", 18000),
    ("PL", "Pologne", "", "Europe/Warsaw", 3600),
    ("PM", "Saint-Pierre-et-Miquelon", "", "America/Miquelon", -10800),
    ("PR", "Porto Rico", "", "America/Puerto_Rico", -14400),
    ("PT", "Portugal", "", "Europe/Lisbon", 0),
    ("PY", "Paraguay", "", "America/Asuncion", -14400),
    ("RE", "La Réunion", "", "Indian/Reunion", 14400),
    ("RO", "Roumanie", "", "Europe/Bucharest", 7200),
    ("RS", "Serbie", "", "Europe/Belgrade", 3600),
    ("RU", "Russie", "", "Europe/Moscow", 10800),
    ("RW", "Rwanda", "", "Africa/Kigali", 7200),
    ("SA", "Arabie Saoudite", "", "Asia/Riyadh", 10800),
    ("SC", "Seychelles", "", "Indian/Mahe", 14400),
    ("SE", "Suède", "", "Europe/Stockholm", 3600),
    ("SG", "Singapour", "", "Asia/Singapore", 28800),
    ("SI", "Slovénie", "", "Europe/Ljubljana", 3600),
    ("SK", "Slovaquie", "", "Europe/Bratislava", 3600),
    ("SM", "Saint-Marin", "", "Europe/San_Marino", 3600),
    ("SN", "Sénégal", "", "Africa/Dakar", 0),
    ("SV", "Salvador", "", "America/El_Salvador", -21600),
    ("TD", "Tchad", "", "Africa/Ndjamena", 3600),
    ("TG", "Togo", "", "Africa/Lome", 0),
    ("TH", "Thaïlande", "", "Asia/Bangkok", 25200),
    ("TJ", "Tadjikistan", "", "Asia/Dushanbe", 18000),
    ("TN", "Tunisie", "", "Africa/Tunis", 3600),
    ("TR", "Turquie", "", "Europe/Istanbul", 10800),
    ("TT", "Trinité-et-Tobago", "", "America/Port_of_Spain", -14400),
    ("TW", "Taïwan", "", "Asia/Taipei", 28800),
    ("TZ", "Tanzanie", "", "Africa/Dar_es_Salaam", 10800),
    ("UA", "Ukraine", "", "Europe/Kyiv", 7200),
    ("UG", "Ouganda", "", "Africa/Kampala", 10800),
    ("UK", "Royaume-Uni", "", "Europe/London", 0),
    ("US", "États-Unis", "", "America/New_York", -18000),
    ("UY", "Uruguay", "", "America/Montevideo", -10800),
    ("UZ", "Ouzbékistan", "", "Asia/Tashkent", 18000),
    ("VA", "Vatican", "", "Europe/Vatican", 3600),
    ("VE", "Venezuela", "", "America/Caracas", -14400),
    ("VN", "Viêt Nam", "", "Asia/Ho_Chi_Minh", 25200),
    ("WF", "Wallis-et-Futuna", "", "Pacific/Wallis", 43200),
    ("XK", "Kosovo", "", "Europe/Belgrade", 3600),
    ("YT", "Mayotte", "", "Indian/Mayotte", 10800),
    ("ZA", "Afrique du Sud", "", "Africa/Johannesburg", 7200),
    ("ZM", "Zambie", "", "Africa/Lusaka", 7200),
    ("ZW", "Zimbabwe", "", "Africa/Harare", 7200),
];

/// Résout le fuseau horaire précis pour le Canada (6 fuseaux horaires)
fn resolve_canada_timezone(text: &str) -> (&'static str, &'static str, i32) {
    let lower = text.to_lowercase();
    if lower.contains("acadie")
        || lower.contains("acadien")
        || lower.contains("moncton")
        || lower.contains("halifax")
        || lower.contains("nouveau-brunswick")
        || lower.contains("nouvelle-écosse")
        || lower.contains("nouvelle-ecosse")
        || lower.contains("atlantique")
        || lower.contains("choy")
        || lower.contains("ckma")
        || lower.contains("ca-nb")
        || lower.contains("ca-ns")
        || lower.contains("ca-pe")
    {
        ("Canada (Atlantique)", "America/Moncton", -14400)
    } else if lower.contains("terre-neuve")
        || lower.contains("newfoundland")
        || lower.contains("st. john")
        || lower.contains("saint-jean")
        || lower.contains("ca-nl")
    {
        ("Canada (Terre-Neuve)", "America/St_Johns", -12600)
    } else if lower.contains("vancouver")
        || lower.contains("victoria")
        || lower.contains("colombie-britannique")
        || lower.contains("pacifique")
        || lower.contains("ca-bc")
        || lower.contains("ca-yt")
    {
        ("Canada (Pacifique)", "America/Vancouver", -28800)
    } else if lower.contains("calgary")
        || lower.contains("edmonton")
        || lower.contains("alberta")
        || lower.contains("rocheuses")
        || lower.contains("ca-ab")
        || lower.contains("ca-nt")
    {
        ("Canada (Rocheuses)", "America/Edmonton", -25200)
    } else if lower.contains("winnipeg")
        || lower.contains("manitoba")
        || lower.contains("saskatchewan")
        || lower.contains("regina")
        || lower.contains("ca-mb")
        || lower.contains("ca-sk")
    {
        ("Canada (Centre)", "America/Winnipeg", -21600)
    } else {
        ("Canada (Est)", "America/Toronto", -18000)
    }
}

/// Résout le fuseau horaire précis pour les États-Unis (6 fuseaux horaires)
fn resolve_usa_timezone(text: &str) -> (&'static str, &'static str, i32) {
    let lower = text.to_lowercase();
    if lower.contains("los angeles")
        || lower.contains("san francisco")
        || lower.contains("california")
        || lower.contains("seattle")
        || lower.contains("pacific")
        || lower.contains("hollywood")
        || lower.contains("us-ca")
        || lower.contains("us-wa")
        || lower.contains("us-or")
        || lower.contains("us-nv")
    {
        ("États-Unis (Pacifique)", "America/Los_Angeles", -28800)
    } else if lower.contains("chicago")
        || lower.contains("texas")
        || lower.contains("dallas")
        || lower.contains("houston")
        || lower.contains("austin")
        || lower.contains("central")
        || lower.contains("louisiana")
        || lower.contains("new orleans")
        || lower.contains("us-tx")
        || lower.contains("us-il")
    {
        ("États-Unis (Centre)", "America/Chicago", -21600)
    } else if lower.contains("denver")
        || lower.contains("colorado")
        || lower.contains("phoenix")
        || lower.contains("arizona")
        || lower.contains("mountain")
        || lower.contains("us-co")
        || lower.contains("us-az")
        || lower.contains("us-ut")
    {
        ("États-Unis (Montagnes)", "America/Denver", -25200)
    } else if lower.contains("alaska") || lower.contains("anchorage") || lower.contains("us-ak") {
        ("États-Unis (Alaska)", "America/Anchorage", -32400)
    } else if lower.contains("hawaii") || lower.contains("honolulu") || lower.contains("us-hi") {
        ("États-Unis (Hawaï)", "Pacific/Honolulu", -36000)
    } else {
        ("États-Unis (Est)", "America/New_York", -18000)
    }
}

/// Résout le fuseau horaire précis pour l'Australie (3 à 5 fuseaux horaires)
fn resolve_australia_timezone(text: &str) -> (&'static str, &'static str, i32) {
    let lower = text.to_lowercase();
    if lower.contains("perth") || lower.contains("western") || lower.contains("au-wa") {
        ("Australie (Ouest)", "Australia/Perth", 28800)
    } else if lower.contains("adelaide") || lower.contains("darwin") || lower.contains("au-sa") || lower.contains("au-nt") {
        ("Australie (Centre)", "Australia/Adelaide", 34200)
    } else {
        ("Australie (Est)", "Australia/Sydney", 36000)
    }
}

/// Résout les métadonnées de fuseau pour un identifiant IANA explicite (ex: Outre-mer, multi-fuseaux US/CA)
fn resolve_explicit_timezone_meta(
    tz: &str,
    country_code: Option<&str>,
) -> Option<(&'static str, &'static str, i32)> {
    match tz {
        "America/Guadeloupe" => Some(("Guadeloupe", "", -14400)),
        "America/Martinique" => Some(("Martinique", "", -14400)),
        "America/Cayenne" => Some(("Guyane", "", -10800)),
        "Indian/Reunion" => Some(("La Réunion", "", 14400)),
        "Indian/Mayotte" => Some(("Mayotte", "", 10800)),
        "America/Miquelon" => Some(("Saint-Pierre-et-Miquelon", "", -10800)),
        "America/St_Barthelemy" => Some(("Saint-Barthélemy", "", -14400)),
        "America/Marigot" => Some(("Saint-Martin", "", -14400)),
        "Pacific/Noumea" => Some(("Nouvelle-Calédonie", "", 39600)),
        "Pacific/Tahiti" => Some(("Polynésie française", "", -36000)),
        "Pacific/Marquesas" => Some(("Polynésie (Marquises)", "", -34200)),
        "Pacific/Gambier" => Some(("Polynésie (Gambier)", "", -32400)),
        "Pacific/Wallis" => Some(("Wallis-et-Futuna", "", 43200)),
        "Europe/Paris" => Some(("France", "", 3600)),
        "America/Moncton" | "America/Halifax" => Some(("Canada (Atlantique)", "", -14400)),
        "America/St_Johns" => Some(("Canada (Terre-Neuve)", "", -12600)),
        "America/Toronto" => Some(("Canada (Est)", "", -18000)),
        "America/Winnipeg" | "America/Regina" => Some(("Canada (Centre)", "", -21600)),
        "America/Edmonton" => Some(("Canada (Rocheuses)", "", -25200)),
        "America/Vancouver" => Some(("Canada (Pacifique)", "", -28800)),
        "America/New_York" | "America/Detroit" => Some(("États-Unis (Est)", "", -18000)),
        "America/Chicago" => Some(("États-Unis (Centre)", "", -21600)),
        "America/Denver" => Some(("États-Unis (Montagnes)", "", -25200)),
        "America/Phoenix" => Some(("États-Unis (Arizona)", "", -25200)),
        "America/Los_Angeles" => Some(("États-Unis (Pacifique)", "", -28800)),
        "America/Anchorage" => Some(("États-Unis (Alaska)", "", -32400)),
        "Pacific/Honolulu" => Some(("États-Unis (Hawaï)", "", -36000)),
        "Europe/Madrid" => Some(("Espagne", "", 3600)),
        "Atlantic/Canary" => Some(("Espagne (Canaries)", "", 0)),
        "Europe/Lisbon" => Some(("Portugal", "", 0)),
        "Atlantic/Azores" => Some(("Portugal (Açores)", "", -3600)),
        "Australia/Sydney" | "Australia/Brisbane" => Some(("Australie (Est)", "", 36000)),
        "Australia/Adelaide" | "Australia/Darwin" => Some(("Australie (Centre)", "", 34200)),
        "Australia/Perth" => Some(("Australie (Ouest)", "", 28800)),
        "America/Sao_Paulo" => Some(("Brésil", "", -10800)),
        "America/Manaus" => Some(("Brésil (Amazonie)", "", -14400)),
        "Europe/Moscow" => Some(("Russie (Moscou)", "", 10800)),
        _ => {
            if let Some(c) = country_code {
                if let Some(entry) = lookup_country_meta(c) {
                    return Some((entry.0, entry.1, entry.3));
                }
            }
            None
        }
    }
}

/// Résout intelligemment les métadonnées de fuseau d'une station à partir de son étiquette, son nom, son groupe et son fuseau explicite
pub fn resolve_station_meta(
    country_code: Option<&str>,
    station_name: &str,
    group_name: Option<&str>,
    explicit_tz: Option<&str>,
) -> Option<(&'static str, &'static str, String, i32)> {
    // 0. Si un fuseau horaire IANA explicite est fourni, il est toujours prioritaire
    if let Some(tz) = explicit_tz.map(|s| s.trim()).filter(|s| !s.is_empty()) {
        if let Some((name, flag, def_off)) = resolve_explicit_timezone_meta(tz, country_code) {
            return Some((name, flag, tz.to_string(), def_off));
        }
        // Fallback pour fuseau IANA personnalisé non répertorié
        if let Some(c) = country_code {
            if let Some(entry) = lookup_country_meta(c) {
                return Some((entry.0, entry.1, tz.to_string(), entry.3));
            }
        }
        return Some(("Monde", "", tz.to_string(), 0));
    }
    let raw_country = country_code.unwrap_or("").trim();
    let combined_context = format!("{} {} {}", raw_country, station_name, group_name.unwrap_or(""));

    // 1. Détection prioritaire par code explicite ou inférence contextuelle
    let upper = raw_country.to_ascii_uppercase();

    if upper == "CA" || (upper.is_empty() && (combined_context.to_lowercase().contains("canada") || combined_context.to_lowercase().contains("acadie"))) {
        let (name, tz, off) = resolve_canada_timezone(&combined_context);
        return Some((name, "", tz.to_string(), off));
    }

    if upper == "US"
        || (upper.is_empty()
            && (combined_context.to_lowercase().contains("usa")
                || combined_context.to_lowercase().contains("united states")
                || combined_context.to_lowercase().contains("bluegrass")
                || combined_context.to_lowercase().contains("nashville")))
    {
        let (name, tz, off) = resolve_usa_timezone(&combined_context);
        return Some((name, "", tz.to_string(), off));
    }

    if upper == "AU" || (upper.is_empty() && combined_context.to_lowercase().contains("australia")) {
        let (name, tz, off) = resolve_australia_timezone(&combined_context);
        return Some((name, "", tz.to_string(), off));
    }

    // Détection Outre-Mer / Antilles / Caraïbes
    let lower_context = combined_context.to_lowercase();
    if upper == "GP"
        || lower_context.contains("guadeloupe")
        || lower_context.contains("transat")
        || lower_context.contains("pointe-à-pitre")
        || lower_context.contains("pointe a pitre")
        || lower_context.contains("basse-terre")
    {
        return Some(("Guadeloupe", "", "America/Guadeloupe".to_string(), -14400));
    }
    if upper == "MQ" || lower_context.contains("martinique") || lower_context.contains("fort-de-france") {
        return Some(("Martinique", "", "America/Martinique".to_string(), -14400));
    }
    if upper == "GF" || lower_context.contains("guyane") || lower_context.contains("cayenne") {
        return Some(("Guyane", "", "America/Cayenne".to_string(), -10800));
    }
    if upper == "RE" || lower_context.contains("la réunion") || lower_context.contains("la reunion") || lower_context.contains("saint-denis") {
        return Some(("La Réunion", "", "Indian/Reunion".to_string(), 14400));
    }
    if upper == "YT" || lower_context.contains("mayotte") || lower_context.contains("mamoudzou") {
        return Some(("Mayotte", "", "Indian/Mayotte".to_string(), 10800));
    }
    if upper == "NC" || lower_context.contains("nouvelle-calédonie") || lower_context.contains("nouvelle-caledonie") || lower_context.contains("nouméa") || lower_context.contains("noumea") {
        return Some(("Nouvelle-Calédonie", "", "Pacific/Noumea".to_string(), 39600));
    }
    if upper == "PF" || lower_context.contains("polynésie") || lower_context.contains("polynesie") || lower_context.contains("tahiti") || lower_context.contains("papeete") {
        return Some(("Polynésie française", "", "Pacific/Tahiti".to_string(), -36000));
    }
    if upper == "BL" || lower_context.contains("saint-barthélemy") || lower_context.contains("saint-barthelemy") || lower_context.contains("gustavia") {
        return Some(("Saint-Barthélemy", "", "America/St_Barthelemy".to_string(), -14400));
    }
    if upper == "MF" || lower_context.contains("saint-martin") || lower_context.contains("marigot") {
        return Some(("Saint-Martin", "", "America/Marigot".to_string(), -14400));
    }

    // 2. Recherche directe dans le registre mondial
    if !raw_country.is_empty() {
        if let Some(entry) = lookup_country_meta(raw_country) {
            return Some((entry.0, entry.1, entry.2.to_string(), entry.3));
        }
    }

    // 3. Inférence contextuelle d'autres pays si le pays n'est pas encore étiqueté
    let lower_context = combined_context.to_lowercase();
    for entry in COUNTRY_REGISTRY {
        let c_lower = entry.1.to_lowercase();
        if lower_context.contains(&c_lower) {
            return Some((entry.1, entry.2, entry.3.to_string(), entry.4));
        }
    }

    None
}

/// Retourne les informations statiques d'un pays à partir de son code ISO (insensible à la casse)
pub fn lookup_country_meta(country_code: &str) -> Option<(&'static str, &'static str, &'static str, i32)> {
    let clean = country_code.trim();
    for entry in COUNTRY_REGISTRY {
        if entry.0.eq_ignore_ascii_case(clean) {
            return Some((entry.1, entry.2, entry.3, entry.4));
        }
    }
    None
}

/// Détermine l'icône astronomique et la période de la journée selon l'heure locale
pub fn get_astronomical_period(hour: u32) -> (&'static str, &'static str) {
    match hour {
        6..=8 => ("", "Morning"),
        9..=17 => ("", "Daytime"),
        18..=21 => ("", "Evening"),
        _ => ("", "Night"),
    }
}

/// Lit directement le décalage UTC actuel en secondes depuis le fichier zoneinfo du système Linux (/usr/share/zoneinfo/...)
/// Reads current UTC offset in seconds from standard Linux zoneinfo binary file
/// Lit le décalage UTC actuel de la machine locale de l'auditeur (en secondes)
pub fn get_local_machine_offset_seconds(now_epoch: i64) -> i32 {
    if let Some(off) = parse_tzif_offset_file("/etc/localtime", now_epoch) {
        return off;
    }
    unsafe {
        let t: libc::time_t = now_epoch;
        let mut tm: libc::tm = std::mem::zeroed();
        if !libc::localtime_r(&t, &mut tm).is_null() {
            return tm.tm_gmtoff as i32;
        }
    }
    0
}

fn parse_tzif_offset(tz_name: &str, now_epoch: i64) -> Option<i32> {
    let path_str = format!("/usr/share/zoneinfo/{}", tz_name);
    parse_tzif_offset_file(&path_str, now_epoch)
}

fn parse_tzif_offset_file(path_str: &str, now_epoch: i64) -> Option<i32> {
    let path = Path::new(&path_str);
    if !path.exists() {
        return None;
    }

    let mut file = File::open(path).ok()?;
    let mut data = Vec::new();
    file.read_to_end(&mut data).ok()?;

    if data.len() < 44 || &data[..4] != b"TZif" {
        return None;
    }

    let mut offset = 0;
    let mut is_64 = false;
    if let Some(pos) = data[1..].windows(5).position(|w| w == b"TZif2" || w == b"TZif3") {
        offset = pos + 1;
        is_64 = true;
    }

    if data.len() < offset + 44 {
        return None;
    }

    let header = &data[offset..offset + 44];
    let timecnt = u32::from_be_bytes([header[32], header[33], header[34], header[35]]) as usize;
    let typecnt = u32::from_be_bytes([header[36], header[37], header[38], header[39]]) as usize;

    let mut pos = offset + 44;
    let time_size = if is_64 { 8 } else { 4 };

    if data.len() < pos + timecnt * time_size + timecnt + typecnt * 6 {
        return None;
    }

    let mut transitions = Vec::with_capacity(timecnt);
    for _ in 0..timecnt {
        let t = if is_64 {
            i64::from_be_bytes(data[pos..pos + 8].try_into().ok()?)
        } else {
            i32::from_be_bytes(data[pos..pos + 4].try_into().ok()?) as i64
        };
        transitions.push(t);
        pos += time_size;
    }

    let time_types = &data[pos..pos + timecnt];
    pos += timecnt;

    let mut utoffs = Vec::with_capacity(typecnt);
    for _ in 0..typecnt {
        let utoff = i32::from_be_bytes(data[pos..pos + 4].try_into().ok()?);
        utoffs.push(utoff);
        pos += 6;
    }

    let mut active_type_idx = 0usize;
    for (i, &t) in transitions.iter().enumerate() {
        if t <= now_epoch {
            if let Some(&type_idx) = time_types.get(i) {
                active_type_idx = type_idx as usize;
            }
        } else {
            break;
        }
    }

    utoffs.get(active_type_idx).copied()
}

/// Calcule l'heure locale et les attributs associés pour un code pays simple
pub fn get_local_time_for_country(country_code: &str) -> Option<CountryTimeInfo> {
    get_local_time_for_station(Some(country_code), "", None, None)
}

/// Calcule l'heure locale exacte d'une station avec résolution multi-fuseaux contextuelle ou fuseau explicite
pub fn get_local_time_for_station(
    country_code: Option<&str>,
    station_name: &str,
    group_name: Option<&str>,
    explicit_tz: Option<&str>,
) -> Option<CountryTimeInfo> {
    let (c_name, c_flag, tz_name, default_offset) =
        resolve_station_meta(country_code, station_name, group_name, explicit_tz)?;

    let now_system = SystemTime::now().duration_since(UNIX_EPOCH).ok()?;
    let now_epoch = now_system.as_secs() as i64;

    let offset_seconds = parse_tzif_offset(&tz_name, now_epoch).unwrap_or(default_offset);

    let local_epoch = now_epoch + offset_seconds as i64;
    let seconds_in_day = (local_epoch.rem_euclid(86400)) as u32;

    let hour = seconds_in_day / 3600;
    let minute = (seconds_in_day % 3600) / 60;
    let formatted_time = format!("{:02}:{:02}", hour, minute);
    let (icon, raw_period) = get_astronomical_period(hour);
    let period_label = crate::i18n::tr(raw_period);
    let offset_hours = (offset_seconds as f32) / 3600.0;

    let code = country_code.unwrap_or("").trim().to_ascii_uppercase();

    let user_machine_offset = get_local_machine_offset_seconds(now_epoch);
    let diff_seconds = offset_seconds - user_machine_offset;
    let user_diff_hours = (diff_seconds as f32 / 3600.0).round() as i32;
    let user_diff_label = if user_diff_hours == 0 {
        crate::i18n::tr("Same time").to_string()
    } else if user_diff_hours > 0 {
        format!("+{}h", user_diff_hours)
    } else {
        format!("{}h", user_diff_hours)
    };

    // Calcul de la ligne de changement de date (International Date Line : J+1 Demain / J-1 Hier)
    let station_day_number = local_epoch.div_euclid(86400);
    let user_day_number = (now_epoch + user_machine_offset as i64).div_euclid(86400);
    let day_diff = (station_day_number - user_day_number) as i32;
    let day_diff_label = match day_diff {
        1 => crate::i18n::tr("Tomorrow"),
        -1 => crate::i18n::tr("Yesterday"),
        d if d > 1 => "+jours",
        d if d < -1 => "-jours",
        _ => "",
    };

    Some(CountryTimeInfo {
        country_code: if code.is_empty() { tz_name.to_string() } else { code },
        country_name: c_name.to_string(),
        flag: c_flag.to_string(),
        timezone: tz_name.to_string(),
        hour,
        minute,
        formatted_time,
        icon,
        period_label,
        offset_hours,
        user_diff_hours,
        user_diff_label,
        day_diff,
        day_diff_label,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_lookup_country_meta() {
        let meta_fr = lookup_country_meta("FR").unwrap();
        assert_eq!(meta_fr.0, "France");
        assert_eq!(meta_fr.1, "");
        assert_eq!(meta_fr.2, "Europe/Paris");

        let meta_jp = lookup_country_meta("jp").unwrap();
        assert_eq!(meta_jp.0, "Japon");
        assert_eq!(meta_jp.1, "");
        assert_eq!(meta_jp.2, "Asia/Tokyo");
    }

    #[test]
    fn test_canada_multi_timezone_inference() {
        // Test spécifique de la station Acadienne de l'utilisateur
        let info_acadie = get_local_time_for_station(
            Some("CA"),
            ", CHOY Fm 99.9 L'Acadie Country",
            Some("Canada"),
            None,
        )
        .unwrap();
        assert_eq!(info_acadie.country_name, "Canada (Atlantique)");
        assert_eq!(info_acadie.timezone, "America/Moncton");
        assert_eq!(info_acadie.flag, "");

        // Test Vancouver (Pacifique)
        let info_bc = get_local_time_for_station(
            Some("CA"),
            "CFOX 99.3 Vancouver Rock",
            Some("Canada"),
            None,
        )
        .unwrap();
        assert_eq!(info_bc.country_name, "Canada (Pacifique)");
        assert_eq!(info_bc.timezone, "America/Vancouver");

        // Test Montréal / Québec (Est)
        let info_mtl = get_local_time_for_station(
            Some("CA"),
            "98.5 FM Montréal",
            Some("Canada"),
            None,
        )
        .unwrap();
        assert_eq!(info_mtl.country_name, "Canada (Est)");
        assert_eq!(info_mtl.timezone, "America/Toronto");
    }

    #[test]
    fn test_usa_multi_timezone_inference() {
        let info_la = get_local_time_for_station(
            Some("US"),
            "KROQ Los Angeles",
            Some("USA"),
            None,
        )
        .unwrap();
        assert_eq!(info_la.country_name, "États-Unis (Pacifique)");
        assert_eq!(info_la.timezone, "America/Los_Angeles");

        let info_ny = get_local_time_for_station(
            Some("US"),
            "Z100 New York",
            Some("USA"),
            None,
        )
        .unwrap();
        assert_eq!(info_ny.country_name, "États-Unis (Est)");
        assert_eq!(info_ny.timezone, "America/New_York");
    }

    #[test]
    fn test_explicit_timezone_support() {
        // Test France métropolitaine explicite
        let info_paris = get_local_time_for_station(
            Some("FR"),
            "France Inter",
            Some("France"),
            Some("Europe/Paris"),
        ).unwrap();
        assert_eq!(info_paris.country_name, "France");
        assert_eq!(info_paris.flag, "");
        assert_eq!(info_paris.timezone, "Europe/Paris");

        // Test France Outre-mer (Guadeloupe)
        let info_guad = get_local_time_for_station(
            Some("FR"),
            "Radio Transat",
            Some("Antilles"),
            Some("America/Guadeloupe"),
        ).unwrap();
        assert_eq!(info_guad.country_name, "Guadeloupe");
        assert_eq!(info_guad.flag, "");
        assert_eq!(info_guad.timezone, "America/Guadeloupe");

        // Test France Outre-mer (La Réunion)
        let info_run = get_local_time_for_station(
            Some("FR"),
            "Freedom FM",
            Some("Océan Indien"),
            Some("Indian/Reunion"),
        ).unwrap();
        assert_eq!(info_run.country_name, "La Réunion");
        assert_eq!(info_run.flag, "");
        assert_eq!(info_run.timezone, "Indian/Reunion");

        // Test États-Unis Californie explicite
        let info_us_ca = get_local_time_for_station(
            Some("US"),
            "KCRW",
            Some("USA"),
            Some("America/Los_Angeles"),
        ).unwrap();
        assert_eq!(info_us_ca.country_name, "États-Unis (Pacifique)");
        assert_eq!(info_us_ca.timezone, "America/Los_Angeles");
    }

    #[test]
    fn test_astronomical_icons() {
        assert_eq!(get_astronomical_period(7).0, "");
        assert_eq!(get_astronomical_period(14).0, "");
        assert_eq!(get_astronomical_period(20).0, "");
        assert_eq!(get_astronomical_period(23).0, "");
        assert_eq!(get_astronomical_period(3).0, "");
    }

    #[test]
    fn test_radio_transat_guadeloupe_inference() {
        // Test sans code pays avec groupe Guadeloupe
        let info_grp = get_local_time_for_station(None, "Radio Transat", Some("Guadeloupe"), None).unwrap();
        assert_eq!(info_grp.country_name, "Guadeloupe");
        assert_eq!(info_grp.flag, "");
        assert_eq!(info_grp.timezone, "America/Guadeloupe");

        // Test sans code pays et sans groupe via le nom seul
        let info_name = get_local_time_for_station(None, "Radio Transat", None, None).unwrap();
        assert_eq!(info_name.country_name, "Guadeloupe");
        assert_eq!(info_name.flag, "");
    }

    #[test]
    fn test_user_offset_diff_label() {
        let info = get_local_time_for_station(
            Some("CA"),
            ", CHOY Fm 99.9 L'Acadie Country",
            Some("Canada"),
            None,
        ).unwrap();
        assert!(!info.user_diff_label.is_empty());
        assert!(info.user_diff_label.contains('h') || info.user_diff_label == "Même heure");
    }

    #[test]
    fn test_international_date_line_detection() {
        let info_nz = get_local_time_for_station(
            Some("NZ"),
            "RNZ National",
            Some("Nouvelle-Zélande"),
            None,
        ).unwrap();
        assert!(info_nz.day_diff >= 0);
        if info_nz.day_diff == 1 {
            assert!(info_nz.day_diff_label == "Demain" || info_nz.day_diff_label == "Tomorrow");
            assert!(info_nz.relative_badge().starts_with("Demain,") || info_nz.relative_badge().starts_with("Tomorrow,"));
        }
    }
}
