                      Zoo Mode
                         │
                         ▼
                 render_meditation.py
                         │
               config/voice.yaml
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      Kokoro-82M    Chatterbox Nano  Chatterbox Turbo
         82M             110M            350M
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                 speech segments
                         │
                 exact [pause Ns]
                         │
                 FFmpeg processing
                         │
             loudness normalization
                         │
                         ▼
                   final WAV


Chatterbox currently exposes Nano through the same ChatterboxTurboTTS class as Turbo, using nano=True; Nano is 110M and designed for low-resource/CPU inference, while Turbo is 350M and intended for efficient English synthesis and narration.

The renderer now supports these presets:
```
meditation-warm
    Kokoro / af_nicole / 0.90

meditation-warm-british
    Kokoro / bf_isabella / 0.90

meditation-deep
    Kokoro / am_onyx / 0.90

meditation-bella
    Kokoro / af_bella / 0.90

chatterbox-nano-meditation
    Chatterbox Nano / 0.92

chatterbox-turbo-meditation
    Chatterbox Turbo / 0.92
```

