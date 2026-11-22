# Curated topic files (`content/topics/<id>.json`)

Each file is one "need" in the app. The app shows, in order:
1. the title and a one-sentence intro,
2. **choices** ("What's happening?") — the person taps one situation and sees 1–4 recommended readings for it,
3. **limits** — when the source itself says to stop, get help, or that a professional/trained person is needed,
4. **prepare** — readings for getting ready before it happens,
5. **learn** — full manuals, videos, encyclopedia articles for deeper study,
6. for learning tracks, an ordered **route** of beginner-to-advanced steps.

Source facts (publisher, edition, date, file type, page count, video length, transcript) are filled in
automatically from `catalog.json` — do not copy them into the topic file.

```json
{
  "id": "water",
  "mode": "now",                     // "now" = urgent need, "learn" = longer-term learning track
  "title": "Get safe drinking water",
  "short": "Treat, store and find water",
  "intro": "One or two plain sentences in your own words. Describe what this section helps with; do not give procedures.",
  "keywords": ["water", "boil", "bleach", "purify", "filter", "thirsty", "drinking"],
  "choices": [
    {
      "id": "unsafe",
      "label": "Tap water is off or might be unsafe",
      "hint": "Boil-water notice, earthquake, flood, broken main",
      "urgent": ["not breathing"],     // optional: a search that names one of these phrases shows this guide and choice first
      "phrases": ["in labor"],         // optional: a search that names one of these phrases counts its words for this choice
      "context": ["minutes"],          // optional, with phrases: other words a search may hold for a phrase to count
      "weak": ["water broke"],         // optional: like phrases, but never next to alongside words
      "who": ["my"],                   // optional, with weak: a weak phrase right after one of these is a full phrase
      "unless": ["our water"],         // optional, with phrases: a search that names one of these is not this choice
      "alongside": ["flood"],          // optional, with phrases: places and disasters; their guides stay listed
      "read": [
        {"doc": "<catalog id>", "page": 9,
         "label": "Short action-style headline of what the page helps with",
         "note": "What the reader will find on that page, <= 30 words, describing (not prescribing)."}
      ]
    }
  ],
  "limits": [
    {"text": "Faithful short paraphrase of a limit/warning/when-to-get-help statement from the source.",
     "doc": "<catalog id>", "page": 12}
  ],
  "prepare": [ {"doc": "...", "page": 21, "label": "...", "note": "..."} ],
  "learn":   [ {"doc": "...", "label": "...", "note": "..."},
               {"zim": "zim/<file>.zim/<Article_path>", "title": "Article title", "label": "...", "note": "..."} ],
  "route": [
    {"title": "Step 1: ...", "goal": "What the step is for, in plain words",
     "read": [ {"doc": "...", "page": 3, "label": "...", "note": "..."} ]}
  ],
  "related": ["sanitation", "food"]
}
```

Rules
- Every `doc` must be a real catalog id (not a `metadata-video-*` id). `page` is the PDF *file* page (1-based) as used by
  `libq.py page`; omit it for html/video/whole-document references. Verify each page by reading it.
- Use a video's own id (`video-...`) for videos. Prefer videos with captions/transcripts and reputable publishers.
- `label`/`note`/`intro`/`hint` are plain-language descriptions written for a stressed non-expert. They may describe what a
  page contains, but must not add steps, doses, quantities or advice that the page does not say.
- `limits` must be traceable to the cited page. Paraphrase faithfully; keep any quote under 15 words.
- Medical, chemical (bleach, fuels, pesticides), electrical and gas items: prefer current WHO/CDC/EPA/FEMA/Red Cross/
  Hesperian/MSF/USDA/extension sources; mention in `note` if a source is old (e.g. 1980s civil defense) or written for
  health workers or trained responders.
- `urgent` is only for a life-threatening choice that must win over any other choice in its topic. When a search names
  one of its phrases, that choice is shown for its topic and the topic is listed first, ahead of guides that matched more
  words and even below the usual 60% cut; the other guides that pass the cut follow in their usual order, at most three
  rows in all. A search that names no `urgent` phrase is ranked exactly as without the field. Each phrase is matched as
  whole words in order, so "not breathing" does not catch "trouble breathing".
- Favour fewer, better items: 1–4 readings per choice, 3–8 in prepare, 4–10 in learn.
- `phrases` is for a wording whose single words point somewhere else ("my water broke" is labor, not tap water). A
  phrase counts only in context: the search names it as whole words in order, names no `unless` entry ("our water",
  "baby coming home"), and every other word is everyday (the search's stop words, `PLAIN` in `web/words.js`, which
  every choice shares, or a number such as "5" or "5mins"), part of a `context` entry the search names ("minutes",
  "home"), a word of the choice's label or hint, or, next to a full phrase only, an `alongside` word. Then the choice and its topic come first, after any `urgent` guide, and
  a guide whose shown choice finds a label, hint or `alongside` word ("bleeding", "flood") stays listed below it, even
  under the 60% cut; `context` words keep no other guide listed, so put label and hint words that name nothing else
  ("someone", "after", "care") in `context` too. Any other word ("fever", "pipe", "goat", "down") leaves the
  search ranked exactly as without the fields, so a word nobody foresaw falls back instead of opening the choice.
- `weak` is for a phrase that also means something else on its own ("water broke", "crowning"). It counts like a
  phrase, but not next to `alongside` words: "water broke what now" opens the choice, "water broke in the kitchen"
  does not. Right after a `who` entry ("my", "her", "wife s") a weak phrase is a full phrase, so "my water broke in
  the kitchen" opens the choice. Put places and disasters in `alongside`, not `context`, so that only a full phrase
  can stand next to them. `context` and `unless` entries match as whole phrases ("our water"); `alongside` entries
  match word by word.
- Before adding to or removing from any of these lists, try the entry in at least five searches where it means
  something else (medicine "minutes apart", plumbing "our water has broken", a baby "coming down with a fever", "push
  the car"), and keep those meanings in `unless`. Never add a life threat ("heavily", "chest", "seizure", "weak") to
  `context` or `alongside`. The tests check this, check every phrase on its own and next to each life threat, and
  check that "labor" and "labour" phrases come in pairs.
