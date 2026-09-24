# Tweede bron: eerste fase-B-run

Status: `MISMATCH` volgens de oorspronkelijke exacte vergelijking; de volledige
41-blokkenproef is nog niet afgerond. GitHub Actions-run
[`36005849133`](https://github.com/mowtiion/meme-quant-lab/actions/runs/36005849133)
deed twee RPC-verzoeken: een slotlijst en het blok voor slot `449382000`.
De GitHub-secret was aanwezig en het Helius-endpoint antwoordde; de sleutel staat niet
in logs of het vergelijkingrapport.

Het Helius-blok bevatte 925 transacties. De SHA-256 van de ruwe Helius-response
`a6fd799dac6325e57e606ced290306b39ce9b5b6061940f1f34734e80ace1755`
komt overeen met het geüploade artifact. Een recursieve vergelijking met de bevroren
primaire response vond precies acht afwijkende velden: `meta.innerInstructions` en
`meta.logMessages` bij de transactie-indexen 114, 115, 705 en 708. Helius gaf `[]`,
de primaire bron `null`. In alle vier gevallen zijn `meta.err` gelijk aan
`MaxLoadedAccountsDataSizeExceeded` en `meta.computeUnitsConsumed` gelijk aan 0.
Headers, geordende signatures, berichten, uitvoering, loaded addresses en balansen
komen voor alle 925 transacties overeen.

We bewaren de exacte ruwe antwoorden; een nieuwe vergelijkingsversie mag alleen voor
deze specifieke fout met nul compute units een lege lijst tegen de primaire `null`
toetsen. Ze mag dit uitsluitend als alle overige veldgroepen overeenkomen en vermeldt
elke aanpassing in het rapport. Dit is een vergelijking van representatie, geen bewijs
dat de ontbrekende primaire logs alsnog bekend zijn. De [Solana-documentatie](https://solana.com/docs/rpc/json-structures)
beschrijft voor deze metadata zowel arrays als `null`; de betekenis van `null` kan
ontbrekende opname zijn.

De bewijsbestanden van de eerste run zijn als GitHub Actions-artifact beschikbaar tot
1 oktober 2026. Pas na een nieuwe begrensde run kunnen we de andere 40 slots beoordelen.
