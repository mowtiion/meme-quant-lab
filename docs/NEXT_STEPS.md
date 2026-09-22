# Eerstvolgende werk — EXP-000 afmaken

GitHub is gekoppeld; de actuele code, tests en rapporten staan in
[mowtiion/meme-quant-lab](https://github.com/mowtiion/meme-quant-lab).

De drie eerdere onopgeloste AMM-events zijn gereconcilieerde protocol buy-and-burn-acties.
De oorspronkelijke proef heeft nul normalisatiefouten. CPI-herstel van de twee historische
transacties is geïmplementeerd en getest: één ontbrekende koop hersteld, twee bekende kopen
zonder dubbeltelling bevestigd. Eén administratief event blijft onbevestigd. EXP-000 blijft FAIL.

1. CPI-herstel is afgerond voor de gevalideerde varianten; zie `reports/CPI_RECOVERY_REPORT.md`.
   Bewaar het resterende `CPI_EXECUTION_UNPROVEN`-event in quarantaine totdat aanvullend
   uitvoeringsbewijs of gevalideerde historische programmasemantiek beschikbaar is.
2. Vergelijk alle create-instructies met CreateEvents en een tweede bron. Leg historische
   IDL/deployment-versies en regimes vast. Onbekende regimes blijven zichtbaar.
3. Bouw en valideer historische pool/reserve- en transfer/mint/burn-ledgers. Protocol buy-and-burn
   beïnvloedt reserves/supply, maar telt niet als walletvraag. Reconcile ook fees en niet-SOL-quotes.
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
