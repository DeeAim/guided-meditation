
# 1. Commands

## Kokoro-82M installation
https://chatgpt.com/c/6a7c7b06-fae0-83eb-ad27-732ba6352abd

### Activate virtual environment
source .venv/bin/activate

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

deactivate
sudo apt-get update
sudo apt-get install -y espeak-ng

### test Kokoro
source .venv/bin/activate
python -c "from kokoro import KPipeline; print('Kokoro OK')"

### First test: af_nicole and Second test: bf_isabella
python render_meditation.py scripts/test.md --backend kokoro --voice af_nicole --speed 0.90 (*****)
python render_meditation.py scripts/test.md --backend kokoro --voice af_sky --speed 0.88 (***)
python render_meditation.py scripts/test.md --backend kokoro --voice bf_isabella --speed 0.85
python render_meditation.py scripts/test.md --backend kokoro --voice am_onyx --speed 0.90  (***)
python render_meditation.py scripts/test.md --backend kokoro --voice bm_lewis --speed 0.90
python render_meditation.py scripts/test.md --backend kokoro --voice af_bella --speed 0.90 (***)

python render_meditation.py scripts/test.md --backend kokoro --voice 'af_nicole:0.4,af_bella:0.6' --speed 0.90 (****)
python render_meditation.py scripts/test.md --backend kokoro --voice 'af_nicole:0.8,af_bella:0.2' --speed 0.90 
python render_meditation.py scripts/test.md --backend kokoro --voice 'af_nicole:0.5,af_bella:0.5' --speed 0.90 

python render_meditation.py scripts/test-v2.md --backend kokoro --voice af_nicole --speed 0.90 (*****)
python render_meditation.py scripts/test-v2.md --backend kokoro --voice bf_isabella --speed 0.86 (**)
python render_meditation.py scripts/test-v2.md --backend kokoro --voice am_onyx --speed 0.90  (***)
python render_meditation.py scripts/test-v2.md --backend kokoro --voice bm_lewis --speed 0.90
python render_meditation.py scripts/test-v2.md --backend kokoro --voice af_sky --speed 0.88
python render_meditation.py scripts/test-v2.md --backend kokoro --voice af_bella --speed 0.90

python render_meditation.py scripts/test-v2.md --backend kokoro --voice 'af_nicole:0.4,af_bella:0.6' --speed 0.90 (****)
python render_meditation.py scripts/test-v2.md --backend kokoro --voice 'af_nicole:0.8,af_bella:0.2' --speed 0.90 
python render_meditation.py scripts/test-v2.md --backend kokoro --voice 'af_nicole:0.5,af_bella:0.5' --speed 0.90 

#### French
python render_meditation.py scripts/test_fr.md --backend kokoro --voice ff_siwis --speed 0.90
python render_meditation.py scripts/test-v2_fr.md --backend kokoro --voice bm_lewis --speed 0.90


Something to test: 
Kokoro consumes voice packs. The official pipeline can load those packs directly, and it can even average several Kokoro voices together and it averages the corresponding voice tensors: `pipeline.load_voice("af_heart,af_bella")`

### To test meditation speeds between 0.82–0.95
Don't immediately assume the slowest one will sound best. TTS voices can become unnatural when slowed too aggressively.


### Validate the renderer
`.venv/bin/python render_meditation.py --help`
```
usage: render_meditation.py [-h] [--config CONFIG] [--preset PRESET] [--backend {kokoro,chatterbox-nano,chatterbox-turbo}]
                            [--voice VOICE] [--speed SPEED] [--reference-audio REFERENCE_AUDIO]
                            [--script-profile {auto,prose,pause-heavy}] [--output OUTPUT] [--normalize | --no-normalize]
                            script

Guided meditation TTS renderer v2

positional arguments:
  script

options:
  -h, --help            show this help message and exit
  --config CONFIG
  --preset PRESET
  --backend {kokoro,chatterbox-nano,chatterbox-turbo}
  --voice VOICE
  --speed SPEED
  --reference-audio REFERENCE_AUDIO
  --script-profile {auto,prose,pause-heavy}
  --output OUTPUT
  --normalize
  --no-normalize
  ```

  ### Check voice.yaml
