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
}

impl AudioEngine {
    pub fn new() -> Result<Self, AudioError> {
        gstreamer::init().map_err(AudioError::Init)?;

        // Favoriser les décodeurs audio natifs ultra-légers (évite de charger FFmpeg/libavcodec et ses 15 Mo de dépendances)
        if let Some(feature) = gstreamer::Registry::get().lookup_feature("faad") {
            use gstreamer::prelude::PluginFeatureExtManual;
            feature.set_rank(gstreamer::Rank::PRIMARY + 10);
            info!("⚡ Décodeur léger faad promu prioritaire pour l AAC");
        }

        let pipeline = gstreamer::ElementFactory::make("playbin")
            .name("timonde-player")
            .build()
            .map_err(|e| AudioError::Build(e.to_string()))?;

        // Optimisations mémoire drastiques issues de radiotray-ng :
        // 1. Désactiver la vidéo, le texte/sous-titres, visualisation, etc.
        // Flags audio exclusifs : GST_PLAY_FLAG_AUDIO (0x02) | GST_PLAY_FLAG_SOFT_VOLUME (0x10) | GST_PLAY_FLAG_BUFFERING (0x100) = 274 (0x112)
        pipeline.set_property_from_str("flags", "audio+soft-volume+buffering");

        // 2. Éléments factices pour la vidéo et les sous-titres (évite de charger les plugins vidéo)
        if let Ok(video_sink) = gstreamer::ElementFactory::make("fakesink").name("dummy-video").build() {
            pipeline.set_property("video-sink", &video_sink);
        }
        if let Ok(text_sink) = gstreamer::ElementFactory::make("fakesink").name("dummy-text").build() {
            pipeline.set_property("text-sink", &text_sink);
        }

        // 3. Tailles de buffer calquées sur radiotray-ng (320 Ko * 2 = 640 Ko, 2 secondes)
        let buffer_size: i32 = 640_000;
        let buffer_duration: i64 = 2 * (gstreamer::ClockTime::SECOND.nseconds() as i64);
        pipeline.set_property("buffer-size", buffer_size);
        pipeline.set_property("buffer-duration", buffer_duration);

        let current_url = Arc::new(Mutex::new(None));
        let state = Arc::new(Mutex::new(PlaybackState::Stopped));

        let bus_watch = if let Some(bus) = pipeline.bus() {
            let state_clone = Arc::clone(&state);
            let guard = bus.add_watch(move |_, msg| {
                use gstreamer::MessageView;
                match msg.view() {
                    MessageView::StateChanged(s) => {
                        if s.src().map(|src| src.name()).as_deref() == Some("timonde-player") {
                            let mut st = state_clone.lock().unwrap();
                            match s.current() {
                                gstreamer::State::Playing => *st = PlaybackState::Playing,
                                gstreamer::State::Paused => {
                                    if *st != PlaybackState::Paused {
                                        *st = PlaybackState::Buffering;
                                    }
                                }
                                gstreamer::State::Ready | gstreamer::State::Null => *st = PlaybackState::Stopped,
                                _ => {}
                            }
                        }
                    }
                    MessageView::Buffering(b) => {
                        let percent = b.percent();
                        let mut st = state_clone.lock().unwrap();
                        if *st != PlaybackState::Paused {
                            if percent < 100 {
                                *st = PlaybackState::Buffering;
                            } else {
                                *st = PlaybackState::Playing;
                            }
                        }
                    }
                    MessageView::Error(err) => {
                        error!("Erreur GStreamer : {} ({})", err.error(), err.debug().unwrap_or_default());
                        *state_clone.lock().unwrap() = PlaybackState::Error;
                    }
                    MessageView::Tag(tag) => {
                        let tags = tag.tags();
                        if let Some(title) = tags.get::<gstreamer::tags::Title>() {
                            info!("Titre en cours : {}", title.get());
                        }
                    }
                    _ => {}
                }
                gstreamer::glib::ControlFlow::Continue
            }).map_err(|e| AudioError::Build(e.to_string()))?;
            Some(guard)
        } else {
            None
        };

        Ok(Self {
            pipeline,
            _bus_watch: bus_watch,
            current_url,
            state,
        })
    }

    /// Démarre la lecture d'une URL de flux audio
    pub fn play(&self, url: &str) -> Result<(), AudioError> {
        info!("Démarrage du flux : {}", url);
        self.stop()?;

        self.pipeline.set_property("uri", url);
        self.pipeline
            .set_state(gstreamer::State::Playing)
            .map_err(|e| AudioError::StateChange(format!("{:?}", e)))?;

        *self.current_url.lock().unwrap() = Some(url.to_string());
        *self.state.lock().unwrap() = PlaybackState::Buffering;
        Ok(())
    }

    /// Met en pause la lecture
    pub fn pause(&self) -> Result<(), AudioError> {
        info!("Mise en pause de la lecture");
        self.pipeline
            .set_state(gstreamer::State::Paused)
            .map_err(|e| AudioError::StateChange(format!("{:?}", e)))?;

        *self.state.lock().unwrap() = PlaybackState::Paused;
        Ok(())
    }

    /// Reprend la lecture après une pause
    pub fn resume(&self) -> Result<(), AudioError> {
        info!("Reprise de la lecture");
        self.pipeline
            .set_state(gstreamer::State::Playing)
            .map_err(|e| AudioError::StateChange(format!("{:?}", e)))?;

        *self.state.lock().unwrap() = PlaybackState::Playing;
        Ok(())
    }

    /// Arrête la lecture et libère les buffers internes
    pub fn stop(&self) -> Result<(), AudioError> {
        self.pipeline
            .set_state(gstreamer::State::Null)
            .map_err(|e| AudioError::StateChange(format!("{:?}", e)))?;

        *self.state.lock().unwrap() = PlaybackState::Stopped;
        unsafe {
            libc::malloc_trim(0);
        }
        Ok(())
    }

    /// Ajuste le volume
    pub fn set_volume(&self, volume: f64) {
        let clamped = volume.clamp(0.0, 1.5);
        self.pipeline.set_property("volume", clamped);
    }

    /// Obtient le volume actuel
    pub fn volume(&self) -> f64 {
        self.pipeline.property::<f64>("volume")
    }

    /// Obtient l'état actuel de lecture
    pub fn state(&self) -> PlaybackState {
        *self.state.lock().unwrap()
    }

    /// Obtient l'URL en cours de lecture
    pub fn current_url(&self) -> Option<String> {
        self.current_url.lock().unwrap().clone()
    }
}

impl Drop for AudioEngine {
    fn drop(&mut self) {
        let _ = self.pipeline.set_state(gstreamer::State::Null);
    }
}
