# Tweede bron: fase-B-run 2

Status: **MISMATCH; controle van 41 blokken niet voltooid**. De [GitHub Actions-run
36018149420](https://github.com/mowtiion/meme-quant-lab/actions/runs/36018149420)
gebruikte commit `44b27cdff627446259a5a696b0afe552f32ae35b`, deed vier
read-only RPC-verzoeken (slotlijst en drie blokken) en bewaarde het bewijs als
artifact `10815616807`. SHA-256 van het gedownloade artifact:
`6a1f5823f631deaa7c9becd17f77845e6c3fb434b623584e803596980b57ce61`.
De gerapporteerde hashes van de drie ongewijzigde Helius-antwoorden zijn tegen
de bytes in het artifact gecontroleerd en de blocks zijn met de oorspronkelijke
primaire raw responses vergeleken.

| Slot | Transacties | Resultaat | Bevinding |
| --- | ---: | --- | --- |
| 449382000 | 925 | MATCH onder de begrensde normalisatie | 4 voor uitvoering afgewezen transacties: Helius `[]`, primaire bron `null` voor logs en inner instructions. |
| 449382001 | 924 | MATCH onder de begrensde normalisatie | Hetzelfde bij 10 transacties. |
| 449382002 | 1.029 | MISMATCH | 6 vergelijkbare `[]`/`null`-gevallen plus **5 daadwerkelijk afgekorte logreeksen**. |

Voor de vijf uitgevoerde transacties met index 14–18 in slot 449382002 geeft
Helius telkens 163 logregels, eindigend op `Log truncated`. De primaire response
geeft viermaal 252 en eenmaal 254 regels, zonder die afkorting. Tot en met de
afkapping zijn de eerste 162 regels gelijk; Helius mist daarna 90 respectievelijk
92 primaire logregels en zet in plaats daarvan een afkapmelding.
Het gaat dus om verloren loginhoud en niet om een verschil tussen lege lijst en
`null`. De header, transactielijst, instructieberichten, uitvoeringsstatus,
inner instructions, loaded addresses en balansen van dit blok kwamen overeen;
voor een volledige logvergelijking voldoet Helius bij deze transacties niet.
De [Solana-documentatie](https://solana.com/docs/programs/anchor-events) waarschuwt
dat RPC-providers programmalogs kunnen afkappen.

De workflow stopte terecht vóór de resterende 38 blokken. De bestaande
vergelijkingsgrens blijft staan; `Log truncated` wordt niet gelijkgesteld aan
volledige logs. Een herhaling met dezelfde provider en instellingen lost dit
bewijsgebrek niet op. Vervolg: vaststellen of de relevante events en programma's
door afgekorte logs geraakt worden en een bron met aantoonbaar volledige logs
vinden voordat deze fase als geslaagd kan worden beschouwd. Dit geeft geen
vrijgave voor EXP-001 of conclusies over een trading edge.
