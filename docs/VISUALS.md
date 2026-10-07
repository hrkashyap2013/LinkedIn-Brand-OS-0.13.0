# Visual reference

How the diagram generator turns a short JSON spec into an exact, editable SVG (and PNG or PDF through Chrome or Edge).

You normally never write these by hand: the agents write them, you pick one of 3 previews, and the generator draws exactly those words. This page is for when you want to edit a spec yourself or understand a warning.

## Formats

| Format | Size | Output |
|---|---|---|
| portrait (default) | 1080 x 1350 px | SVG, PNG |
| square | 1080 x 1080 px | SVG, PNG |
| carousel | pages of 1080 x 1350 px | one SVG per slide, and one PDF with a page per slide |

PNG and PDF are made with Google Chrome or Microsoft Edge, if one is installed (or set `LBA_BROWSER` to the full path of a Chromium-based browser). With none, you still get the SVG and an `.html` page you can open and print to PDF.

## Every spec

Every spec: type, title (the one-sentence takeaway), subtitle?, takeaway? (one bottom line), source?, alt? (override alt text). Use the owner's approved words only; never invent numbers. A carousel is {type: 'carousel', title, slides: [cover, ...diagram specs..., closing]}.

## The 10 diagram types

### process_flow (process flow)

steps: [{label, detail?}] (3-6); emphasis: step number starting at 0 (optional)

```json
{
  "type": "process_flow",
  "title": "From vague goal to a plan you can start Monday",
  "steps": [
    {
      "label": "Name the outcome",
      "detail": "One sentence, measurable"
    },
    {
      "label": "List the blockers",
      "detail": "Only the real ones"
    },
    {
      "label": "Pick one lever",
      "detail": "The change that unlocks the rest"
    },
    {
      "label": "Schedule the first step",
      "detail": "Put it on the calendar"
    }
  ],
  "emphasis": 2,
  "takeaway": "Small plans get done."
}
```

### matrix_2x2 (2x2 matrix)

x_axis & y_axis: {label, low, high}; quadrants: 4 x {label, detail?} in the order top-left, top-right, bottom-left, bottom-right; emphasis: 0-3

```json
{
  "type": "matrix_2x2",
  "title": "Where to spend your next hour",
  "x_axis": {
    "label": "Effort",
    "low": "Low",
    "high": "High"
  },
  "y_axis": {
    "label": "Impact",
    "low": "Low",
    "high": "High"
  },
  "quadrants": [
    {
      "label": "Quick wins",
      "detail": "Do first"
    },
    {
      "label": "Big bets",
      "detail": "Plan carefully"
    },
    {
      "label": "Fill-ins",
      "detail": "Only if free"
    },
    {
      "label": "Time sinks",
      "detail": "Avoid"
    }
  ],
  "emphasis": 0
}
```

### comparison_table (comparison table)

columns: 2-4 names; rows: [{label, values: [one per column]}] (up to 6); emphasis: column number starting at 0

```json
{
  "type": "comparison_table",
  "title": "Two ways to run a weekly review",
  "columns": [
    "Ad hoc",
    "Structured"
  ],
  "rows": [
    {
      "label": "Prep time",
      "values": [
        "None",
        "10 minutes"
      ]
    },
    {
      "label": "Consistency",
      "values": [
        "Varies",
        "Same every week"
      ]
    },
    {
      "label": "Follow-through",
      "values": [
        "Often missed",
        "Tracked"
      ]
    }
  ],
  "emphasis": 1
}
```

### cycle (cycle)

steps: [{label, detail?}] (3-6, drawn clockwise from the top); center: short text (optional); emphasis: step number

```json
{
  "type": "cycle",
  "title": "The learning loop that keeps teams improving",
  "center": "Learn",
  "steps": [
    {
      "label": "Try"
    },
    {
      "label": "Measure"
    },
    {
      "label": "Reflect"
    },
    {
      "label": "Adjust"
    }
  ],
  "emphasis": 2
}
```

### funnel (funnel or pyramid)

levels: [{label, detail?, value?}] (3-6, top to bottom); style: 'funnel' (default) or 'pyramid'; emphasis: level number

```json
{
  "type": "funnel",
  "title": "How a good idea becomes a shipped result",
  "levels": [
    {
      "label": "Ideas",
      "detail": "Everything on the table"
    },
    {
      "label": "Tested",
      "detail": "Small, cheap trials"
    },
    {
      "label": "Chosen",
      "detail": "Evidence says yes"
    },
    {
      "label": "Shipped",
      "detail": "Owned by one person"
    }
  ]
}
```

### timeline (timeline)

events: [{when, label, detail?}] (3-6); emphasis: event number

