use gstreamer::prelude::*;
use log::{error, info};
use std::sync::{Arc, Mutex};

/// État de lecture actuel
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlaybackState {
    Stopped,
    Buffering,
    Playing,
    Paused,
    Error,
}

/// Erreurs potentielles du moteur audio
#[derive(Debug)]
pub enum AudioError {
    Init(gstreamer::glib::Error),
    Build(String),
    StateChange(String),
}

impl std::fmt::Display for AudioError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Init(e) => write!(f, "Erreur initialisation GStreamer : {}", e),
            Self::Build(msg) => write!(f, "Erreur création pipeline : {}", msg),
            Self::StateChange(msg) => write!(f, "Erreur changement d'état : {}", msg),
        }
    }
}

impl std::error::Error for AudioError {}

/// Moteur audio s'appuyant sur GStreamer (playbin)
pub struct AudioEngine {
    pipeline: gstreamer::Element,
    _bus_watch: Option<gstreamer::bus::BusWatchGuard>,
    current_url: Arc<Mutex<Option<String>>>,
    state: Arc<Mutex<PlaybackState>>,
    current_title: Arc<Mutex<Option<String>>>,
}

impl AudioEngine {
    pub fn new(current_title: Arc<Mutex<Option<String>>>) -> Result<Self, AudioError> {
        gstreamer::init().map_err(AudioError::Init)?;

        let registry = gstreamer::Registry::get();

        // 1. Éliminer le chargement du mastodonte FFmpeg (libgstlibav.so et ses ~35 Mo de dépendances)
        // Les flux webradio sont décodés par des bibliothèques C légères (mpg123, faad, vorbis, opus, flac).
        if let Some(plugin) = registry.find_plugin("libav") {
            registry.remove_plugin(&plugin);
            info!("🛡️ Plugin lourd libav (FFmpeg) exclu du registre GStreamer pour préserver la RAM");
        }

        // 2. Favoriser les décodeurs audio natifs ultra-légers
        if let Some(feature) = registry.lookup_feature("faad") {
            use gstreamer::prelude::PluginFeatureExtManual;
            feature.set_rank(gstreamer::Rank::PRIMARY + 10);
            info!("⚡ Décodeur léger faad promu prioritaire pour l AAC");
        }
        if let Some(feature) = registry.lookup_feature("mpg123audiodec") {
            use gstreamer::prelude::PluginFeatureExtManual;
            feature.set_rank(gstreamer::Rank::PRIMARY + 10);
            info!("⚡ Décodeur léger mpg123 promu prioritaire pour le MP3");
        }

        let pipeline = gstreamer::ElementFactory::make("playbin")
            .name("timonde-player")
            .build()
            .map_err(|e| AudioError::Build(e.to_string()))?;

        // Optimisations mémoire drastiques :
        // 1. Désactiver la vidéo, le texte/sous-titres, visualisation, etc.
        pipeline.set_property_from_str("flags", "audio+soft-volume+buffering");

        // 2. Éléments factices pour la vidéo et les sous-titres (évite de charger les plugins vidéo)
        if let Ok(video_sink) = gstreamer::ElementFactory::make("fakesink").name("dummy-video").build() {
            pipeline.set_property("video-sink", &video_sink);
        }
        if let Ok(text_sink) = gstreamer::ElementFactory::make("fakesink").name("dummy-text").build() {
            pipeline.set_property("text-sink", &text_sink);
        }

        // 3. Réduire la taille du tampon (Buffer Duration & Size)
        pipeline.set_property("buffer-size", 640 * 1024i32);
        pipeline.set_property("buffer-duration", (2i64) * 1_000_000_000i64);

        let state = Arc::new(Mutex::new(PlaybackState::Stopped));
        let current_url = Arc::new(Mutex::new(None));

        let bus_watch = if let Some(bus) = pipeline.bus() {
            let state_clone = Arc::clone(&state);
            let title_clone = Arc::clone(&current_title);
            let guard = bus.add_watch(move |_, msg| {
                use gstreamer::MessageView;
                match msg.view() {
                    MessageView::StateChanged(sc) => {
                        if sc.src().map(|s| s.name() == "timonde-player").unwrap_or(false) {
                            let mut st = state_clone.lock().unwrap();
                            match sc.current() {
                                gstreamer::State::Playing => {
                                    *st = PlaybackState::Playing;
                                }
                                gstreamer::State::Paused => {
                                    if *st != PlaybackState::Buffering {
                                        *st = PlaybackState::Paused;
                                    }
                                }
                                gstreamer::State::Ready | gstreamer::State::Null => {
                                    *st = PlaybackState::Stopped;
                                }
                                _ => {}
                            }
                        }
                    }
                    MessageView::Buffering(b) => {
                        let percent = b.percent();
                        if percent < 100 {
                            *state_clone.lock().unwrap() = PlaybackState::Buffering;
                        } else {
                            *state_clone.lock().unwrap() = PlaybackState::Playing;
                        }
                    }
                    MessageView::Error(err) => {
                        error!("Erreur GStreamer : {} ({:?})", err.error(), err.debug());
                        *state_clone.lock().unwrap() = PlaybackState::Error;
                    }
                    MessageView::Eos(_) => {
                        info!("Fin de flux atteinte (EOS)");
                        *state_clone.lock().unwrap() = PlaybackState::Stopped;
                    }
                    MessageView::Tag(tag) => {
                        let tags = tag.tags();
                        if let Some(title) = tags.get::<gstreamer::tags::Title>() {
                            let title_str = title.get().to_string();
                            info!("Titre en cours : {}", title_str);
                            *title_clone.lock().unwrap() = Some(title_str);
                        }
                    }
                    _ => {}
                }
                gstreamer::glib::ControlFlow::Continue
            });
            guard.ok()
        } else {
            None
        };

        Ok(Self {
            pipeline,
            _bus_watch: bus_watch,
            current_url,
            state,
            current_title,
        })
    }

