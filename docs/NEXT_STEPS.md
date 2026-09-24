# Eerstvolgende werk — EXP-000 afmaken

**Update 24 september:** [SOL én tokenlevenscycli in de steekproef zijn opgelost](../reports/TOKEN_LIFECYCLES_RESOLVED.md).
Alle **2.873 SOL-transacties** en **20.102 tokenaccount-controles** sluiten exact aan.
De 36 herinitialisaties, 20 resterende WSOL-eindgrenzen en unwrap zijn afgehandeld;
63 transacties hebben geen tokenaccount-activiteit. **239 tests slagen**.
Alle eerdere SOL-resultaten, 2.663 gewone AMM-feecontroles en 3 protocol burns blijven identiek.
Begin niet opnieuw met routerdiagnose, WSOL-reserves, provider-setup of benchmarks.

Eerstvolgend inhoudelijk werk: historische **Pump/PumpSwap binary/config/IDL-koppeling**,
resterend administratief uitvoeringsbewijs, complete census en upstream-herkomst.
De 1.000-launchpilot blijft geblokkeerd tot die onderzoeksgates slagen.
Zie `reports/TOKEN_LIFECYCLE_VERIFICATION.json` en `reports/TOKEN_NATIVE_RULES.json`.

GitHub is gekoppeld; de actuele code, tests en rapporten staan in
[mowtiion/meme-quant-lab](https://github.com/mowtiion/meme-quant-lab).

De drie eerdere onopgeloste AMM-events zijn gereconcilieerde protocol buy-and-burn-acties.
De oorspronkelijke proef heeft nul normalisatiefouten. CPI-herstel van de twee historische
transacties is geïmplementeerd en getest: één ontbrekende koop hersteld, twee bekende kopen
zonder dubbeltelling bevestigd. Eén administratief event blijft onbevestigd. EXP-000 blijft FAIL.

1. CPI-herstel is afgerond voor de gevalideerde varianten; zie `reports/CPI_RECOVERY_REPORT.md`.
   Bewaar het resterende `CPI_EXECUTION_UNPROVEN`-event in quarantaine totdat aanvullend
   uitvoeringsbewijs of gevalideerde historische programmasemantiek beschikbaar is.
2. De zes creates in 44 blokken zijn intern gereconcilieerd; twee Mayhem-launches en één
   holder-rewards-launch zijn expliciet vastgelegd. Twee loader-upgrades zijn bevestigd.
   De Pump-upload van 12 september is nu volledig uit de historische buffer gereconstrueerd
   (54 blokken, 1.638.312 bytes). Koppel deze binary nog aan verifieerbare broncode/IDL en
   bevestig het geldigheidsinterval. PublicNode/dRPC gaven HTTP 403, OnFinality HTTP 429.
   Drie ruwe Helius-blokken zijn nu onafhankelijk tegen de primaire veldgroep-hashes
   herberekend. De begrensde 41-slotproef is inmiddels met Alchemy geslaagd (42 requests, 140.090.905 bytes).
   De zes bewijsdelen zijn offline opnieuw gehasht; alle events zijn opnieuw vergeleken.
   Leg nog de upstream-herkomst vast; aparte leveranciers bewijzen geen onafhankelijke upstream.
   Een betaald abonnement is niet noodzakelijk gebleken. Zie `docs/SECOND_SOURCE_CHECK.md`.
   Zie `reports/HISTORICAL_BINARY_REPORT.md`.
3. De account-, reserve-, transfer/mint/burn- en native-ledgers voor de 41-bloksteekproef zijn gevalideerd.
   Breid de bewezen regels pas na historische programma/config-validatie uit naar de census.
   De sample bewijst geen volledige historische mintsupply; protocol burns blijven apart van walletvraag.
4. Gebruik het vastgelegde pilotplan in `configs/pilot1000.json`: launches van 14 september UTC,
   follow-up tot 22 september 00:05 UTC. Bevestig eerst volledige velddekking en bereken een
   begrensd downloadplan met opslag-, request- en runtimebudget.
5. Trek pas uit een complete, bevroren census 1.000 echte launches met seed 20260922.
   Houd dode/rug/zero-trade launches in de populatie. Reconstructeer vijf snapshots en outcomes;
   voer grensperturbaties en onafhankelijke known-answer-controles uit.
6. Werk het gatebesluit bij. EXP-001 begint alleen als essentiële data-integriteitsgates slagen.

## Wat de archiefproef bewijst

De publieke RPC leverde drie blokken van 14 september zonder API-key of aankoop.
Dit is geen bewijs voor schaalbare volledige backfill of onbeperkte archiefretentie.
Een API-abonnement is momenteel niet aangetoond als noodzakelijke oplossing; afgebroken on-chain
logs vereisen eerst parserherstel. Indien een provider later nodig blijkt: eerst een concrete
veld-/kostenvergelijking en kostenlimiet, pas daarna eventuele goedkeuring voor uitgaven.

## Uitvoerbare readiness-controle

```bash
python -m meme_quant.cli preflight --report experiments/exp000/archive-preflight-v3.json
```

Verwacht: `BLOCKED`, exitcode 2. Dit start geen download en verlaagt geen onderzoekscriteria.
Raw-data en afgeleide databases blijven buiten GitHub; de code en onderzoeksbesluiten zijn daar herleidbaar.