```json
{
  "type": "timeline",
  "title": "A 90-day rollout in four moves",
  "events": [
    {
      "when": "Days 1-14",
      "label": "Listen",
      "detail": "Interview the team"
    },
    {
      "when": "Days 15-45",
      "label": "Pilot",
      "detail": "One team, one process"
    },
    {
      "when": "Days 46-75",
      "label": "Adjust",
      "detail": "Fix what hurt"
    },
    {
      "when": "Days 76-90",
      "label": "Scale",
      "detail": "Roll out with owners"
    }
  ],
  "emphasis": 1
}
```

### before_after (before and after)

before & after: {heading, points: [up to 5 short strings]}

```json
{
  "type": "before_after",
  "title": "What changes when meetings have owners",
  "before": {
    "heading": "Before",
    "points": [
      "No clear decision",
      "Notes nobody reads",
      "Same topic again next week"
    ]
  },
  "after": {
    "heading": "After",
    "points": [
      "One decision per meeting",
      "Actions with names and dates",
      "Topic closed or escalated"
    ]
  }
}
```

### hub_spoke (hub-and-spoke map)

hub: {label, detail?}; spokes: [{label, detail?}] (3-8); emphasis: spoke number

```json
{
  "type": "hub_spoke",
  "title": "One clear message, five places it shows up",
  "hub": {
    "label": "Core message"
  },
  "spokes": [
    {
      "label": "Posts"
    },
    {
      "label": "Comments"
    },
    {
      "label": "Talks"
    },
    {
      "label": "Profile"
    },
    {
      "label": "Newsletter"
    }
  ]
}
```

### stat_callout (statistic callout)

stat: {value, label, context?}; supporting: up to 3 x {value, label}; source: REQUIRED (where the number comes from, or 'My own data')

```json
{
  "type": "stat_callout",
  "title": "Why the first five minutes matter",
  "stat": {
    "value": "3x",
    "label": "more follow-through",
    "context": "in teams that agree the next step before leaving"
  },
  "supporting": [
    {
      "value": "5 min",
      "label": "to agree the step"
    },
    {
      "value": "1",
      "label": "named owner"
    }
  ],
  "source": "My own team data, 2025"
}
```

### checklist (checklist)

items: [{label, detail?, done?}] (3-7); done defaults to true

```json
{
  "type": "checklist",
  "title": "Before you hit send on a hard message",
  "items": [
    {
      "label": "One clear ask"
    },
    {
      "label": "Facts, not labels",
      "detail": "What happened, not what it means"
    },
    {
      "label": "A way for them to reply"
    },
    {
      "label": "Read it out loud"
    }
  ]
}
```

## Carousel slides

A carousel is `{"type": "carousel", "title": "...", "slides": [...]}`. The first slide must be a `cover`, the last a `closing`, and the ones between use the diagram types above.

### cover

title, subtitle? (carousel only)

```json
{
  "type": "cover",
  "title": "Five habits that make meetings shorter",
  "subtitle": "A quick guide for team leads"
}
```

### closing

title, subtitle? (carousel only)

```json
{
  "type": "closing",
  "title": "Which habit will you try first?",
  "subtitle": "Tell me in the comments."
}
```

## Your brand look

Fill in the visual fields in section 11 of `docs/brand-profile.md`: primary, secondary, accent, background and text colors (hex such as `#1F3A5F`), heading and body fonts (a font installed on your computer), a logo file saved inside your workspace (PNG, JPG or SVG, up to 400 KB), and a footer text such as your name or handle. Blank fields give a clean neutral theme. Colors with too little contrast are reported (4.5:1 is the readable minimum) rather than silently used.

## What the checks mean

| Warning | Meaning | What to do |
|---|---|---|
| text_overflow | A text did not fit and was shortened | Use fewer words |
| small_text | Text would be under 28 px (hard to read in a phone feed) | Use fewer words; the generator shrinks type only down to 28 px |
| too_many_items | More items than stay readable (usually more than 6) | Split into two visuals or a carousel |
| too_many_words | More than about 100 words (70 per carousel slide) | Cut words before shrinking type |
| stat_needs_source | A statistic with no source | Add `source`, or write `My own data` / `My experience` |
| contrast | A brand color pair is hard to read | Pick a darker or lighter color |
| header_too_tall | Title, subtitle and takeaway leave too little room | Shorten them |

## Alt text and the visual prompt

Every render also writes `<name>.alt.txt` (a short version of up to 120 characters and a full description, built only from your spec's words), `<name>.prompt.txt` (a plain brief that recreates the visual in any design tool) and `<name>.meta.json` (fingerprints of the files, so the approved version can be proven later).

## Commands

```
python3 scripts/visual_engine.py types
python3 scripts/visual_engine.py example funnel
python3 scripts/visual_engine.py check --spec spec.json
python3 scripts/visual_engine.py render --spec spec.json --out out --png --pdf
python3 scripts/visual_engine.py previews --specs three.json --out previews
python3 scripts/visual_engine.py browser
```
