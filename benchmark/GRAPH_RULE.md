# Graph construction rule (pre-registered)

Written before any seed was probed and before any label exists for the new graph.

## Rule
1. **Source:** fr.wikipedia.org, main namespace (articles only, no `Fichier:`, `Catégorie:`, ...).
2. **Graph:** every article within link distance 2 of the seed (the seed, the pages it
   links to, and the pages those link to). No size cap and no truncation by crawl order.
   The set is fixed by the rule, not by what a crawler met first.
3. **Closed:** links to pages outside the set are dropped. Each page keeps its links
   to pages inside the set, with their anchor text, in page order.
4. **Seed choice, by structure only:** from the candidates below, take the first that
   has (a) the target page at link distance exactly 2, and (b) a distance-2 ball of
   3,000 to 20,000 pages. A candidate over 20,000 is rejected, not sampled. If none
   qualifies, stop and ask.
5. The label distribution plays no part in choosing the seed, because no labels exist
   when it is chosen.

Target page: `Institut_supérieur_d'informatique_(Tunisie)`.

Candidate seeds, in this order:
1. `Enseignement_supérieur_en_Tunisie`
2. `Liste_des_universités_en_Tunisie`
3. `Tunisie`

## What a page record holds
Title and the first 450+ characters of article text, with hatnotes, stub banners, edit
links and reference markers removed, plus its in-set links with anchor text.

## Outcome (recorded after construction, no labels exist yet)
Seed `Enseignement_supérieur_en_Tunisie`, the first candidate, qualified: target at distance 2.
Radius-2 ball: 5,865 pages (1 seed, 77 at distance 1, 5,787 at distance 2), 355,590 in-set links
(about 61 per page), 838 pages with no in-set links. Saved to `benchmark/data/ball.json`.
The probe's title count (10,358) included redirect names; the recorded count merges them.
