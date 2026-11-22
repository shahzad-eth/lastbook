#!/usr/bin/env python3
"""Topic search beyond a-z: web/words.js run in Node, with Intl.Segmenter, without it, and with one that throws.

  python3 -B -m unittest app.tests.test_topic_search [-v]

Accented words stay whole and fold (niño finds nino), short words in Chinese, Hindi, Hebrew and Arabic count,
typed symbols never reach a RegExp, Turkish İ folds to i, and every English query in the list ranks exactly as it
did before. Words used outside the US (torch, rubbish, 999, 108, 1122, power cut, loadshedding, hydro, forest fire)
find the guide their US word finds. A search that finds nothing is tried again by word form (tourniquets,
fainting, choked). Needs Node on PATH; skipped without it. Never packaged."""
import json, re, shutil, subprocess, tempfile, unicodedata, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NODE = shutil.which('node')
WORDS = ROOT / 'web' / 'words.js'

# The stop words app.js passes in, read from app.js so the test follows it.
QSTOP = re.search(r"const QSTOP = new Set\('([^']*)'\.split", (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')).group(1).split(' ')
TOPICS = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((ROOT / 'content' / 'topics').glob('*.json'))]

# Everyday English questions. Each must give the same topics and choices as the old a-z matching,
# including words joined by punctuation, which the old split took apart.
ENGLISH = [
    'how do I purify water', 'boil water', 'is the tap water safe', 'bleach for drinking water', 'find water',
    'deep cut bleeding', 'broken leg', 'burn on my hand', 'cpr', 'choking', 'fever', 'dehydration', 'snake bite',
    'hypothermia', 'the power is out', 'generator', 'solar panel', 'car battery', 'earthquake', 'flood',
    'wildfire smoke', 'store food', 'cook without power', 'stay warm', 'shelter', 'toilet', 'radio',
    'grow vegetables', 'save seeds', 'first aid kit', "water's gone brown", "don't have power", "can't breathe",
    'how to start a fire', 'baby', 'medicine', 'keep food cold', 'clean water storage container',
    'water.boil', 'first_aid kit', 'e.coli', 'boil:water', 'https://example.org/water',
]

# Everyday words a guide covers, and the guide and choice search must show first, with and without Intl.Segmenter.
# Most found nothing or the wrong guide until the word was added to the hint of the choice that covers it. A word only
# in a topic's keywords is not enough: another word then picks the choice ("poisoned water" went to burns, for "hot water").
EVERYDAY = {
    'burned my hand': ['hurt', 'burn'], 'burnt': ['hurt', 'burn'],
    'fractured arm': ['hurt', 'bone'], 'dislocated shoulder': ['hurt', 'bone'], 'poisoned': ['hurt', 'poison'],
    'heatstroke': ['hurt', 'heatcold'], 'throwing up': ['hurt', 'diarrhea'], 'dehydrated': ['hurt', 'diarrhea'],
    'diarrhoea': ['hurt', 'diarrhea'], 'suicidal': ['health', 'mind'],
    'bushfire smoke': ['disaster', 'smoke'],
    'poisoned water': ['water', 'chemical'], 'drank poisoned water': ['water', 'chemical'],
    'dehydrated water': ['hurt', 'diarrhea'], 'throwing up water': ['hurt', 'diarrhea'], 'diarrhoea water': ['hurt', 'diarrhea'],
    'fractured neck': ['hurt', 'head'], 'fractured back': ['hurt', 'head'], 'dislocated neck': ['hurt', 'head'],
    'fractured skull': ['hurt', 'head'], 'fractured spine': ['hurt', 'head'], 'dislocated spine': ['hurt', 'head'],
    'spinal fracture': ['hurt', 'head'], 'fractured vertebra': ['hurt', 'head'], 'fractured vertebrae': ['hurt', 'head'],
    'vertebral fracture': ['hurt', 'head'], 'fractured vertebral column': ['hurt', 'head'],
    'I drank from the stream and have diarrhea': ['hurt', 'diarrhea'], 'I drank and feel dehydrated': ['hurt', 'diarrhea'],
}

# Injuries in a forest: since "forest fires" joined the wildfire hint, "forest" also picks wildfire, so these only have
# to show Broken bone somewhere in the results, not first.
LISTED = {
    'I fractured my arm in the forest': ['hurt', 'bone'], 'I dislocated my shoulder in the forest': ['hurt', 'bone'],
    'I had a fall in the forest': ['hurt', 'bone'],
}

# Query -> words, the same with or without Intl.Segmenter (every script here uses spaces).
WORDS_BOTH = {
    '¿Cómo purifico el agua para el niño?': ['como', 'purifico', 'agua', 'para', 'nino'],   # accents whole, then folded
    'niño': ['nino'],                                     # precomposed ñ
    'niño': ['nino'],                                    # n + combining tilde (NFD)
    'crème brûlée': ['creme', 'brulee'],        # every accent goes, not just the first
    "How do I purify water's taste?": ['purify', 'water', 'taste'],   # water's -> water, as before
    'don’t have water': ['water'],                         # curly apostrophe, stop words
    'ｗａｔｅｒ': ['water'],                # full-width Latin
    'water.boil first_aid e.coli boil:water': ['water', 'boil', 'first', 'aid', 'coli', 'boil', 'water'],
    'water­proof': ['water', 'proof'],                     # soft hyphen separates, as in FTS5
    'می‌خواهم': ['می', 'خواهم'],   # ZWNJ separates
    'आग אש دم': ['आग', 'אש', 'دم'],   # two-letter words without case
    'पानी उबालें': ['पानी', 'उबालें'],   # marks stay in words
    'ab 42 112 go': ['112'],                                    # short Latin words and numbers dropped, as before
    '\U00010428\U0001042f': [],                                # two letters outside the BMP: still two, still too short
    'c++ (water': ['water'],
    '[a': [], '(': [], '\\': [], '*?+{': [], '': [],            # symbols: no words, no exception
    'İstanbul': ['istanbul'],
    'éclair': ['eclair'],
}

FOLD = {
    'İstanbul': 'istanbul', 'ISTANBUL': 'istanbul', 'ılık': 'ılık',   # dotless ı stays
    'Straße': 'straße', 'ΣΟΦΟΣ': 'σοφοσ',   # ß stays, ς -> σ, as FTS5
    'ｗａｔｅｒ': 'water', 'niño': 'nino', 'niño': 'nino', 'Jalapeño': 'jalapeno',
    'καφές': 'καφέσ',   # Greek accents kept, as in FTS5
    'crème brûlée': 'creme brulee',
}

MATCH = [  # text, word, expected
    ['chocolate éclair', 'eclair', True], ['Chocolate Éclair', 'eclair', True],
    ['煮沸 水', '水', True], ['怎么净化水', '净化', True],
    ['drink water', 'rink', False], ['drink water', 'drin', True], ['Rainwater', 'water', False],
    ['Straße', 'strasse', False], ['ΣΟΦΟΣ', 'σοφοσ', True],
    ['İstanbul', 'istanbul', True], ['72-hour kit', 'hour', True], ['Water: purify, boil', 'purif', True],
]

# Words used outside the US, each with the US word the guides already had. A search for the first must give
# the same guides and choices, in the same order, as a search for the second.
SAME_AS = {
    'torch': 'flashlight', 'rubbish': 'garbage', 'rubbish pickup': 'trash pickup', 'tinned food': 'canned food',
    '999': '911', '112': '911', '111': '911', 'adrenaline': 'epinephrine',
    '108': '911', 'geyser': 'water heater',
    '1122': '911', '115': '911',   # Rescue 1122 and Edhi in Pakistan
}
# These sit in a guide's keywords only, so they open the same guide first but pick no choice of their own.
# In a hint, "bushfire" would also answer "bus" and "barbecue" would answer "bar" (a search word matches the
# start of a word), and "heatwave" or "sanitiser" beside the US spelling would read oddly.
SAME_GUIDE = {
    'bushfire': 'wildfire', 'bushfire smoke': 'wildfire smoke', 'heatwave': 'heat wave', 'barbecue': 'grill',
    'bbq': 'grill', 'sanitiser': 'sanitizer', 'hand sanitiser': 'hand sanitizer',
    'heatstroke': 'heat stroke',
    'snowstorm': 'winter storm', 'snow squall': 'winter storm', 'whiteout': 'winter storm',
    'polar vortex': 'winter storm', 'wind chill': 'winter storm', 'arctic outflow': 'winter storm',
    'warming centre': 'winter storm', 'aqhi': 'air quality', 'AQHI': 'air quality',
    'cooling centre': 'cooling center', 'washroom': 'sanitation',
    # Pakistan's scheduled power cuts. Written as one word in the keywords: "load shedding" as two would let
    # "shed" open the power guide, and "load" in a hint would take "generator load" away from the generator choice.
    'loadshedding': 'power cut', 'load shedding': 'power cut', 'load-shedding': 'power cut',
}
# Words used in South Asia and Canada with no single US twin among the guides: [guide, choice] that comes first.
FIRST = {
    'power cut': ['power', 'first-hours'], 'cyclone': ['disaster', 'flood'], 'monsoon': ['disaster', 'flood'],
    'borewell': ['water', 'outside'], 'tubewell': ['water', 'outside'], 'loose motions': ['hurt', 'diarrhea'],
    'hydro': ['power', 'first-hours'], 'hydro is out': ['power', 'first-hours'],
    'hydro outage': ['power', 'first-hours'], 'ice storm': ['shelter', 'cold'], 'freezing rain': ['shelter', 'cold'],
    'extreme cold': ['shelter', 'cold'], 'cold snap': ['shelter', 'cold'], 'blizzard': ['shelter', 'cold'],
    'furnace': ['shelter', 'cold'], 'furnace is out': ['shelter', 'cold'], 'frostnip': ['hurt', 'heatcold'],
    'forest fire': ['disaster', 'wildfire'], 'forest fires': ['disaster', 'wildfire'],
    'forest fire smoke': ['disaster', 'smoke'], 'Hydro': ['power', 'first-hours'], 'Frostnip': ['hurt', 'heatcold'],
    'cold': ['shelter', 'cold'], 'its cold': ['shelter', 'cold'],
    'house fire': ['disaster', 'home-fire'], 'my house is on fire': ['disaster', 'home-fire'],
    'smog': ['shelter', 'smoke'],   # winter smog in Lahore and Delhi; the choice cites a page on particles and ozone
}
# Words that a reading already cited under a choice is about, but that no title, keyword, label or hint held, so a search
# for them found nothing: [guide, choice] that comes first.
ALREADY_COVERED = {
    'pets': ['food', 'special'], 'propane': ['power', 'gas'], 'propane tank': ['power', 'gas'], 'dental': ['health', None],
}
# An emergency that happens to mention a new word still opens the urgent choice first, not the routine one the word was added to.
URGENT_FIRST = {
    'child unconscious after pet food': ['hurt', 'breathing'], 'child swallowed pet food': ['hurt', 'poison'],
}
# Searches the new words must not disturb: [guide, choice] that comes first.
UNDISTURBED = {
    'bus': ['disaster', 'no-car'], 'no bus': ['disaster', 'no-car'], 'bar soap': ['sanitation', 'hands'],
    'heat wave': ['shelter', 'heat'], 'grill': ['food', 'cook'], 'canned food': ['food', 'cook'],
    'cut': ['hurt', 'bleeding'], 'well': ['land', 'water-source'], 'storm': ['disaster', 'flood'],
    'ice': ['water', 'inhome'], 'micro-hydro': ['energy', None], 'wind': ['disaster', 'hurricane'],
    'winter storm': ['shelter', 'cold'], 'furnace smells like gas': ['power', 'gas'], 'gas furnace': ['power', 'gas'],
    'lost in the forest': ['comms', 'signal'],
    'baby formula': ['food', 'special'], 'food allergies': ['food', 'outage'], 'spoiled food': ['food', 'outage'],
    'pet food': ['food', 'outage'],
    'dentist': ['health', None], 'toothache': ['health', 'teeth'],
    'cold frame': ['repair', 'build'], 'freezing': ['shelter', 'cold'],
    'fire alarm': ['disaster', 'home-fire'], 'smoke alarm': ['disaster', 'home-fire'], 'smoke': ['disaster', 'smoke'],
    'fires after an earthquake': ['disaster', 'earthquake-after'],
    'shed': ['repair', None], 'generator load': ['power', 'generator'], 'air quality': ['shelter', 'smoke'],
}
# A search that names a sign of a life-threatening emergency shows that choice, even if another choice in the guide
# matches more words. The rest don't say the person isn't breathing or is unconscious, and keep their choice.
URGENT = {
    'burn and not breathing': ['hurt', 'breathing'], 'broken leg and not breathing': ['hurt', 'breathing'],
    'cut and not breathing': ['hurt', 'breathing'], 'fractured neck and not breathing': ['hurt', 'breathing'],
    'dislocated neck unconscious': ['hurt', 'breathing'], 'my baby stopped breathing': ['hurt', 'breathing'],
    "he isn't breathing": ['hurt', 'breathing'], 'choking': ['hurt', 'breathing'],
    'allergic reaction trouble breathing': ['hurt', 'allergy'], "can't breathe after a bee sting": ['hurt', 'allergy'],
    'gas burn': ['hurt', 'burn'], 'broken leg stuck under rubble': ['hurt', 'bone'],
    'wound infection not responding to antibiotics': ['hurt', 'bleeding'],
    'allergic reaction not responding to epinephrine': ['hurt', 'allergy'],
    'allergic reaction choking': ['hurt', 'allergy'], 'burn and choking on smoke': ['hurt', 'burn'],
}
# A breathing emergency after a sting must not open routine sting care.
NOT_STING = ["bee sting can't breathe", 'bee sting cannot breathe', 'bee sting unconscious', 'wasp sting unconscious']
TOPS = sorted({*SAME_AS, *SAME_AS.values(), *SAME_GUIDE, *SAME_GUIDE.values(), *FIRST, *ALREADY_COVERED, *URGENT_FIRST, *UNDISTURBED, *URGENT, *EVERYDAY, *LISTED, *NOT_STING})

# Words used in Thailand and Denmark. Emergency numbers find what 911 finds; haze, PM2.5 and cloudburst sit in a
# guide's keywords only and open the guide their US word opens. Thailand's fire number, 199, is left out: a fire
# number must not open first aid (as the UAE's 997 in #98).
TH_DK_SAME_AS = {'1669': '911', '191': '911', '1813': '911'}
NOT_FIRST_AID = ['199']
TH_DK_SAME_GUIDE = {'haze': 'air quality', 'PM2.5': 'air quality', 'pm2.5': 'air quality', 'cloudburst': 'flood'}
# Searches those words must not disturb: [guide, choice] that comes first.
TH_DK_UNDISTURBED = {'cloud': ['disaster', 'tornado'], 'funnel cloud': ['disaster', 'tornado'],
                     'burn': ['hurt', 'burn'], 'flood': ['disaster', 'flood'], 'mask': ['shelter', None]}
TOPS = sorted({*TOPS, *TH_DK_SAME_AS, *TH_DK_SAME_GUIDE, *TH_DK_SAME_GUIDE.values(), *TH_DK_UNDISTURBED,
              'burning', 'season', *NOT_FIRST_AID})

# A question about her ranks exactly as the same question about him. A guide word only has to start with a search
# word, so "she" found "shelter" and put Shelter in place first; "her" and "his" found "here" and "hissing".
SAME_FOR_HIM = {
    'she is bleeding': 'he is bleeding', "she can't breathe": "he can't breathe", 'is she breathing': 'is he breathing',
    'she is choking': 'he is choking', 'she fell and hit her head': 'he fell and hit his head',
    'she burned her hand': 'he burned his hand', 'she has a fever': 'he has a fever',
    'her arm is bleeding': 'his arm is bleeding',
}
# Typing "shelter" still finds it from "shel": [guide, choice] that comes first.
STILL_SHELTER = {'shel': ['disaster', 'shelter-in-place'], 'shelter': ['disaster', 'shelter-in-place'],
                 'shelter in place': ['disaster', 'shelter-in-place']}
TOPS = sorted({*TOPS, *SAME_FOR_HIM, *SAME_FOR_HIM.values(), *STILL_SHELTER})

# A made-up topic in Spanish and Chinese: found by Spanish words and by a single Han character.
OWN = {'id': 'own', 'title': 'Agua potable', 'short': 'Hervir el agua', 'keywords': ['水'], 'choices': []}
RANK_OWN = [['agua', [OWN]], ['水', [OWN]], ['hervir', [OWN]]]

# Emergencies where the first choice decides what someone reads first. A cardiac arrest needs CPR, not the
# long-term care guide that "heart" also matches: [guide, choice] that comes first.
EMERGENCY_FIRST = {
    'cardiac arrest': ['hurt', 'breathing'], 'heart stopped': ['hurt', 'breathing'], 'AED': ['hurt', 'breathing'],
    'aed': ['hurt', 'breathing'], 'defibrillator': ['hurt', 'breathing'], 'heart attack': ['hurt', 'sudden'],
    'having a heart attack': ['hurt', 'sudden'], 'signs of heart attack': ['hurt', 'sudden'],
}
# Searches those words must not disturb: [guide, choice] that comes first.
EMERGENCY_UNDISTURBED = {
    'heart': ['health', 'chronic'], 'heart disease': ['health', 'chronic'], 'blood pressure': ['health', 'chronic'],
    'chest pain': ['hurt', 'sudden'], 'collapsed': ['hurt', 'breathing'], 'not breathing': ['hurt', 'breathing'],
    'drowning': ['hurt', 'breathing'], 'cpr': ['hurt', None], 'stopped': ['disaster', 'earthquake-after'],
}
TOPS = sorted({*TOPS, *EMERGENCY_FIRST, *EMERGENCY_UNDISTURBED})

# Labor in the words people type. One word at a time, "water broke" found unsafe tap water, "the baby is coming" a
# hurricane and "contractions" nothing: [guide, choice] that comes first.
PREGNANT = ['health', 'pregnant']
LABOR = {q: PREGNANT for q in [
    'my water broke', 'water broke', 'her water broke', 'my water just broke', 'waters broke', 'her waters have broken',
    'the baby is coming', 'baby is coming', "the baby's coming", 'how to deliver a baby', 'delivering a baby at home',
    'giving birth at home', 'going into labour', 'in labour', 'contractions', 'having contractions',
    'contractions 5 minutes apart', 'childbirth', 'umbilical cord', 'cut the umbilical cord',
    'giving birth', 'in labor', 'going into labor',
    "my wife's water broke", 'wifes water broke', 'water broke 2 hours ago', 'contractions 5 mins apart',
    'contractions every 3 minutes', 'baby crowning', 'labour pains', 'umbilical cord around neck',
    'labour started at home', 'water broke call 911', 'contractions every five minutes', 'water broke pregnancy',
]}
# The same words about something else keep their first result; Not breathing still comes first.
NOT_LABOR = {
    'water main broke': ['water', 'unsafe'], 'water pipe broke': ['water', 'unsafe'], 'broke water heater': ['water', 'unsafe'],
    'baby choking': ['hurt', 'breathing'], 'baby not breathing': ['hurt', 'breathing'], 'baby fever': ['health', 'start'],
    'child not breathing': ['hurt', 'breathing'], 'hurricane coming': ['disaster', 'hurricane'],
    'extension cord': ['power', 'generator'], 'apartment': ['disaster', 'highrise-fire'],
    'unconscious and in labor': ['hurt', 'breathing'], 'water broke and she is unconscious': ['hurt', 'breathing'],
    'water has broken through the wall': ['water', 'unsafe'], 'our water has broken': ['water', 'unsafe'],
    'our water is broken': ['water', 'unsafe'], 'giving birth control pills': ['health', 'medicine'],
    'contractions while having a seizure': ['hurt', 'sudden'], 'cut head having a baby': ['hurt', 'bleeding'],
    'contractions in my neck': ['hurt', 'head'],
}
# A labor phrase among other words keeps its other meaning: the pregnancy choice must not come first.
NOT_LABOR_FIRST = [
    'minutes apart', 'take medicine 30 minutes apart', 'seizures 5 minutes apart', 'baby is coming down with a fever',
    'the baby is coming home from the hospital', 'baby coming in and out of consciousness', 'baby coming out of the car',
    'deliver the baby formula', 'deliver a baby goat', 'my water broke down', "grandma's water has broken",
    "the city's water broke down", 'premature ventricular contractions', 'spasms and contractions in the neck',
    'cramps and contractions every few minutes apart in legs', 'childbirth class', 'lightning baby is coming',
    'labour hours', 'labour help', 'need labour fast', 'labour first time', 'his water just broke', 'our water just broke',
    'deliver the baby to me', 'baby coming with me', 'baby coming from the hospital', 'water broke up',
    'the water just broke', 'water broke in the car', "the hospital's water has broken", 'emergency water broke',
    'the cord came out', 'the power cord came out', 'phone cord came out', 'the baby is coming from the hospital',
    'the baby is coming with her', 'water broke in the house', 'the baby is coming to my moms house',
    "the baby is coming to my mom's tonight", 'deliver the baby to her', 'contractions around the neck',
    'cord around neck', 'cord around the babys neck', 'baby is coming to the hospital now',
]
# A labor phrase lists only guides that find the search's other words: none here, so the pregnancy choice alone.
LABOR_ALONE = ['deliver a baby 108', 'contractions 5 minutes apart 108', 'someone is giving birth', 'giving birth care', 'contractions after birth', 'in labour after prenatal care']
# Bleeding in labor opens the pregnancy choice, whose readings cover it, but Bleeding stays in the list.
LABOR_BLEEDING = ['umbilical cord bleeding', 'contractions and bleeding', 'childbirth bleeding',
                  'my water broke and she is bleeding', 'bleeding alone right now last night contractions']
# Everyday wording (second review): filler and question words, people, places, and each moment of a birth.
LABOR_EVERYDAY = [
    'my water broke what should I do', 'her water broke we are at home', "my wife's water broke we're at home",
    'my water broke and im scared', 'my water broke but no contractions', 'i think my water just broke',
    'my waters have gone', 'did my water break or did i pee', 'our baby is coming', 'the baby is coming and no one can come',
    'baby on the way', 'contractions are 4 min apart', 'contractions 10 minutes apart should we go to the hospital',
    'contractions in my back', 'how do i know if im in labor', "i'm in labor and i don't know what to do",
    'going through labor at home alone', 'baby is crowning what do i do', 'baby born at home',
    'the head is out what now', 'baby is breech', 'how to cut the umbilical cord', "placenta won't come out", 'bloody show',
    'how to give birth at home', 'my water broke during the hurricane', 'my water broke and the power is out',
    'in labour no midwife', 'labour pains every 5 minutes', "she's about to give birth", 'had the baby at home what now',
    'MY WATER BROKE!!!', 'my water broke in the bathroom', 'my sisters water broke', 'pregnant during the flood',
    'my water broke what am i supposed to do', 'her water broke we r at home', 'pretty sure my water broke',
    'my water broke now she is pushing', 'baby is coming out of her', 'what to do when your water breaks',
    'her water broke in the car', 'my water broke at work',
    'going through labour', 'her waters break', 'labor pain relief', "contractions won't stop", 'the cord came out first',
    'labour has started', 'signs of labour',
    'my water broke what should i bring', 'her water broke we are at a friends house',
    'her water broke and we live far from the hospital', "her water broke we can't reach the hospital",
]
# Every phrase of the pregnancy choice opens it on its own. Next to a life threat, the first guide is the one the search
# gets with the choice's phrase fields taken out: a phrase never changes what comes first (Breathing, Bleeding, or
# whatever main shows, even when that is not first aid).
PREGNANT_CHOICE = next(c for t in TOPICS if t['id'] == 'health' for c in t['choices'] if c['id'] == 'pregnant')
PHRASES_ALONE = [*PREGNANT_CHOICE['phrases'], *PREGNANT_CHOICE.get('weak', []),
                 *(f'my {p}' for p in PREGNANT_CHOICE.get('weak', []) if p.startswith('water'))]
THREATS = ['not breathing', 'unconscious', 'choking', 'having a seizure', 'chest pain', 'bleeding heavily',
           'heavy bleeding', 'a lot of blood', "bleeding won't stop", 'bleeding wont stop', "won't stop bleeding",
           'overdose', 'poisoned']
PHRASE_THREATS = sorted({f'{p} {t}' for p in PHRASES_ALONE for t in THREATS} | {f'{t} {p}' for p in PHRASES_ALONE[::7] for t in THREATS})
PLAIN_TOPICS = [{**t, 'choices': [{k: v for k, v in c.items() if k not in ('phrases', 'weak', 'who', 'context', 'unless', 'alongside')}
                                  for c in t.get('choices', [])]} for t in TOPICS]
NOT_LABOR_NOWHERE = ['delivery', 'deliver food', 'baby formula', 'minutes', 'power cord']   # no pregnancy guide for these
TOPS = sorted({*TOPS, *LABOR, *NOT_LABOR, *NOT_LABOR_NOWHERE, *NOT_LABOR_FIRST, *LABOR_BLEEDING, *LABOR_ALONE,
               *LABOR_EVERYDAY, *PHRASES_ALONE,
               *PHRASE_THREATS})

# A guide whose urgent phrase the search names comes first, even when the other words pull another guide ahead or
# below the cut; that guide is still offered: query -> (first row, a row that must still be shown).
GUIDE_URGENT = {
    'unconscious in the flood water': (['hurt', 'breathing'], ['water', 'unsafe']),
    'unconscious after drinking flood water': (['hurt', 'breathing'], ['water', 'unsafe']),
    'not breathing after falling in the well water': (['hurt', 'breathing'], ['land', 'water-source']),
    'unconscious after the generator ran indoors': (['hurt', 'breathing'], ['shelter', 'co']),
    'child unconscious after pet food': (['hurt', 'breathing'], None), 'pet food unconscious': (['hurt', 'breathing'], None),
}
# Searches without an urgent phrase keep their guide order: [guide, choice] that comes first.
GUIDE_ORDINARY = {
    'how do i light a campfire': ['power', 'first-hours'], 'treat water': ['water', 'keepclean'],
    "make the water safe for a baby's formula": ['food', 'outage'], 'not responding to antibiotics': ['health', 'medicine'],
    'radio not responding': ['comms', 'alerts-radio'], 'dental abscess': ['health', 'teeth'], 'propane burns': ['hurt', 'shock'],
}
TOPS = sorted({*TOPS, *GUIDE_URGENT, *GUIDE_ORDINARY})
# Cardiac arrest is urgent too: "heart stopped" in a search with other words still opens CPR first, and the guide
# those words point to is still offered: query -> (first row, a row that must still be shown).
HEART_URGENT = {
    'heart stopped in the flood water': (['hurt', 'breathing'], ['water', 'unsafe']),
    'heart stopped after drinking flood water': (['hurt', 'breathing'], ['water', 'unsafe']),
    'heart stopped after the generator ran indoors': (['hurt', 'breathing'], ['shelter', 'co']),
    'her heart has stopped': (['hurt', 'breathing'], None), 'cardiac arrest in the flood water': (['hurt', 'breathing'], None),
}
# Searches with "heart" or "stopped" but no cardiac arrest keep their first row.
HEART_ORDINARY = {
    'heart attack': ['hurt', 'sudden'], 'heart attack after shoveling snow': ['hurt', 'sudden'],
    'heart disease': ['health', 'chronic'], 'the generator stopped': ['power', 'generator'],
    'water heater stopped': ['water', 'inhome'],
}
TOPS = sorted({*TOPS, *HEART_URGENT, *HEART_ORDINARY})

# Another form of a word a guide already has: a plural, -ed or -ing. Alone, each found nothing, because a typed word
# must start a guide's word and "tourniquets" is longer than "tourniquet". A search for the first must give the same
# guides and choices, in the same order, as a search for the second.
FORMS = {
    'tourniquets': 'tourniquet', 'fainting': 'fainted', 'choked': 'choking', 'choke': 'choking',
    'drowned': 'drowning', 'bleeds': 'bleeding', 'wounds': 'wound', 'seizures': 'seizure', 'snakes': 'snake',
    'bees': 'bee', 'earthquakes': 'earthquake', 'evacuating': 'evacuate', 'boiled': 'boil', 'filters': 'filter',
}
# Whole searches in which no word starts a guide's word: [guide, choice] that comes first.
FORMS_FIRST = {
    'he is fainting': ['hurt', 'breathing'], 'kid choked on a grape': ['hurt', 'breathing'],
    'applying tourniquets': ['hurt', 'bleeding'], 'swarm of bees': ['hurt', 'sting'],
}
TOPS = sorted({*TOPS, *FORMS, *FORMS.values(), *FORMS_FIRST})

# The rule itself, on made-up topics so it doesn't depend on what the guides say: query -> ids found, in order.
# Only a search that finds nothing is tried by form, so "baby choked" still gives what "baby" gives.
FORM_TOPICS = [
    {'id': 'words', 'title': 'Tourniquet, fainted, choking, stopped, batteries, stitches', 'short': 'A plan for incoming missiles',
     'keywords': ['can', 'bee'], 'choices': []},
    {'id': 'baby', 'title': 'Baby care', 'short': 'Feeding', 'keywords': [], 'choices': []},
]
RANK_FORMS = {
    'tourniquets': ['words'], 'fainting': ['words'], 'faints': ['words'], 'choked': ['words'], 'choke': ['words'],
    'stopping': ['words'], 'battery': ['words'], 'stitching': ['words'], 'plans': ['words'], 'planning': ['words'],
    'bees': ['words'], 'missile': ['words'], 'he is fainting': ['words'], 'babies': ['baby'],
    'missing': [], 'planes': [], 'cans': [], 'stung': [],         # not missiles, not a plan, "can" is a stop word, irregular
    'baby': ['baby'], 'baby choked': ['baby'], 'choked baby': ['baby'], 'feeding tourniquets': ['baby'],
}

CASES = {
    'stop': QSTOP, 'fold': list(FOLD), 'match': [m[:2] for m in MATCH], 'rank': ENGLISH, 'topics': TOPICS,
    'rankOwn': RANK_OWN, 'rankForms': [[q, FORM_TOPICS] for q in RANK_FORMS],
    'words': list(WORDS_BOTH) + ['怎么净化水', '水をきれいにする方法',
                                 '물 끓이기', 'น้ำ'],
    'tops': TOPS,
}

CASES.update(topsPlain=PHRASE_THREATS, plainTopics=PLAIN_TOPICS)   # the same searches without the phrase fields


def run(mode):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'cases.json'
        p.write_text(json.dumps(CASES, ensure_ascii=False), encoding='utf-8')
        r = subprocess.run([NODE, str(HERE / 'topic_search_test.mjs'), str(WORDS), str(p), mode],
                           capture_output=True, text=True, encoding='utf-8', timeout=60)
    if r.returncode:
        raise AssertionError(r.stderr[-1500:])
    return json.loads(r.stdout)


def ok(entry):
    if 'error' in entry:
        raise AssertionError(entry['error'])
    return entry['ok']


@unittest.skipUnless(NODE, 'needs node on PATH')
class TopicSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seg, cls.wk, cls.fb, cls.thr = run('segmenter'), run('webkit'), run('fallback'), run('throwing')
        cls.modes = (cls.seg, cls.wk, cls.fb, cls.thr)

    def words(self, r):
        return dict(zip(CASES['words'], (ok(e) for e in r['words'])))

    def test_modes(self):
        self.assertTrue(self.seg['segmenter'])
        self.assertTrue(self.wk['segmenter'])
        self.assertFalse(self.fb['segmenter'])
        self.assertFalse(self.thr['segmenter'])
        self.assertEqual(self.thr, self.fb)                       # a throwing Segmenter falls back cleanly

    def test_fold(self):
        for r in self.modes:
            self.assertEqual(dict(zip(FOLD, r['fold'])), FOLD)

    def test_turkish_i_order(self):
        # Shows why the order matters: removing marks from NFC "İ" finds none, and lower-casing it afterwards
        # leaves "i" + U+0307, which no longer matches "istanbul". The fold assertions check words.js itself.
        marks_first = ''.join(ch for ch in unicodedata.normalize('NFC', 'İ') if not unicodedata.combining(ch)).lower()
        self.assertEqual(marks_first, 'i̇')
        for r in self.modes:
            self.assertEqual(r['fold'][0], 'istanbul')

    def test_query_words(self):
        for r in self.modes:
            w = self.words(r)
            for q, expect in WORDS_BOTH.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(w[q], expect)

    def test_scripts_without_spaces(self):
        for r in (self.seg, self.wk):
            w = self.words(r)
            zh = w['怎么净化水']
            self.assertEqual(''.join(zh), '怎么净化水')      # nothing dropped
            self.assertTrue(all(1 <= len(x) <= 2 for x in zh))                  # one- and two-character words count
            ja = w['水をきれいにする方法']
            self.assertIn('水', ja)
            self.assertIn('方法', ja)
            self.assertIn('물', w['물 끓이기'])              # Korean 물 (water), one syllable
            self.assertTrue(w['น้ำ'])                            # Thai น้ำ (water)
        for r in (self.fb, self.thr):                                           # no segmenter: the run stays whole
            self.assertEqual(self.words(r)['怎么净化水'], ['怎么净化水'])

    def test_match(self):
        for r in self.modes:
            self.assertEqual([ok(e) for e in r['match']], [m[2] for m in MATCH])

    def test_emergency_words_open_first_aid(self):
        for r in self.modes:
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            for q, first in [*EMERGENCY_FIRST.items(), *EMERGENCY_UNDISTURBED.items()]:
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], [first])   # an empty result fails, not errors

    def test_rank_non_english_topic(self):
        for r in self.modes:
            self.assertEqual([ok(e) for e in r['rankOwn']], [[['own', None]]] * 3)

    def test_everyday_words_find_their_guide(self):
        for r in self.modes:
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            for q, first in EVERYDAY.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][0] if top[q] else None, first)
            for q, choice in LISTED.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertIn(choice, top[q])

    def test_english_ranks_as_before(self):
        for r in self.modes:
            for case in r['rank']:
                with self.subTest(q=case['q'], segmenter=r['segmenter']):
                    self.assertEqual(ok(case['now']), case['before'])
        self.assertGreater(sum(1 for c in self.seg['rank'] if c['before']), 30)   # the list does reach the guides

    def test_words_used_in_thailand_and_denmark(self):
        for r in self.modes:
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            for q, us in TH_DK_SAME_AS.items():
                with self.subTest(q=q, us=us, segmenter=r['segmenter']):
                    self.assertTrue(top[us])
                    self.assertEqual(top[q], top[us])
            for q, us in TH_DK_SAME_GUIDE.items():
                with self.subTest(q=q, us=us, segmenter=r['segmenter']):
                    self.assertTrue(top[q])
                    self.assertEqual(top[q][0][0], top[us][0][0])
            for q, first in TH_DK_UNDISTURBED.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], [first])
            # "burning season" was left out for these two, so neither opens the shelter guide on its own. "burning"
            # is now found by word form, where "burned" already was.
            for q, found in (('burning', [['hurt', 'burn']]), ('season', [])):
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q], found)
            for q in NOT_FIRST_AID:                             # a fire number does not open the hurt guide
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertNotIn('hurt', [guide for guide, _ in top[q]])

    def test_words_used_outside_the_us(self):
        for r in self.modes:
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            for q, us in SAME_AS.items():
                with self.subTest(q=q, us=us, segmenter=r['segmenter']):
                    self.assertTrue(top[us])                       # the US word does find a guide
                    self.assertEqual(top[q], top[us])
            for q, us in SAME_GUIDE.items():
                with self.subTest(q=q, us=us, segmenter=r['segmenter']):
                    self.assertTrue(top[q])
                    self.assertEqual(top[q][0][0], top[us][0][0])
            for q, first in [*FIRST.items(), *ALREADY_COVERED.items(), *URGENT_FIRST.items(), *UNDISTURBED.items()]:
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][0], first)

    def test_other_forms_of_a_word(self):
        for r in self.modes:
            found = dict(zip(RANK_FORMS, ([row[0] for row in ok(e)] for e in r['rankForms'])))
            for q, ids in RANK_FORMS.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(found[q], ids)
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            for q, word in FORMS.items():
                with self.subTest(q=q, word=word, segmenter=r['segmenter']):
                    self.assertTrue(top[word])                     # the guide's own word does find a guide
                    self.assertEqual(top[q], top[word])
            for q, first in FORMS_FIRST.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], [first])

    def test_urgent_choice_wins(self):
        for r in self.modes:
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            for q, first in URGENT.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][0] if top[q] else None, first)

    def test_breathing_after_a_sting(self):
        for r in self.modes:
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            for q in NOT_STING:
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertTrue(top[q])
                    self.assertNotIn(['hurt', 'sting'], top[q])

    def test_urgent_guide_comes_first(self):
        for r in self.modes:
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            for q, (first, offered) in GUIDE_URGENT.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], [first])
                    if offered:
                        self.assertIn(offered, top[q])
                    self.assertLessEqual(len(top[q]), 3)
            for q, first in GUIDE_ORDINARY.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], [first])

    def test_heart_stopped_is_urgent(self):
        for r in self.modes:
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            for q, (first, offered) in HEART_URGENT.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], [first])
                    if offered:
                        self.assertIn(offered, top[q])
            for q, first in HEART_ORDINARY.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], [first])


    def test_her_ranks_as_him(self):
        for r in self.modes:
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            for q, him in SAME_FOR_HIM.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertTrue(top[him])                      # the question about him does find a guide
                    self.assertEqual(top[q], top[him])
            for q, first in STILL_SHELTER.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], [first])

    def test_labor_finds_the_pregnancy_guide(self):
        for r in self.modes:
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            for q, first in {**LABOR, **NOT_LABOR}.items():
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], [first])
            for q in NOT_LABOR_NOWHERE:
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertNotIn(PREGNANT, top[q])
            for q in NOT_LABOR_FIRST:
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertNotEqual(top[q][:1], [PREGNANT])
            for q in LABOR_BLEEDING:
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], [PREGNANT])
                    self.assertIn(['hurt', 'bleeding'], top[q])
            for q in LABOR_ALONE:
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q], [PREGNANT])
            for q in [*LABOR_EVERYDAY, *PHRASES_ALONE]:
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], [PREGNANT])

    def test_labor_and_labour_alike(self):
        # Every phrase spelled one way has its twin in the other spelling.
        for field in ('phrases', 'weak'):
            entries = set(PREGNANT_CHOICE.get(field, []))
            for p in entries:
                twin = p.replace('labour', 'labor') if 'labour' in p else p.replace('labor', 'labour')
                with self.subTest(field=field, phrase=p):
                    self.assertIn(twin, entries)

    def test_context_never_holds_a_life_threat(self):
        # A word in "context" lets a phrase count next to it, so a life threat there would put the pregnancy choice
        # ahead of first aid. The main words of every urgent phrase ("breathing", not "out"), and these, stay out.
        threats = {w for t in TOPICS for c in t.get('choices', []) for u in c.get('urgent', []) for w in u.split()
                   if len(w) > 3 and w not in ("isn't", 'isnt')}
        threats |= {'bleeding', 'blood', 'loss', 'weak', 'moving', 'limp', 'heavily', 'heavy', 'hemorrhage',
                    'haemorrhage', 'seizure', 'fitting', 'convulsing', 'choking', 'breathe', 'pulse', 'chest',
                    'overdose', 'poison', 'poisoned', 'shock', 'faint', 'fainted', 'blue', 'pale', 'stroke'}
        for entry in [*PREGNANT_CHOICE.get('context', []), *PREGNANT_CHOICE.get('alongside', [])]:
            with self.subTest(entry=entry):
                self.assertFalse(set(entry.split()) & threats)

    def test_a_life_threat_ranks_as_without_phrases(self):
        for r in self.modes:
            top = dict(zip(TOPS, (ok(e) for e in r['tops'])))
            plain = dict(zip(PHRASE_THREATS, (ok(e) for e in r['topsPlain'])))
            for t in THREATS:
                with self.subTest(q=t, segmenter=r['segmenter']):
                    self.assertTrue(plain[f'{PHRASES_ALONE[0]} {t}'])
            for q in PHRASE_THREATS:
                with self.subTest(q=q, segmenter=r['segmenter']):
                    self.assertEqual(top[q][:1], plain[q][:1])

if __name__ == '__main__':
    unittest.main()
