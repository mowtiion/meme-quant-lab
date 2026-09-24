# Effect van afgekorte Helius-logs op de doel-events

Status: **beperkte overeenkomst voor drie blokken; geen volledige verificatie van 41 blokken**.
Deze audit gebruikt uitsluitend het al verkregen artifact van
[run #2](https://github.com/mowtiion/meme-quant-lab/actions/runs/36018149420),
de drie op SHA-256 gecontroleerde primaire raw-objecten en de vastgelegde
Pump- en PumpSwap-IDL's. Er zijn geen aanvullende netwerkverzoeken gedaan.

| Slot | Transacties | Pump/PumpSwap-events aan beide kanten | Helius-afkappingen buiten doelprogramma's |
| --- | ---: | ---: | ---: |
| 449382000 | 925 | 43 identiek | 0 |
| 449382001 | 924 | 30 identiek | 0 |
| 449382002 | 1.029 | 34 identiek | 5 |

Alle **107** gedecodeerde doel-events hebben bij beide providers dezelfde
transactie-index, logpositie, programmanaam, eventnaam en volledige payload.
De decoder vond in deze drie blokken bij beide bronnen geen openstaande issues.
De vijf afgekorte transacties hebben uitsluitend Token-2022-instructies; de
laatste heeft daarnaast een systeeminstructie. Er zijn geen Pump- of
PumpSwap-instructies op het buitenste of innerlijke niveau in deze vijf
transacties. Daarom veranderen deze vijf afkappingen de waargenomen doel-events
in **deze drie blokken** niet. Het maakt hun ontbrekende logs niet volledig.

Een afzonderlijke, gehashte inventaris van alle 41 bestaande primaire blokken
vond **35 transacties met Pump/PumpSwap-instructies** en **30 andere transacties**
waarvan de volledige primaire logs meer dan 10.000 bytes bevatten. Geen van
die primaire logreeksen bevat `Log truncated`. Omdat Helius in blok 449382002
bij ongeveer deze omvang vijf reeksen afkapt, is er een concreet risico dat
verderop wél doeltransacties geraakt worden. Dit is een risicoschatting uit de
primaire logs, geen bewijs dat Helius alle 35 zou afkappen.

De bestaande 41-blokkengrens blijft daarom **FAIL**. We mogen de vijf niet-
doeltransacties apart classificeren, maar daarmee zijn de overige 38 blokken
niet gevalideerd. Bij een alternatieve leverancier toetsen we eerst alleen
slot `449382002` (de vijf aantoonbaar lange logs) en slot `449382004` (een
transactie met een Pump/PumpSwap-aanroep en lange primaire logs). Beide
antwoorden moeten originele volledige logs, instructies en balances bevatten
en hun herkomst moet zijn vastgelegd voordat een grotere export zinvol is.
Dit vergt maximaal twee `getBlock`-verzoeken voor een eerste geschiktheidstoets.

Een [officieel overzicht van Alchemy](https://www.alchemy.com/overviews/solana-archival-data)
beschrijft archival `getBlock` en een gratis startplan. Dat document garandeert
geen logs zonder afkapping in de twee genoemde slots; de proef moet dat
daadwerkelijk vaststellen. Er is nog geen account of sleutel voor een nieuwe
provider ingesteld. EXP-000 blijft FAIL en EXP-001 blijft geblokkeerd.

De drie-blokkenaudit is herhaalbaar met
`scripts/audit_phase_b_scope.py` en het JSON-bewijs
`reports/SECOND_SOURCE_TARGET_SCOPE_VERIFICATION.json`.
