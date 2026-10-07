### Humanizer rules (three tiers)

Default tier: **Strict** (the owner can ask for Forensic only, or for Strict plus Style, per post or in `docs/settings.json` as `humanizer_tier`: `forensic`, `strict`, `style`). A tier includes the ones before it.

If the scripts are available, measure first: `python3 scripts/ai_tells.py --file draft.txt --tier strict`, edit, then compare: `python3 scripts/ai_tells.py compare --before draft.txt --after edited.txt`. If not, apply the rules by hand.

**Tier 1, Forensic (always).** Remove leftovers that no person would write:
- chatbot residue ("Certainly!", "I hope this helps", "As an AI", "Great question");
- unfilled placeholders such as [Name] or {{topic}};
- tracking leftovers in links (utm parameters from an AI tool) and invisible characters;
- markdown that LinkedIn does not render (**bold**, ## headings, tables);
- more than one em dash per 150 words; replace the rest with a full stop or a comma.

**Tier 2, Strict (default).** Remove the patterns that mark text as machine-made. Judge by density, not by single words: one "leverage" is fine, five in a post is not.
- Stock AI vocabulary clustering in one paragraph (for example: delve, tapestry, landscape, realm, unlock, leverage, seamless, robust, pivotal, game-changer, navigate the complexities).
- Filler bridges: "Here's the thing", "Let that sink in", "Here's why", "The truth is", "Let's dive in".
- Negative parallelism used more than once: "It is not X, it is Y".
- Stacked triads: three items in a row, repeatedly ("fast, simple, and scalable").
- Staccato runs: three or more very short sentences in a row used for drama.
- Openers like "In today's fast-paced world" and closers that restate the post.
- Hedge piles ("may potentially perhaps") and empty intensifiers.

**Tier 3, Style (only when asked).** Vary sentence length, prefer concrete nouns to abstractions, use bold rarely, break up evenly sized paragraphs.

**Over-correction guard (always).**
- Never remove or change a number, name, quote, date or claim. Never add an anecdote or detail to sound human.
- Keep the owner's signature phrases and habits (see the voice section of the brand profile). A person's text is allowed to be a little uneven.
- Do not replace every flagged word mechanically; rewrite the sentence so it still says the same thing.
- After editing, sentence-length variety must not drop and the text must not become shorter by more than about a quarter without a reason you can state. If the meaning drifted, undo that edit.
- Report what changed and what you deliberately left alone.