`.venv/bin/python -c "import yaml; c=yaml.safe_load(open('config/voice.yaml')); print(list(c['presets']))"`
```
meditation-warm
meditation-warm-british
meditation-deep
meditation-bella
chatterbox-nano-meditation
chatterbox-turbo-meditation
```

### Test the new script
Script profile: pause-heavy
.venv/bin/python render_meditation.py \
  scripts/test.md \
  --preset meditation-warm

#### Script profile: prose
.venv/bin/python render_meditation.py \
  scripts/test-v2.md \
  --preset meditation-warm

## Testing Chatterbox nano and turbo
### Use chatterbox-nano with meditation-male-clive-catterall.wav
.venv-chatterbox/bin/python render_meditation.py \
  scripts/test.md \
  --preset chatterbox-nano-meditation \
  --reference-audio references/meditation-male-clive-catterall.wav

### Use chatterbox-turbo with meditation-male-clive-catterall.wav (*****)
.venv-chatterbox/bin/python render_meditation.py \
  scripts/test.md \
  --preset chatterbox-turbo-meditation \
  --reference-audio references/meditation-male-clive-catterall.wav

### Use chatterbox-nano with meditation-female-cori-samuel.wav
.venv-chatterbox/bin/python render_meditation.py \
  scripts/test.md \
  --preset chatterbox-nano-meditation \
  --reference-audio references/meditation-female-cori-samuel.wav

### Use chatterbox-turbo with meditation-female-cori-samuel.wav
.venv-chatterbox/bin/python render_meditation.py \
  scripts/test.md \
  --preset chatterbox-turbo-meditation \
  --reference-audio references/meditation-female-cori-samuel.wav

### meditation-male-chris_vocals.wav (*****)
.venv-chatterbox/bin/python render_meditation.py \
  scripts/test.md \
  --preset chatterbox-turbo-meditation \
  --reference-audio references/meditation-male-chris_vocals.wav

### Use chatterbox-turbo with meditation-male-keep-going_insta.wav
.venv-chatterbox/bin/python render_meditation.py \
  scripts/test.md \
  --preset chatterbox-turbo-meditation \
  --reference-audio references/meditation-male-keep-going_insta.wav

## Shortlisted voice with Chatterbox
### Use chatterbox-turbo with meditation-male-clive-catterall.wav (*****)
.venv-chatterbox/bin/python render_meditation.py \
  scripts/test.md \
  --preset chatterbox-turbo-meditation \
  --reference-audio references/meditation-male-clive-catterall.wav

.venv-chatterbox/bin/python render_meditation.py \
  scripts/test-v2.md \
  --preset chatterbox-turbo-meditation \
  --reference-audio references/meditation-male-clive-catterall.wav

### meditation-male-chris_vocals.wav (*****)
.venv-chatterbox/bin/python render_meditation.py \
  scripts/test.md \
  --preset chatterbox-turbo-meditation \
  --reference-audio references/meditation-male-chris_vocals.wav

.venv-chatterbox/bin/python render_meditation.py \
  scripts/test-v2.md \
  --preset chatterbox-turbo-meditation \
  --reference-audio references/meditation-male-chris_vocals.wav



# 2 `🧘 Meditation Voiceover` Mode commands examples

"Render scripts/morning.md using meditation-warm"

"Compare Nicole and Isabella"

"Make this one 8% slower"

"Try Chatterbox Nano"

"Regenerate this meditation without normalization"

"Render this pause-heavy script"

"Render scripts/test.md using meditation-warm-british and compare it with meditation-warm."

"Render scripts/test.md using Chatterbox Nano. 
Use the reference voice in references/meditation-speaker.wav."

## Review render_meditation.py with `🧘 Meditation Voiceover` Mode
```
Inspect @/config/voice.yaml and @/render_meditation.py.

Verify that this project is correctly configured for the
Meditation Voiceover V2 workflow.

Do not modify anything yet.

Check:
- Kokoro environment
- Chatterbox environment
- FFmpeg
- espeak-ng
- available presets
- scripts/test.md
- output/manifests/segments directories

Then tell me whether the project is ready to render using:
1. meditation-warm
2. meditation-warm-british
3. chatterbox-nano-meditation
4. chatterbox-turbo-meditation
```

