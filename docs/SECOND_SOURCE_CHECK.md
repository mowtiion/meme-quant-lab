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

De proef van 24 september is afgerond: het `comparison.json` en alle drie ruwe
Helius-responses zijn ontvangen en hier onafhankelijk op hashes en inhoud herberekend;
zie `reports/SECOND_SOURCE_PHASE_A_REPORT.md`. De API-key blijft privé.
De controle op het ontvangen archief is herhaalbaar met `scripts/verify_second_source_archive.py`;
ook een opzettelijk gewijzigd balansveld wordt geweigerd.

## Fase B — alleen na een geslaagde fase A

Vergelijk de 41 bestaande slots 449382000–449382040, met vooraf vastgelegde request-, byte-,
runtime- en gratis-quotumgrenzen. Maak daarna een apart plan voor controle van de bufferhistorie
en historische binaries. Drie of 44 overeenkomende blokken bewijzen geen volledige dagcensus.

Gemeten primaire omvang: 140.090.475 bytes voor 41 blokken, maximaal 7.984.212 bytes per
blok. Stel het maximum op 42 requests (één slotlijst + 41 blokken), 192 MiB responsdata
en 600 seconden totale runtime. Elk blok moet apart dezelfde volledige veldgroepen doorlopen.
Helius publiceert een Free-plan met één miljoen maandcredits; historische calls kosten
volgens de [prijskaart](https://www.helius.dev/pricing) doorgaans tien credits per call.
Een schatting van maximaal 420 credits is geen garantie op beschikbaarheid of backend-onafhankelijkheid.

De begrensde lokale fase-B-controle staat klaar. Download eerst de nieuwste GitHub-versie van
de repository op de eigen computer (de eerdere ZIP bevat dit script nog niet), open PowerShell
in de nieuwe projectmap en voer uit:

```powershell
py scripts/compare_second_source.py --phase-b
```

De API-key wordt alleen verborgen gevraagd; het script doet maximaal 42 read-only verzoeken,
stopt bij een afwijkend blok of een budgetfout en slaat geen sleutel of volledige URL op.
Bij een resultaat maakt het naast `comparison.json` maximaal zes kleine `evidence-*.zip`-bestanden
in `data/secondary/helius41-...`. Deel het rapport en die zes ZIP-bestanden voor herberekening
met `scripts/verify_second_source_archives.py`. De gehele primaire 41-blokkenreferentie is
vooraf lokaal op alle veldgroep-hashes gecontroleerd. Een mock-run van de volledige keten
voltooide 42 requests, 41 matches en zes archieven onder de uploadlimiet; opzettelijke
verandering van één balansveld werd geweigerd. Live Helius fase B moet nog worden uitgevoerd.

### GitHub Actions: zonder lokale PowerShell

De handmatige workflow `.github/workflows/helius-phase-b.yml` kan dezelfde begrensde proef
op GitHub draaien. De eigenaar stelt **eenmalig** onder `Settings → Secrets and variables →
Actions → New repository secret` de naam `HELIUS_API_KEY` in met de bestaande Helius-sleutel.
Dit is een repository-secret, geen repository-variable; zet de sleutel nooit in een issue,
commit, workflow-invoer of chat. De workflow verschijnt na opname in `main` onder `Actions →
Helius 41-block verification → Run workflow`. De proef start alleen na die handmatige klik,
heeft uitsluitend leesrechten op de repository, en stuurt maximaal 42 verzoeken naar Helius.
De uitkomst en originele responses zijn zeven dagen als workflow-artifact beschikbaar en
kunnen daarna met `scripts/verify_second_source_archives.py` onafhankelijk worden herberekend.
Een groen resultaat bevestigt uitsluitend overeenkomst voor deze 41 slots; upstream-
onafhankelijkheid en de resterende EXP-000 voorwaarden blijven open.

De eerste Actions-run stopte na blok 449382000: vier vóór uitvoering afgewezen transacties
gaven bij Helius lege lijsten voor logs en inner instructions, terwijl de primaire bron
`null` teruggaf. Alle overige velden in dit blok kwamen overeen. De vergelijking accepteert
deze twee representaties voortaan alleen bij `MaxLoadedAccountsDataSizeExceeded` met nul
verbruikte compute units en alleen wanneer alle andere veldgroepen exact overeenkomen.
De originele antwoorden blijven onveranderd bewaard en de normalisaties verschijnen per
transactie in het rapport. Zie `reports/SECOND_SOURCE_PHASE_B_FIRST_RUN.md`.

Geen proef hierboven geeft automatisch EXP-001 vrij. De 1.000-launchpilot start pas na
voldoende historische programmakoppeling, volledige velddekking en het resterende integriteitswerk.
