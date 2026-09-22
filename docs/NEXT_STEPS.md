# Eerstvolgende werk — EXP-000 afmaken

1. Leg één pilotperiode vast, met volledige creatie-census en minimaal zeven dagen follow-up.
   Controleer beschikbaarheid op een kleine export voordat de 1.000 echte launches worden getrokken.
2. Valideer de actuele parser tegen historische IDL/deployment-versies en named regimevelden.
   Onbekende regimes blijven apart. Vergelijk create-instructies met CreateEvents en een tweede bron.
3. Bouw de historische PumpSwap pool/mint/quote-ledger inclusief migratie, poolwijzigingen,
   virtual quote reserves en niet-SOL-paren. Decoderen alleen is onvoldoende.
4. Voeg transfers, mint/burn en account-eigenaars toe. Reconcile tokenbalansen en reserves
   voor geselecteerde transacties en begin/eindpunten; fee/burn-bewegingen zijn geen walletverkopen.
5. Meet welke features werkelijk reconstructeerbaar zijn. Houd ontbrekende, gecensureerde,
   gerugde en niet-verhandelbare gevallen in de noemer. Geen vervanging door alleen graduates.
6. Reconstructeer 1.000 willekeurige echte launches en vijf snapshots per mint; voer boundary-
   perturbaties (bijvoorbeeld 0/1/2 seconden) en onafhankelijke known-answer checks uit.
7. Definieer gevalideerde entryreferences/outcomes; houd execution-aannames expliciet apart.
   Latency is een scenario totdat waargenomen aankomsttijden beschikbaar zijn.
8. Schrijf een nieuw EXP-000-rapport. De gates worden alleen aangepast op basis van herleidbare
   tests en data; er bestaat bewust geen `--force-pass`-optie.

## Benodigde toegang / besluit

De lokale publieke RPC-proef is gratis uitgevoerd. Nog geen API-account, abonnement,
databudget of GitHub-remote is voor dit project vastgesteld.

Een bestaand read-only archiefendpoint of geschikte export is voldoende om verder te testen.
Geef sleutels via een beveiligde environment/secret-instelling, niet via broncode of chat.
Bij aanschaf eerst een concrete offerte, velddekking en kostenlimiet laten goedkeuren.
De huidige bevindingen rechtvaardigen nog geen grote datadownload of betaald jaarabonnement.

Een GitHub-URL kan later aan deze checkout worden gekoppeld, met behoud van lokale commits.
Geen live wallet/trading-actie is onderdeel van dit vervolg.
