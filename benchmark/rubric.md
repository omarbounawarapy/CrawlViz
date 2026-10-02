# Relevance rubric (v1, FROZEN 2026-10-02)

Frozen after a 42-page pilot (judge matched hand labels on 38; the 4 differences are
recorded in the README). It is not changed after the label distribution has been seen.
A change means a new rubric version and a full relabel.

Target: the *Institut supérieur d'informatique* (ISI), Ariana, Tunisia, part of the
Université de Tunis El Manar.

The judge sees only a page's title and the first 450 characters of its text.

## Labels

**2 = direct target.** The page's subject is the ISI itself: the article about that
institute, or a page devoted to one of its own programmes, departments or buildings.

**1 = topical neighbourhood.** The page's subject is any one of:

- (a) a degree-granting higher-education institution in Tunisia: a university, faculty,
  school (*école*), institute or technology institute, public or private, including the
  Tunisian campus of a foreign institution;
- (b) the Tunisian higher-education system as a whole, its governing ministry, or a list
  of Tunisian higher-education institutions.

and it is not the target itself.

**0 = irrelevant.** Everything else.

Label 1 is not "something vaguely related". A page is 1 only if its *subject* is (a) or (b).
Mentioning Tunisian universities in passing does not qualify. Being about education,
about Tunisia, or about computing does not qualify.

Label 2 is not "a Tunisian higher-education page that touches on computing". It is about the
ISI specifically. The ISI's parent university, sibling institutes and its city are 1 or 0,
never 2. So are other Tunisian institutes whose names resemble it (for example the computing institutes of Mahdia or Sfax): same name pattern, different institution.

## Decision rules

1. Decide from the title and excerpt shown. If they do not make clear that the subject is
   in Tunisia, label 0. (A deliberate bias toward 0.)
2. Check 2 first, then 1, then 0.
3. Pages about a person, event, rule or concept are 0 even when linked to a Tunisian
   institution, unless the page is devoted to the institution itself.

## Examples

| Page | Label | Why |
|---|---|---|
| Institut supérieur d'informatique (Tunisie) | 2 | the target |
| Université de Tunis - El Manar | 1 | Tunisian university, the ISI's parent, not the ISI |
| Faculté des sciences de Tunis | 1 | Tunisian faculty |
| École nationale d'ingénieurs de Tunis | 1 | Tunisian engineering school |
| Institut supérieur des études technologiques de Béja | 1 | Tunisian technology institute |
| Université Paris-Dauphine Tunis | 1 | Tunisian campus of a foreign university |
| Université privée de Sousse | 1 | private Tunisian university |
| Enseignement supérieur en Tunisie | 1 | the Tunisian system as a whole |
| Liste des universités en Tunisie | 1 | list of Tunisian institutions |
| Université virtuelle de Tunis | 1 | Tunisian university |
| Institut supérieur d'informatique de Mahdia / de Sfax / de Monastir / de Kairouan | 1 | other Tunisian institutes with a similar name, not the ISI of Ariana |
| Université Harvard | 0 | not in Tunisia |
| Sorbonne Université | 0 | not in Tunisia |
| Liste des universités au Québec | 0 | list for another country |
| Université en Afrique / Université au Maroc | 0 | not Tunisia |
| Tunis, Tunisie | 0 | the city and country, not an institution |
| Arabe tunisien, Judéo-tunisien | 0 | about Tunisia, not higher education |
| Institut Pasteur de Tunis | 0 | research and health institute, not degree-granting |
| Journal officiel de la République tunisienne | 0 | Tunisian but not higher education |
| Informatique | 0 | computing in general |
| Université, Faculté, Doyen (université), Grande école | 0 | generic concepts, no country |
| Agence universitaire de la Francophonie | 0 | international body |
| Classement international des universités | 0 | ranking, not an institution |

## Judge output

Per page, an integer 0, 1 or 2. Eight pages per call; the answer is JSON,
`{"labels": {"1": 2, "2": 0, ...}}`, and a call with a missing or non-integer entry is
retried, not guessed.
