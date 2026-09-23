# Historische Pump-binary — 23 september 2026

**De upload van 12 september is volledig uit één RPC-bron gereconstrueerd. EXP-000 blijft FAIL.**

## Resultaat

| Controle | Uitkomst |
|---|---|
| Bufferhistorie | 1.623 transacties, twee pagina's van 1.000 en 623 |
| Raw blokken | 54 geselecteerde slots, 222.218.805 bytes |
| Loader-schrijfacties | 1.619 |
| Programmabytes | 1.638.312, volledige dekking, geen overschrijvingen |
| Overige mutaties | allocatie, initialisatie, autoriteitswissel, storting van één lamport, upgrade |
| Upgrade | slot 446462760, 12 september 2026 15:24:04 UTC |
| Tests | 120 geslaagd, 0 mislukt; GitHub Actions geslaagd |
| Binary/source/IDL-koppeling | UNPROVEN |
| Onafhankelijke broncontrole | UNPROVEN |

Programma: `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`.
Buffer: `J7raNSKXB14MeCc6RwXQrKbPJXH4CWh9V4NCnw4Kibtk`.
Binary SHA-256: `7e260ecaa7aef442073042b513d61f8846ad8c5620022db200a76507e2312067`.
Raw manifest SHA-256: `8832a6b1ee5f4e17a82f8ae61e1571d0bb8ebbccc5e75dcdcc07fa5da2291ddb`.

## Bewijs en grenzen

De huidige bufferaccount is gesloten. De finalized transactiehistorie is daarom gepagineerd
tot de laatste, kortere pagina. Alle 1.623 signatures, slots en uitvoeringsresultaten sluiten
aan op de betreffende raw blokken. Hashes zijn gecontroleerd vóór verwerking. Alleen bewezen
succesvolle instructies en aanroepketens veranderen de gereconstrueerde toestand.

De replay controleert allocatie, autoriteit, exacte encoding, schrijfgrenzen, bytecoverage,
de doelupgrade en account-hergebruik. Een aangetroffen System Transfer stort één lamport op
de bestaande buffer en verandert geen programmabytes. Die expliciete variant is getest;
uitgaande of ongeldige transfers blijven geblokkeerd. Onbekende handelingen blijven fouten.
De [SystemInstruction-documentatie](https://docs.rs/solana-system-interface/latest/solana_system_interface/instruction/enum.SystemInstruction.html)
beschrijft de accountvolgorde en lamportsemantiek.

Een statische ELF-headerinspectie geeft ELF64, little-endian, type DYN en machinewaarde 0x107.
Het bestand is niet uitgevoerd. Dit is geen onafhankelijke validatie van de loader, een
reproduceerbare source-build of bewijs van alle economische programmasemantiek.

De officiële IDL-publicatie van 12 september, commit
`e0687ae9b7e064a0f54efc7297c65eecfbba3a8f`, bevat byte-identieke Pump- en PumpSwap-IDL's aan
onze vendorbestanden. Zie `vendor/history/provenance.json`. Publicatietijd en gelijke IDL's
koppelen het programma nog niet aan verifieerbare broncode. Ook het volledige geldigheidsinterval
tot de bekende upgrade op slot 447228373 blijft afzonderlijk te valideren.

De collector is hervat na een onvolledige HTTP-response en een gestopte langzaam binnenkomende
response. De al opgeslagen blokken zijn behouden. Het definitieve manifest bevat 54 blokken
zonder open downloadfouten. De limieten zijn 64 slots, 256 MiB opgeslagen blokdata en 600 seconden
per aanroep; de runtimegrens is geen cumulatieve grens over alle hervattingen. Transportdeadlines
en Content-Length-controles voorkomen dat gedeeltelijke responses als bewijs worden opgeslagen.

## Tweede bron

PublicNode gaf eerder HTTP 403. dRPC gaf bij deze proef HTTP 403; OnFinality gaf HTTP 429 bij
`getBlocks` en later ook bij `getSlot`. Geen van deze pogingen leverde vergelijkbare blokdata.
Dit bewijst geen gebrek aan historische dekking of noodzaak van een betaald abonnement.
De nieuwe pogingmetadata staat in `experiments/exp000/independent-source-probes-v1.json`.
Zie [het begrensde vervolgprotocol](../docs/SECOND_SOURCE_CHECK.md).

## Reproduceren

Broncode van de definitieve run: `4b2afd7420e86c4d5a6cd2b8b650defcbdea5c05`, werkboom schoon.
[GitHub Actions](https://github.com/mowtiion/meme-quant-lab/actions/runs/35825899874) slaagt.
De samenvatting staat in `experiments/exp000/pump-historical-binary-v1.json`; het volledige
operationele spoor, raw responses, manifest en ELF staan in het bijbehorende bewijsarchief.

Na uitpakken van dat archief in de projectmap en installeren van `requirements.lock`:

```bash
PYTHONPATH=src python -m meme_quant.cli reconstruct-buffer \
  --manifest data/processed/pump-old-buffer-blocks-v1.json \
  --program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P \
  --programdata B5MvUwXdiW1NMM6QFFD3ssPKBujD4zMohncbM73Z2BQu \
  --upgrade-signature SgEwKjomLvZgYWZVHkqLZAzB7LHtyQo7hWu5VgYKoVb82jqtz3fum7sAaCB7yzL2GNks5BwRB5wvpuyy4CKFbQV \
  --out data/processed/pump-old-binary-reproduced
```

De uitvoermap moet nieuw zijn. Geen data wordt opgehaald door deze offline reconstructie.
De administratieve CPI-kandidaat blijft in quarantaine. De volledige onafhankelijke census,
reserve-/transferledgers, 1.000 echte launches en essentiële integriteitsgates blijven open.