# 3. Meditation voice for kokoro-82M

https://voicerankings.com/voice/kokoro-82M/female
https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md

## af_nicole (*****)
https://voicerankings.com/voice/kokoro-82M/female/af_nicole
Archetype: The Sleep Narrator
Emotion: Sympathetic / Reassurance
Texture: Airy / Breathy
Age: Young Adult
Pitch: 210 Hz
Speed: 117 WPM
Expressiveness: 3
Projection: 1
Roughness: 4
Tempo: 2
Brightness: 2
Articulation: 4
Instability: 2
Accent: 1

## bf_isabella
https://voicerankings.com/voice/kokoro-82M/female/bf_isabella
Archetype: The Caring Guide
Emotion: Friendly / Warm
Texture: Airy / Breathy
Age: Young Adult
Pitch: 215 Hz
Speed: 186 WPM
Expressiveness: 6
Projection: 4
Roughness: 3
Tempo: 5
Brightness: 5
Articulation: 5
Instability: 3
Accent: 5

# am_onyx - slow it down
https://voicerankings.com/voice/kokoro-82M/male/am_onyx
Archetype: The Caring Guide
Emotion: Friendly / Warm
Texture: Liquid / Warm
Age: Mature Adult
Pitch: 105 Hz
Speed: 194 WPM
Expressiveness: 6
Projection: 4
Roughness: 4
Tempo: 5
Brightness: 3
Articulation: 5
Instability: 2
Accent: 4

## bm_lewis
https://voicerankings.com/voice/kokoro-82M/male/bm_lewis


## bm_fable

## am_puck



# 3. Chatterbox 
This is the interesting higher-end option.

Resemble AI's current Chatterbox family includes a 350M English Turbo model and 500M multilingual models. It supports reference-audio voice conditioning / voice cloning and more expressive generation. The current implementation explicitly supports cpu as a device for the standard models.

For meditation, voice cloning is particularly attractive.

You could record or license a voice actor saying perhaps:

"Allow yourself to become comfortable. Feel the weight of your body settling into the surface beneath you..."

and condition subsequent speech on that voice/style.

Chatterbox also gives you parameters such as exaggeration and cfg_weight, and Resemble documents how those affect pacing and expressiveness.

But I would not deploy Chatterbox as the main engine on your E-2176G.

It can technically use CPU, but 350M–500M generative models are several times larger than Kokoro. On your 6-core Xeon, I'd expect significantly poorer throughput. That's an inference based on the architectures/model sizes rather than a published benchmark for your particular CPU.

# 4. Chatterbox-Nano 110M on VPS
I would pick Chatterbox-Nano 110M, provided you have a good reference voice that you own or are licensed to use.

The deciding factor is not the extra 28M parameters. It is voice conditioning. Chatterbox-Nano accepts a roughly 10-second reference recording and uses it for zero-shot voice cloning, so you can deliberately choose a narrator who sounds warm, intimate, calm, and reassuring.

Chatterbox-Nano's official example explicitly runs with device="cpu" and uses a reference clip for generation. It also uses the same streamlined architecture as Chatterbox Turbo, including a single-step speech-token-to-mel decoder.

Why I'd prefer Nano for meditation

Consider what matters after someone has listened for ten minutes.

A technically clean voice isn't enough. You want:

softness → warmth → consistency → intimacy → natural phrase endings → absence of “TTS fatigue.”

With Kokoro, you're asking:
> Which available Kokoro voice comes closest to the meditation narrator I want?

With Chatterbox-Nano, you're asking:
> What should my meditation narrator sound like?

Then you supply that voice as the reference. That difference is substantial.

For example, you could record a high-quality 10-second reference along these lines:
> Gently allow your attention to settle on your breathing. There is nowhere you need to go, and nothing you need to change right now.

Read it with exactly the cadence, warmth and intimacy you want. Chatterbox-Nano can then condition subsequent synthesis on that reference; the official Nano example uses a 10-second reference clip.

