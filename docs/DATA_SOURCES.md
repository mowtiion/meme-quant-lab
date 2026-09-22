# Databronnen — gecontroleerd 22 september 2026

De onderstaande mogelijkheden zijn documentatieclaims, tenzij expliciet lokaal getest.
Actuele accountrechten en daadwerkelijke historische dekking moeten met een kleine proef worden bevestigd.

| Bron | Historische trades / tijd | Curve, holders, wallets | Bulk / realtime | Kosten en begrenzing |
|---|---|---|---|---|
| Pump.fun / PumpSwap on-chain | Raw transacties, events en volgorde via RPC; officiële IDL's beschrijven parsing | Reserves/creatie/regime-events; holders vereisen transfer- en eigenaarsreplay | Zelf indexeren; geen hier gevalideerde officiële historische bulk-API | Programmadocumentatie gratis; transport/indexering apart |
| Bitquery | GraphQL trades, prijzen, launches; diepte verschilt per cube | On-chain instructies/pooldata hebben andere retentie dan koersaggregaten; holderhistorie niet als één API aannemen | GraphQL/WebSocket; historische S3/Parquet-export en Kafka als afzonderlijke routes | Personal $49/maand; Solana OHLCV $300/maand extra, transfers/balances $500/maand extra. Jaarlijkse equivalenten $210/$400. Geen aankoop gedaan |
| Helius | Archival RPC; getTransactionsForAddress met tijd-/slotfilter, paginering en maximaal 1.000 volledige transacties per pagina | Raw metadata beschikbaar; economische replay blijft eigen werk | RPC en WebSocket/LaserStream; bulkextractkosten vooraf meten | Free: 1M credits, 10 RPC req/s; Developer $49/maand, 10M credits, 50 req/s. Specifieke endpointrechten verifiëren |
| Direct Solana RPC | getBlocks/getBlock met expliciete slots; publieke endpoint is met echte blokken getest | Volledige metadata waar beschikbaar; geen kant-en-klare historische holderledger | HTTP-paginering en PubSub; archief/retentie endpointafhankelijk | Publieke dienst rate-limited; geen gegarandeerde backfillcapaciteit |

## Consequenties voor de bronkeuze

**Voorstel:** eerst één begrensde raw-RPC-pilot; een Helius-proef kan snellere adresgeschiedenis testen.
Vraag Bitquery pas om een specifiek exportvoorbeeld als alle vereiste velden en de launchpopulatie
voor dat tijdvak aantoonbaar worden gedekt. OHLCV alleen is geen vervanging voor transacties.
Er is nog geen voldoende onderbouwde totale prijs voor 1.000 launches plus zeven dagen follow-up.

Bitquery's retentiematrix noemt ongeveer 12 uur voor verschillende Solana on-chain cubes,
circa zeven dagen voor DEXTradeByTokens realtime en een aparte archive-route. Dezelfde pagina
waarschuwt voor Solana combined-fouten. De marketing/prijstekst noemt soms kortere on-chain
vensters. Behandel de werkelijke oldest/newest query per account en cube als acceptatietest.
Afwezige rijen zijn nooit automatisch afwezige trades.

De huidige Helius-methodedocumentatie rekent 10 credits per 100 geretourneerde volledige transacties,
naar boven afgerond, met minimum 10. Oudere blogprijzen mogen dit niet overschrijven.
Meet aantal pagina's, transacties, bytes, responstijd, 429's en werkelijk afgeschreven credits vóór opschaling.

## Regimes en tijd

De huidige Pump-documentatie bevat Mayhem, oudere cashback-coins, holder rewards en verschillende
quote-assets. PumpSwap kent ook virtual quote reserves. Gebruik daarom geen vaste SOL-aanname,
fee of initiële reserve voor alle vintages. De meegeleverde IDL-hashes leggen de parser vast;
ze bewijzen nog niet welke versie op een historische slot actief was.

Solana blockTime is een geschatte productietijd in seconden. De baseline sluit de laatste seconde
voor de deadline uit, maar die marge bewijst geen echte beschikbaarheid. Chain replay en
waargenomen aankomsttijd blijven aparte modi. De publieke dataproef vereiste
maxSupportedTransactionVersion=1; met versie 0 werd het blok expliciet geweigerd.

## Officiële bronnen

1. [Pump public docs](https://github.com/pump-fun/pump-public-docs)
2. [Pump-programma](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md)
3. [PumpSwap](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_SWAP_README.md)
4. [Bitquery Pump.fun API](https://docs.bitquery.io/docs/blockchain/Solana/Pumpfun/Pump-Fun-API/)
5. [Bitquery dekking en retentie](https://docs.bitquery.io/docs/graphql/data-coverage-retention/)
6. [Bitquery prijzen](https://bitquery.io/pricing)
7. [Helius prijzen](https://www.helius.dev/pricing)
8. [Helius getTransactionsForAddress](https://www.helius.dev/docs/rpc/gettransactionsforaddress)
9. [Solana getBlock](https://solana.com/docs/rpc/http/getblock)
10. [Solana getBlockTime](https://solana.com/docs/rpc/http/getblocktime)
11. [Solana publieke endpoints](https://solana.com/docs/references/clusters)
