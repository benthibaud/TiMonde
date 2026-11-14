use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

fn timonde_bin() -> &'static str {
    env!("CARGO_BIN_EXE_timonde")
}

fn temp_file(name: &str) -> PathBuf {
    let mut p = std::env::temp_dir();
    p.push(format!("timonde_it_{}_{}", std::process::id(), name));
    p
}

#[test]
fn test_cli_version_matches_cargo() {
    let out = Command::new(timonde_bin())
        .arg("--version")
        .output()
        .expect("Échec exécution timonde --version");
    assert!(out.status.success());
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains(env!("CARGO_PKG_VERSION")),
        "Version attendue {}, obtenu: {}",
        env!("CARGO_PKG_VERSION"),
        stdout
    );
}

#[test]
fn test_cli_dump_countries_and_infer_timezone() {
    let out = Command::new(timonde_bin())
        .arg("--dump-countries-json")
        .output()
        .expect("Échec --dump-countries-json");
    assert!(out.status.success());
    let parsed: serde_json::Value =
        serde_json::from_slice(&out.stdout).expect("JSON invalide pour --dump-countries-json");
    let arr = parsed.as_array().expect("Tableau JSON attendu");
    assert!(arr.len() >= 200, "Trop peu de pays retournés: {}", arr.len());
    assert!(arr.iter().any(|c| c.get("code").and_then(|v| v.as_str()) == Some("FR")));

    let tz_out = Command::new(timonde_bin())
        .args(["--infer-timezone", "FR", "France Inter"])
        .output()
        .expect("Échec --infer-timezone");
    assert!(tz_out.status.success());
    let tz_json: serde_json::Value =
        serde_json::from_slice(&tz_out.stdout).expect("JSON invalide pour --infer-timezone");
    assert_eq!(tz_json["timezone"], "Europe/Paris");
}

#[test]
fn test_cli_bookmarks_json_roundtrip_and_wipe_protection() {
    let xml_path = temp_file("bookmarks.xml");
    let _ = std::fs::remove_file(&xml_path);

    let payload = r#"[
      {
        "name": "France",
        "is_separator": false,
        "stations": [
          {
            "name": "FIP",
            "url": "https://icecast.radiofrance.fr/fip-midfi.mp3",
            "country": "FR",
            "timezone": "Europe/Paris",
            "is_separator": false
          }
        ]
      }
    ]"#;

    // 1. Sauvegarde JSON -> XML via stdin
    let mut child = Command::new(timonde_bin())
        .args(["--save-bookmarks-json", "-", xml_path.to_str().unwrap()])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("Échec spawn --save-bookmarks-json");
    child.stdin.as_mut().unwrap().write_all(payload.as_bytes()).unwrap();
    let save_out = child.wait_with_output().unwrap();
    assert!(
        save_out.status.success(),
        "Sauvegarde échouée: {}",
        String::from_utf8_lossy(&save_out.stderr)
    );

    // 2. Relecture XML -> JSON
    let dump_out = Command::new(timonde_bin())
        .args(["--dump-bookmarks-json", xml_path.to_str().unwrap()])
        .output()
        .expect("Échec --dump-bookmarks-json");
    assert!(dump_out.status.success());
    let dumped: serde_json::Value = serde_json::from_slice(&dump_out.stdout).unwrap();
    let groups = dumped.as_array().unwrap();
    assert_eq!(groups.len(), 1);
    assert_eq!(groups[0]["name"], "France");
    assert_eq!(groups[0]["stations"][0]["name"], "FIP");

    // 3. Protection anti-écrasement par liste vide []
    let mut wipe_child = Command::new(timonde_bin())
        .args(["--save-bookmarks-json", "-", xml_path.to_str().unwrap()])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    wipe_child.stdin.as_mut().unwrap().write_all(b"[]").unwrap();
    let wipe_out = wipe_child.wait_with_output().unwrap();
    assert!(
        !wipe_out.status.success(),
        "L'écrasement d'un bookmarks.xml non vide par [] aurait dû être refusé !"
    );

    let _ = std::fs::remove_file(&xml_path);
}

#[test]
fn test_cli_parse_file_json_m3u() {
    let m3u_path = temp_file("sample.m3u");
    std::fs::write(
        &m3u_path,
        "#EXTM3U\n#EXTINF:-1,Radio Test\nhttps://example.org/stream.mp3\n",
    )
    .unwrap();

    let out = Command::new(timonde_bin())
        .args(["--parse-file-json", m3u_path.to_str().unwrap()])
        .output()
        .expect("Échec --parse-file-json");
    assert!(out.status.success());
    let parsed: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    let stations = parsed.as_array().unwrap();
    assert_eq!(stations.len(), 1);
    assert_eq!(stations[0]["name"], "Radio Test");
    assert_eq!(stations[0]["url"], "https://example.org/stream.mp3");

    let _ = std::fs::remove_file(&m3u_path);
}