One Nano feature to know about
Every Chatterbox-generated audio file includes Resemble's PerTh neural watermark. Resemble describes it as imperceptible and designed to survive MP3 compression and common editing.

# 5. Run on Google Collab

| Model                     | Free Colab       | 20-min meditation | Setup                | Recommendation                  |
| ------------------------- | ---------------- | ----------------- | -------------------- | ------------------------------- |
| **Chatterbox-Turbo 350M** | ✅ Good candidate | ✅ Yes             | Relatively easy      | **My choice**                   |
| **Chatterbox 500M**       | ✅ Likely         | ✅ Yes             | Moderate             | Good if Turbo voice isn't right |
| **Chatterbox-Nano 110M**  | ✅ Easily         | ✅ Yes             | Easy                 | Great for drafts / VPS          |
| **StyleTTS2**             | ✅ Yes            | ✅ Yes             | More fragile/complex | Experiment second               |
| **Kokoro-82M**            | ✅ Easily         | ✅ Yes             | Very easy            | Excellent baseline              |

A free Google Colab is a realistic way to produce a 20-minute guided meditation, especially with Chatterbox. I would favor Chatterbox over StyleTTS2 for this workflow.

The caveat is that Google does not guarantee GPU access, GPU type, runtime duration, or fixed usage limits on the free tier. Free notebooks can run for up to 12 hours, subject to availability and usage patterns, and GPU access is heavily restricted.

The current Chatterbox family is actually more interesting than when we discussed it previously. Resemble AI now offers Turbo at 350M parameters and Nano at 110M parameters. They specifically describe Turbo as lower-compute/lower-VRAM and suitable for narration, while Nano targets CPU/on-device inference and is claimed to run about 3× real time on 8 CPU cores.

For commercial work, of course, use your own voice or a voice for which you have explicit cloning/licensing permission.

Chatterbox Turbo also supports paralinguistic tags and is explicitly described by its developers as working well for narration and creative workflows.

## What about StyleTTS2?
The official StyleTTS2 repository contains a Colab directory and provides dedicated inference notebooks for its single-speaker and multi-speaker pretrained models.

And quality was the entire point of StyleTTS2: the research uses latent style diffusion and speech-language-model adversarial training to improve naturalness.

However, I'd rank it below Chatterbox for this project because its ecosystem feels much more like a research project:
- more dependencies;
- phonemizer/espeak setup;
- multiple supporting pretrained components;
- more complicated speaker/style handling;
- some licensing considerations around inference dependencies and pretrained voices.

So I'd use:
> Chatterbox first → StyleTTS2 only if its sound noticeably wins your listening test.

# 6. Voices 

