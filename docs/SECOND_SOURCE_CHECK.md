# Tweede databron: begrensde toelatingsproef

Doel: dezelfde historische ketendata via een afzonderlijke provider controleren voordat
de census wordt opgeschaald. Een andere domeinnaam alleen bewijst geen onafhankelijke backend.
Leg daarom provider en bekende upstream/herkomst vast; markeer onbekende onafhankelijkheid expliciet.

## Benodigde toegang

Het Helius Free-account van de gebruiker heeft in de dashboard Playground de drie historische
slots getoond. De Playground biedt `getBlock` niet aan. Die slotlijst bewijst alleen
beschikbaarheid, geen inhoudsovereenkomst. Gebruik daarom de lokale, read-only controle hieronder.
Helius heeft op de geraadpleegde [prijskaart](https://www.helius.dev/pricing) een Free-plan;
bruikbaarheid voor de volledige historische blokinhoud moet nog worden getest.

De lokale controle vraagt de API-key verborgen op de eigen computer en slaat hem niet op.
Zet de key niet in chat, GitHub, rapporten of een gedeeld bestand.
Bevestig vooraf dat het gekozen endpoint binnen het gratis quotum valt; stop bij een betaalvereiste.

## Fase A — drie bestaande archiefblokken

1. Alleen finalized slots 447000000–447000002: één `getBlocks`, maximaal drie `getBlock`-responses.
   Request volledige transacties, logs, inner instructions, token-/SOL-balansen en loaded addresses,
   met transactieversie 1. Geen adresgestuurde selectie van alleen succesvolle launches.
2. Maximaal acht HTTP-pogingen inclusief retries, 32 MiB responses en 120 seconden totale runtime.
   Stop bij auth-, tarief-, velddekkings- of budgetfouten. Betaald gebruik is niet toegestaan.
3. Bewaar ongewijzigde responses op hash en een manifest met provideralias en geredigeerde
   requestmetadata. Bewaar geen URL met sleutel. De raw SHA's mogen verschillen door JSON-encoding.
4. Vergelijk semantisch: slotlijst/skipped slots, blockhash/parent/previousBlockhash, blockTime,
   geordende transacties en signatures, instructies, logs, uitvoering/errors, loaded addresses,
   inner instructions, pre/post SOL- en tokenbalansen. Vergelijk ook launch/trade/issue-aantallen.
   Elke ontbrekende of afwijkende waarde krijgt een expliciet verschilrapport.

Referentie: raw manifest `2b1a82e1062f068ff884a34b34ca1c7c94400fa99bba4fa7fffafca9f7695683`.
Het archief van de vorige census-audit bevat die referentiedata.
De bevroren semantische SHA-256-controles uit precies die drie raw blokken staan in
`configs/second_source_reference.json`. De scriptuitvoering vereist de raw referentiebestanden
niet op de eigen computer. Start vanuit de bijgewerkte repository op de eigen Windows-computer:

```powershell
py scripts/compare_second_source.py
```

Typ de `meme-quant-lab` API-key wanneer daarom wordt gevraagd; de invoer blijft onzichtbaar.
Het programma voert maximaal vier verzoeken uit en schrijft alleen de response-data en het
geredigeerde `comparison.json` onder een nieuwe `data/secondary/helius-...` map. Deel alleen
`comparison.json` als resultaat. Een `MATCH` bevestigt veld-voor-veld gelijkheid van deze drie
blokken tussen twee endpoints; het legt de upstream-onafhankelijkheid nog niet vast.

De proef van 24 september meldt `MATCH` voor alle drie slots; zie
`reports/SECOND_SOURCE_PHASE_A_REPORT.md`. Het ontvangen `comparison.json` is gecontroleerd,
maar de drie ruwe Helius-responses zijn nog niet overgedragen. Voor herberekening van de
hashes in deze werkruimte kan de gebruiker uitsluitend deze vier JSON-bestanden archiveren:

```powershell
Compress-Archive -Path '.\data\secondary\helius-20260924T130539717096Z\*.json' -DestinationPath '.\data\secondary\helius-phase-a-evidence.zip'
```

Deel alleen dat archief; de lokaal gebruikte sleutel of volledige RPC-URL hoort er niet in.

## Fase B — alleen na een geslaagde fase A

Vergelijk de 41 bestaande slots 449382000–449382040, met vooraf vastgelegde request-, byte-,
runtime- en gratis-quotumgrenzen. Maak daarna een apart plan voor controle van de bufferhistorie
en historische binaries. Drie of 44 overeenkomende blokken bewijzen geen volledige dagcensus.

Geen proef hierboven geeft automatisch EXP-001 vrij. De 1.000-launchpilot start pas na
voldoende historische programmakoppeling, volledige velddekking en het resterende integriteitswerk.
