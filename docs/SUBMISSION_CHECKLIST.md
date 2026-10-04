# Hack in Hills '26 — Submission checklist (TeamAlpha · AuLens · PS 03)

Source: hackinhills.com round details, read 2 Oct 2026.

## Round 1 · Idea & PPT (10 Sep – 20 Oct 2026)

- [ ] Deck on the official template: `AuLens_HackInHills26_PPT.pptx` (9 slides)
- [ ] Covers what organisers ask for: problem statement, solution, innovation, target users, tech stack, expected impact, implementation approach
- [ ] Export a PDF copy as well, in case the form wants PDF
- [ ] Upload on Unstop before 20 Oct

## Round 2 · Prototype (1 Oct – 20 Oct 2026)

Organisers want: working prototype / MVP, demo video, repository link, supporting documentation.

- [x] Download real Bhavcopy history into `data/raw/` (Oct 2025 – Oct 2026, 258 days)
- [ ] Run `pytest -q` (all green) and `streamlit run app.py` on real data
- [x] Record the backtest verdict honestly, including a "no edge" result (README → Results)
- [ ] Push to a public GitHub repo (`EIWOUP/aulens` or a team org)
- [ ] Deploy the app on Streamlit Community Cloud and put the link in the README
- [ ] Record the demo video (script below)
- [ ] Submit: prototype link, video link, repo link, `docs/METHODOLOGY.md`

### Demo video script (about 3 minutes)

| Time | Show | Say |
|---|---|---|
| 0:00–0:20 | Title slide | "Four gold futures on MCX, one metal. AuLens checks whether their price gaps are real and tradable after costs." |
| 0:20–0:50 | Normalised prices tab | "We convert every contract to rupees per gram of pure gold. Raw prices aren't comparable; these are." |
| 0:50–1:20 | Term structure tab | "GOLDM expires early in the month, the others at month-end. We remove that timing gap using the carry the GOLDM curve itself implies." |
| 1:20–1:50 | Today tab | "Alerts stay quiet unless the gap is big, beats costs, both legs trade, and there's time before tender. Today: quiet." |
| 1:50–2:35 | Backtest tab + results slide | "Twelve months of real MCX data, 258 days. Out of sample we made ₹1.26 lakh after costs, but ₹1.49 lakh of that came from the January–February gold rally. Every calm month lost money, including the July–September holdout. So our verdict is: no persistent edge after costs; the gap pays only in violent rallies. Gold beta is near zero, so this isn't just gold moving." |
| 2:35–3:00 | Data quality tab + repo | "Every data trap in the PS has a rule and a test. Code, tests and method are on GitHub." |

## Round 3 · Social pitch & outreach (22 – 25 Oct 2026)

Required: LinkedIn post, Instagram Reel, short video with repo link. Tag Eren, BuilderBase, Nexido, Web3 India.

### LinkedIn draft

> Four gold futures. One metal. Prices that should agree — but don't always.
>
> For Hack in Hills '26 (PS 03: Commodity Derivatives Intelligence), TeamAlpha built AuLens. It compares MCX's GOLDM, GOLDTEN, GOLDGUINEA and GOLDPETAL on a like-for-like basis: rupees per gram of pure gold, adjusted for the days between expiries.
>
> Then the hard part: does trading those gaps survive real costs? Our walk-forward backtest uses next-day prices, every exchange levy and slippage, and reports the answer even when it's "no edge".
>
> What we learned: the small contracts traded above GOLDTEN on all 258 days, but trading the swings only paid during the Jan–Feb 2026 rally. In calm months, costs ate the gap. Honest answer: no persistent edge.
>
> Repo: <link> · Demo: <link>
>
> @Eren @BuilderBase @Nexido @Web3 India #HackInHills26

### Instagram Reel outline (30–45 s)

1. Hook (3 s): "Same gold. Four prices. Which one is lying?"
2. Screen: four raw prices, then the same four normalised (they snap together).
3. Screen: the alert panel staying quiet: "Most gaps are just costs."
4. Screen: backtest verdict + β ≈ 0.
5. Team shot in front of the laptop. Text: "AuLens · Hack in Hills '26 · link in bio."

## Round 4 · Grand finale (20 – 21 Nov 2026, Manali)

- [ ] Live data refresh working offline-tolerant (cache the last download)
- [ ] Silver family extension (SILVER, SILVERM, SILVERMIC): add specs, rerun
- [ ] 5-minute pitch built from the Round 1 deck, with real results replacing the plan slide
