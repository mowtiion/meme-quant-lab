# Data contracts — versie 1

## Raw, immutable en herleidbaar

| Object | Velden / opslag | Regel |
|---|---|---|
| RPC-response | Exacte JSON-bytes in `data/raw/objects/<prefix>/<sha256>.json` | SHA-256 wordt opnieuw gecontroleerd voor iedere replay; geen bewerking of overschrijving |
| Collectiemanifest | Bron, finalized, begin/eindslot, enumeratie-hash, enumerated_slots, block-hashes, issues, collected_at, complete | Een ontbrekend blok sluit complete uit; enumeratie wordt apart geverifieerd |
| Gedecodeerd event | slot, tx_index, event_index, signature, program, event_ms, name, payload, raw_sha256, decoder_hash | Event-index is log-index binnen transactie; identieke CPI-kopie wordt niet opnieuw ingelezen |
| Genormaliseerd event | Event-contract in domain.py | Logische identiteit plus tijd, mint, kind, bedragen/decimals, wallet, quote-unit en herkomst |

Raw JSON is de bron van waarheid; Parquet is een lossless herleidbare projectie, geen vervanging
van de oorspronkelijke response. `payload_json` bewaart geneste velden en integerbedragen zonder
floatconversie; kernvelden zijn expliciete Parquet-kolommen. DuckDB bevat dezelfde tabellen.

`event_ms` gebruikt blockTime × 1.000. On-chain event timestamps blijven in payload staan.
`available_ms` is alleen geldig als de oorspronkelijke ontvangst/confirmatie is gemeten;
een historische downloadtijd wordt nooit als historische aankomsttijd gebruikt.
`availability_basis` = unknown/observed/assumed. Alleen observed telt in de observed-modus.
Een bron die alleen hele seconden geeft, krijgt geen verzonnen millisecondenprecisie.

`base_raw`/`quote_raw` zijn positieve u64-integers; decimals moeten bekend zijn.
De huidige adapter normaliseert Pump-events met expliciete quote_mint/quote_amount. PumpSwap-mints
worden uit de eigen handelsinstructie en tokenbalansmetadata gehaald; ook tijdelijke gesloten
tokenaccounts kunnen daarmee worden herkend. Onopgeloste identiteiten worden geweigerd.
Afwezige legacyvelden worden gemarkeerd, niet stilzwijgend met moderne defaults gevuld.
Token-2022 en fee-afwijkingen zijn nog niet economisch gevalideerd.

## Snapshot — sleutel (dataset_version, mint, decision_ms, time_mode)

| Familie | Velden | Huidige status |
|---|---|---|
| Tijd/herkomst | age_seconds, event_cutoff_ms, boundary_guard_ms, last_event_order, max_feature_event_ms, max_feature_available_ms, coverage_complete | Geïmplementeerd; 10/30/60/120/300s na creatie; chain replay is diagnostisch |
| Handel | n_buys/sells/trades, unique_buyers/sellers, buy/sell_volume, net_flow, median/mean_trade_size, largest_buy | Geïmplementeerd op aanwezige genormaliseerde events; niet gelijk aan volledige economische boekhouding |
| Dynamiek | buyer/trade/volume_velocity en acceleration | Twee gelijke aangrenzende vensters; buyer meet nieuwe adressen per venster, volume is bruto |
| Prijs/curve | last_trade_price/ms/age, quote_mint, decimals, bonding_curve_progress, price/curve_velocity/acceleration | Prijs is tape-mark. Afgeleiden gebruiken drie as-of-ankers over tweede helft tokenleeftijd; oud/ontbrekend anker → NULL |
| Regime | is_mayhem_mode, is_cashback_enabled, is_holder_reward, token_program, curve_complete, migrated | Alleen vóór cutoff zichtbare creatie/completion/migration-events; onbekend blijft onbekend |
| Distributie | holder_count, top5/10/20_concentration, hhi, creator_holdings | NULL; vereist volledige transfers, mint/burn, owner/account-ledger en expliciete uitsluiting van vaults |
| Wallet/graph | wallet_ods, independent_buyers | NULL; historische outcomes moeten vóór decision zijn gerijpt, clusters moeten point-in-time zijn |

Curve progress = 1 − laatste real_token_reserves / reserves bij creatie. Het is een
reservefractie, geen percentage verwachte winst en geen bewijs van een geldige curveformule.
Een negatieve/onwaarschijnlijke fractie wordt niet naar [0,1] geknipt; die vereist regime-onderzoek.
Implied market cap wordt pas toegevoegd na validatie van supply en relevante prijsdefinitie.

## Outcome — sleutel (dataset_version, mint, decision_ms, horizon_seconds)

| Veld | Contract |
|---|---|
| horizons | 30m, 1h, 6h, 24h, 7d na decision |
| entry_basis | Momenteel last_trade_mark_only_NOT_EXECUTABLE; geen toekomsttrade als vervangende entry |
| status | UNPRICED, CENSORED of DIAGNOSTIC_ONLY |
| executable_labels_valid | Altijd false in deze versie |
| forward_return, mfe, mae, runner_labels | Altijd NULL totdat een gevalideerde entry/exit-reference bestaat |
| diagnostic | mark_entry_price, mark_mfe/mae, time_to_multiple_ms, hit_multiple, last_mark_return, terminal_mark_age_ms, coverage_complete |
| multiple thresholds | 2, 5, 10, 20, 50, 100; feature-events ≤ cutoff, label-events strikt > decision en ≤ horizon |

Een waargenomen hit is een diagnostische hit, ook bij latere datagaten. Geen hit met ontbrekende
dekking is NULL, niet false. Een stale eindprijs geeft geen horizonreturn. Een dode token wordt
niet verwijderd; zonder bewezen verkoopmogelijkheid kan zijn netto liquidation value niet uit
een oude prijs worden afgeleid. MFE is een achteraf waargenomen maximum, geen exitstrategie.

De latere uitvoerbare reference vereist positiegrootte, latency, reserves vóór eigen fill,
feeversie, impact, slippage, transactiekosten, failures en routebeschikbaarheid. Die specificatie
en reconciliatie horen vóór labels voor modeltraining worden vrijgegeven.

## Populatie, splits en gates

Steekproef: hash-ranking met vaste seed over alle unieke succesvolle creates in een vooraf
vastgelegd tijdvak. Geen selectie op huidige handelsactiviteit, migratie of toekomstige returns.
Dezelfde mint krijgt één kans; alle snapshots van een mint horen bij dezelfde chronologische split.
Een onvolledige launch-census blijft een blocker, ook als er 1.000 rijen zijn.

Voor later: labelhorizons die een splitgrens overlappen purgen; maximaal zeven dagen labelmaturatie
respecteren. Features en walletreputatie uitsluitend fitten op eerdere, toen beschikbare data.
Holdout niet bekijken of aanpassen om een gunstige uitkomst te krijgen. In EXP-000 is nog geen
train/validation/holdoutselectie gemaakt en geen predictieve hypothese getoetst.
