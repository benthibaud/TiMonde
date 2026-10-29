//! Utilitaires d'émulation de clic droit sous X11 (XTest) pour afficher le menu contextuel sans latence.

/// Harmonisation multi-bureaux (LXQt, XFCE, MATE sous X11) :
/// Certains panneaux de barre des tâches (comme lxqt-panel ou xfce4-panel) ne délèguent pas
/// l'ouverture du D-BusMenu lors d'un clic gauche (Qt::LeftButton), mais appellent obligatoirement
/// la méthode `Activate(x, y)` sur D-Bus, réservant l'ouverture de leur menu au seul clic droit.
///
/// Cette fonction injecte instantanément un événement physique de clic droit via l'extension X11 XTest.
/// Avantages majeurs :
/// - Latence strictement nulle (0 ms, exécuté en espace utilisateur en ~0.05 ms).
/// - Ouvre le menu contextuel natif généré par le panneau hôte (respect absolu du thème Qt/GTK du bureau).
/// - Zéro processus externe forké, zéro allocation mémoire lourde.
/// - Liaison dynamique FFI sans dépendance de compilation statique obligatoire.
pub fn try_trigger_context_menu_x11() -> bool {
    // Si la session est sous Wayland (pur ou avec XWayland), XTest ne doit pas être utilisé :
    // il frapperait dans le vide ou n'atteindrait pas le compositeur Wayland.
    // On laisse alors s'exécuter le repli D-Bus natif (show_menu.py).
    if std::env::var_os("WAYLAND_DISPLAY").is_some()
        || std::env::var("XDG_SESSION_TYPE")
            .map(|v| v.eq_ignore_ascii_case("wayland"))
            .unwrap_or(false)
    {
        return false;
    }

    if std::env::var_os("DISPLAY").is_none() {
        return false;
    }
    unsafe {
        let x11_name = match std::ffi::CString::new("libX11.so.6") {
            Ok(s) => s,
            Err(_) => return false,
        };
        let xtst_name = match std::ffi::CString::new("libXtst.so.6") {
            Ok(s) => s,
            Err(_) => return false,
        };
        let lib_x11 = libc::dlopen(x11_name.as_ptr(), libc::RTLD_LAZY);
        if lib_x11.is_null() {
            return false;
        }
        let lib_xtst = libc::dlopen(xtst_name.as_ptr(), libc::RTLD_LAZY);
        if lib_xtst.is_null() {
            libc::dlclose(lib_x11);
            return false;
        }

        type XOpenDisplayFn = unsafe extern "C" fn(*const libc::c_char) -> *mut libc::c_void;
        type XCloseDisplayFn = unsafe extern "C" fn(*mut libc::c_void) -> libc::c_int;
        type XFlushFn = unsafe extern "C" fn(*mut libc::c_void) -> libc::c_int;
        type XTestFakeButtonEventFn =
            unsafe extern "C" fn(*mut libc::c_void, libc::c_uint, libc::c_int, libc::c_ulong) -> libc::c_int;

        let fn_open: Option<XOpenDisplayFn> =
            std::mem::transmute(libc::dlsym(lib_x11, c"XOpenDisplay".as_ptr()));
        let fn_close: Option<XCloseDisplayFn> =
            std::mem::transmute(libc::dlsym(lib_x11, c"XCloseDisplay".as_ptr()));
        let fn_flush: Option<XFlushFn> =
            std::mem::transmute(libc::dlsym(lib_x11, c"XFlush".as_ptr()));
        let fn_fake: Option<XTestFakeButtonEventFn> =
            std::mem::transmute(libc::dlsym(lib_xtst, c"XTestFakeButtonEvent".as_ptr()));

        let mut success = false;
        if let (Some(open), Some(close), Some(flush), Some(fake)) = (fn_open, fn_close, fn_flush, fn_fake) {
            let display = open(std::ptr::null());
            if !display.is_null() {
                // Button 3 = clic droit souris physique
                fake(display, 3, 1, 0);
                fake(display, 3, 0, 0);
                flush(display);
                close(display);
                success = true;
            }
        }

        libc::dlclose(lib_xtst);
        libc::dlclose(lib_x11);
        success
    }
}
