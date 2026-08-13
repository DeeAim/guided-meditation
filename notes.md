
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
python render_meditation.py scripts/test.md --backend kokoro --voice bf_isabella --speed 0.85
python render_meditation.py scripts/test.md --backend kokoro --voice am_onyx --speed 0.90  (***)
python render_meditation.py scripts/test.md --backend kokoro --voice bm_lewis --speed 0.90

python render_meditation.py scripts/test-v2.md --backend kokoro --voice af_nicole --speed 0.90 (*****)
python render_meditation.py scripts/test-v2.md --backend kokoro --voice bf_isabella --speed 0.88 (**)
python render_meditation.py scripts/test-v2.md --backend kokoro --voice am_onyx --speed 0.90  (***)
python render_meditation.py scripts/test-v2.md --backend kokoro --voice bm_lewis --speed 0.90


### To test meditation speeds between 0.82–0.95
Don't immediately assume the slowest one will sound best. TTS voices can become unnatural when slowed too aggressively.


# 2. Meditation voice for kokoro-82M

https://voicerankings.com/voice/kokoro-82M/female

## af_nicole
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