    pub fn play(&self, url: &str) -> Result<(), AudioError> {
        info!("Démarrage du flux : {}", url);
        *self.state.lock().unwrap() = PlaybackState::Buffering;
        *self.current_title.lock().unwrap() = None;
        *self.current_url.lock().unwrap() = Some(url.to_string());

        let _ = self.pipeline.set_state(gstreamer::State::Ready);
        self.pipeline.set_property("uri", url);
        self.pipeline
            .set_state(gstreamer::State::Playing)
            .map_err(|e| AudioError::StateChange(format!("{:?}", e)))?;

        Ok(())
    }

    pub fn pause(&self) -> Result<(), AudioError> {
        info!("Mise en pause de la lecture");
        self.pipeline
            .set_state(gstreamer::State::Paused)
            .map_err(|e| AudioError::StateChange(format!("{:?}", e)))?;
        *self.state.lock().unwrap() = PlaybackState::Paused;
        Ok(())
    }

    pub fn resume(&self) -> Result<(), AudioError> {
        info!("Reprise de la lecture");
        self.pipeline
            .set_state(gstreamer::State::Playing)
            .map_err(|e| AudioError::StateChange(format!("{:?}", e)))?;
        *self.state.lock().unwrap() = PlaybackState::Playing;
        Ok(())
    }

    pub fn stop(&self) -> Result<(), AudioError> {
        info!("Arrêt du flux et réinitialisation du pipeline");
        let _ = self.pipeline.set_state(gstreamer::State::Null);
        self.pipeline
            .set_state(gstreamer::State::Null)
            .map_err(|e| AudioError::StateChange(format!("{:?}", e)))?;

        *self.state.lock().unwrap() = PlaybackState::Stopped;
        *self.current_title.lock().unwrap() = None;
        unsafe {
            libc::malloc_trim(0);
        }
        Ok(())
    }

    pub fn set_volume(&self, volume: f64) {
        self.pipeline.set_property("volume", volume);
    }

    pub fn state(&self) -> PlaybackState {
        *self.state.lock().unwrap()
    }
}

impl Drop for AudioEngine {
    fn drop(&mut self) {
        let _ = self.pipeline.set_state(gstreamer::State::Null);
    }
}