## Possible to get samples from [librivox](https://librivox.org/)
[Children's Fiction](https://librivox.org/search?primary_key=1&search_category=genre&search_page=1&search_form=get_results&search_order=alpha)



## Short-listed by [chatGPT 5.6](https://chatgpt.com/c/6a7e34ef-bf50-83eb-92ac-96a41b15344b)
- (*****) [Cori Samuel — The Secret Agent, Chapter I](https://librivox.org/the-secret-agent-by-joseph-conrad-2)
> Suggested 20–60 second segment: approximately 00:00:25–00:00:58, move them ±2–3 seconds to the nearest complete-sentence pauses after auditioning.

- (***) [Helen Taylor — The Enchanted April, Chapter 3](https://librivox.org/the-enchanted-april-version-2-by-elizabeth-von-arnim/)
> Suggested segment: about 00:01:04–00:01:42 (~38 sec). This is the most precisely researched excerpt in the set.

- (***) [John Van Stan — Seneca, “On Quiet Conversation”](https://librivox.org/moral-letters-to-lucilius-epistulae-morales-ad-lucilium-by-lucius-annaeus-seneca)
> Suggested segment: approximately 00:00:24–00:00:58 (~34 sec)

- (***) [Phil Benson — Six Lectures on Literature, Lecture 1](https://librivox.org/six-lectures-on-literature-by-charles-harold-herford/)
> Suggested segment: roughly 00:00:25–00:01:00

- (not tested) [Ruth Golding — The Speaking Voice, “The Essay”](https://librivox.org/the-speaking-voice-by-katherine-jewell-everts)

- (*****) [Peter Yearsley — Sadhana, “Realisation in Love”](https://librivox.org/sadhana-by-rabindranath-tagore-v2/)
> Suggested segment: roughly 00:00:25–00:01:00

- (*****) [David Barnes — On Union with God, “Interior Recollection”](https://librivox.org/on-union-with-god-by-blessed-albert-the-great/)
> Suggested segment: roughly 00:00:25–00:00:58

## Personal exploration
Good one from [A Leaf from Heaven (in Hans Christian Andersen Fairy Tale Collection)](https://librivox.org/hans-christian-andersen-fairy-tale-collection-by-hans-christian-andersen/)
- andersen_01_inathousandyears_lkp_64kb.mp3 (Lucy Perry)
- andersen_07_theemperorsnewsuit_eep_64kb.mp3
- andersen_20_theelfoftherose_cpac_64kb.mp3 (*****)
- andersen_02_thetinderbox_mme_64kb.mp3 (****)
- andersen_13_greatclausandlittleclaus_mme_64kb.mp3
- andersen_16_angel_lf_64kb
- andersen_17_buckwheat_lf_64kb
- andersen_19_thebelldeep_mme_64kb (***)

# 7 Places for sample voices

For **guided meditations**, there are several good options depending on whether you want an existing synthetic narrator or actual reference audio for voice cloning/style transfer.

* **Kokoro-82M** — probably the easiest starting point. It’s an open-weight TTS model with Apache-licensed weights and includes multiple built-in voices such as `af_heart` and `af_sky`. You can slow the delivery somewhat and add pauses between sentences, which works nicely for meditation narration. ([Hugging Face][1])
* **LibriVox** — excellent if you specifically need **human reference recordings**. LibriVox explicitly releases its recordings into the public domain and says they may be reused, remixed, broadcast, or commercially used. There are thousands of narrators, so you can search for a calm, slow speaker whose pacing fits your meditation style. ([LibriVox][2])
* **LibriTTS / LibriTTS-R** — better if you're building or fine-tuning a TTS system. LibriTTS contains about 585 hours of sentence-level English speech and is CC BY 4.0; LibriTTS-R is an audio-quality-enhanced version under the same license. ([OpenSLR][3])
* **Mozilla Common Voice** — useful if you want lots of different speakers, accents, genders, and languages. Mozilla currently makes Common Voice datasets available under CC0 unless otherwise specified, although access/distribution is subject to Mozilla's dataset terms. ([Common Voice][4])
* **OpenVoice V2** — useful if you already have an appropriate reference voice and actually want to perform voice cloning/style transfer locally. OpenVoice V1/V2 are MIT-licensed and support commercial as well as research use. ([GitHub][5])

For a meditation product, I'd personally favor **Kokoro rather than cloning a LibriVox narrator**. You avoid deliberately recreating a particular real person's identity, while still getting a consistent narrator you can tune for slower pacing.

A meditation-oriented setup could be roughly: **Kokoro `af_heart` → slightly reduced speaking speed → 500–1,500 ms pauses at paragraph boundaries → very light room/reverb processing afterward.**

If by “voice reference” you mean **a 10–30 second human WAV/MP3 that you can feed into a voice-cloning model**, I can also find you **5–10 specific public-domain reference voices with a soft, warm, meditative sound**, including male and female options.

[1]: https://huggingface.co/hexgrad/Kokoro-82M?utm_source=chatgpt.com "hexgrad/Kokoro-82M"
[2]: https://librivox.org/pages/public-domain/?utm_source=chatgpt.com "Public Domain"
[3]: https://www.openslr.org/60/?utm_source=chatgpt.com "LibriTTS corpus"
[4]: https://commonvoice.mozilla.org/terms?utm_source=chatgpt.com "Common Voice Legal Terms - Mozilla"
[5]: https://github.com/myshell-ai/openvoice?utm_source=chatgpt.com "myshell-ai/OpenVoice: Instant voice cloning by MIT and ..."

