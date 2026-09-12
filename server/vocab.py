"""Words the index can 'hear'. CLAP puts text and audio in one space, so a
track's vector can be read back as the phrases it sits closest to — the same
model that answers a search, run in reverse. Shown per result as "What the
index hears", so people learn which words find which sounds."""
GENRES = ["hip hop", "boom bap rap", "trap", "drill", "r&b", "neo soul", "soul", "funk", "disco", "house", "deep house", "tech house", "techno",
  "trance", "progressive house", "electro house", "big room edm", "dubstep", "drum and bass", "jungle", "uk garage", "breakbeat", "ambient", "downtempo",
  "trip hop", "lo-fi hip hop", "chillwave", "synthwave", "synth pop", "new wave", "post-punk", "indie rock", "alternative rock", "punk rock", "hardcore punk",
  "pop punk", "emo", "grunge", "classic rock", "hard rock", "heavy metal", "thrash metal", "death metal", "black metal", "metalcore", "progressive rock",
  "psychedelic rock", "shoegaze", "dream pop", "indie pop", "pop", "dance pop", "k-pop", "j-pop", "city pop", "reggaeton", "latin pop", "salsa", "cumbia",
  "bossa nova", "samba", "flamenco", "afrobeats", "amapiano", "highlife", "dancehall", "reggae", "dub", "ska", "country", "bluegrass", "americana", "folk",
  "singer-songwriter", "blues", "delta blues", "jazz", "bebop", "cool jazz", "jazz fusion", "smooth jazz", "big band swing", "gospel", "classical orchestra",
  "solo piano classical", "string quartet", "baroque", "opera", "film score", "video game music", "chiptune", "vaporwave", "hyperpop", "industrial",
  "ebm", "idm", "glitch", "experimental electronic", "noise", "drone", "new age", "meditation music", "children's music", "christmas music", "march", "polka"]
INSTRUMENTS = ["acoustic guitar", "nylon string guitar", "electric guitar", "distorted guitar", "slide guitar", "bass guitar", "slap bass", "synth bass",
  "808 bass", "piano", "electric piano", "rhodes", "organ", "synthesizer", "arpeggiated synth", "pad synth", "strings", "violin", "cello", "brass section",
  "trumpet", "saxophone", "flute", "clarinet", "harmonica", "accordion", "banjo", "mandolin", "ukulele", "harp", "sitar", "steel drums", "marimba",
  "vibraphone", "drum machine", "live drums", "breakbeat drums", "hand percussion", "congas", "tabla", "turntable scratching", "vinyl crackle", "choir",
  "vocoder", "autotuned vocals", "acapella"]
VOCALS = ["male vocals", "female vocals", "deep male voice", "high female voice", "falsetto", "rapping", "fast rapping", "spoken word", "screaming vocals",
  "whispered vocals", "harmonized vocals", "chanting", "no vocals, instrumental", "wordless vocals", "duet", "group vocals"]
MOODS = ["happy", "sad", "melancholic", "nostalgic", "dreamy", "hazy", "dark", "menacing", "aggressive", "angry", "euphoric", "uplifting", "triumphant",
  "romantic", "sensual", "sexy", "playful", "quirky", "epic", "cinematic", "tense", "eerie", "calm", "relaxing", "peaceful", "lonely", "bittersweet",
  "hopeful", "anthemic", "gritty", "warm", "cold", "spacey", "psychedelic", "hypnotic", "groovy", "funky", "bouncy", "smooth", "raw and lo-fi", "polished and glossy"]
TEMPO = ["very slow tempo", "slow tempo", "mid tempo", "upbeat", "fast tempo", "very fast", "driving beat", "four on the floor kick", "half-time groove",
  "swing rhythm", "shuffle", "syncopated", "steady pulse", "no beat, ambient"]
ERA = ["1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s", "vintage recording", "modern production"]
PRODUCTION = ["heavy bass", "huge bass drop", "sidechain pumping", "wall of reverb", "tape saturation", "clean and sparse", "dense and layered",
  "distorted", "lo-fi", "hi-fi", "acoustic and unplugged", "live concert recording", "studio recording", "loud and compressed", "quiet and intimate",
  "build-up and drop", "long intro", "breakdown", "sampled vocals chopped", "sample-based beat"]
VOCAB = GENRES + INSTRUMENTS + VOCALS + MOODS + TEMPO + ERA + PRODUCTION
GROUP = {t: g for g, ts in (("genre", GENRES), ("instrument", INSTRUMENTS), ("vocals", VOCALS), ("mood", MOODS), ("tempo", TEMPO), ("era", ERA), ("production", PRODUCTION)) for t in ts}
