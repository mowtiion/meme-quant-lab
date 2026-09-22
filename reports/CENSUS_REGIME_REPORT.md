# EXP-000 — launch-census en historische regimes

**Lokale instructie/event-reconciliatie: PASS voor de 44 onderzochte blokken. EXP-000 blijft FAIL.**

Broncode: `b802d4c9be6ab76d4b6fe5b412add385cefe0e15`, schone werkboom bij de census-audit.
100 tests slagen, waaronder 25 nieuwe controles. [GitHub Actions](https://github.com/mowtiion/meme-quant-lab/actions/runs/35778400374).

## Zes launches gereconcilieerd

De audit begint bij alle Pump-instructies in de opgeslagen geslaagde transacties en zoekt
`create`/`create_v2`. Hij koppelt iedere create aan precies één CreateEvent binnen dezelfde
programma-aanroep. Een event zonder create, ontbrekend event, dubbel event of onbekende
Pump-instructie veroorzaakt een expliciet issue. Uitvoering, instructieaccounts en gedeelde
payloadvelden worden gecontroleerd; huidige defaults worden niet op ontbrekende historische
instructievelden toegepast. Dit is een afzonderlijke audit, geen wijziging van de handelsdataset.

| Slot | Token | Mayhem | Holder rewards | Resultaat |
|---|---|---|---|---|
| 447000002 | STONK BROKER | Ja | Nee | PASS |
| 449382020 | MrBeast | Nee | Nee | PASS; twee optionele argumenten ontbreken |
| 449382028 | LVL | Nee | Nee | PASS |
| 449382030 | IronClaw | Nee | Ja | PASS; creator is holder-rewards-PDA |
| 449382031 | MEG POW | Ja | Nee | PASS |
| 449382040 | Haha Yes | Nee | Nee | PASS |

Alle zes gebruiken volgens hun events Token-2022. Er zijn twee Mayhem-launches en één
holder-rewards-launch. Die flags zijn point-in-time observaties uit de eigen creatieevents;
ze bewijzen niet dat alle historische economische regels gevalideerd zijn.
Er zijn geen onbekende Pump-instructiediscriminators in deze onderzochte geslaagde transacties.

Bij IronClaw verschilt het input-creatoradres van het creatoradres in het event. Dat is het
verwachte holder-rewards-mechanisme. De audit berekent de PDA uit `holder-rewards`, mint en
Pump-programma-ID en controleert het eventadres exact. Inputcreator en fee-ontvanger blijven
als aparte velden bewaard; een protocoladres wordt niet als de oorspronkelijke creatorwallet
geïnterpreteerd. Deze audit is nog geen creator-history-feature.

De bestaande Borsh-reader ondersteunde geen tuple-structs zoals Pump's `OptionBool` en
`OptionU64`. Dat is toegevoegd. Ontbrekende optionele staartargumenten blijven expliciet
`omitted_arguments`; de actuele IDL levert geen automatische historische defaults.
Bij MrBeast ontbreken creator_fee_bps en is_holder_reward in de instructie. Het volledige
CreateEvent bevat wel de waargenomen waarden. Fee-economie en historische defaultsemantiek
blijven buiten deze lokale vergelijking.

## Twee historische upgrades daadwerkelijk gevonden

Vier begrensde `getAccountInfo`-aanvragen naar de publieke Solana-RPC leverden de huidige
Program/ProgramData-metadata van Pump en PumpSwap. De loader, accounttypes en afgeleide
ProgramData-adressen zijn gecontroleerd. Vervolgens zijn de twee genoemde wijzigingsblokken
apart gedownload. Beide bevatten een geverifieerde, succesvol uitgevoerde loader-v3 Upgrade.

| Programma | Upgrade-slot | Bloktijd UTC | Betekenis voor onze proeven |
|---|---:|---|---|
| Pump | 447228373 | 15-09-2026 10:34:32 | Ligt ná het archiefvenster van 14 september en vóór de proef van 22 september |
| PumpSwap | 446462733 | 12-09-2026 15:23:56 | Ligt vóór beide onderzochte vensters |

De actuele metadata is op 22 september opgehaald. Het wijzigingsslot is eerst een aanwijzing;
de apart gecontroleerde Upgrade-instructie levert vervolgens concreet transactiebewijs.
De uitvoeringscontrole omvat ook inner-aanroepen en hun ouders. Volledige signatures,
instructiepaden, raw-hashes en manifests staan in het controlebewijs.

**Dit is nog geen gevalideerde koppeling van historische bytecode aan IDL-versies.** De vorige
Pump-binary, exacte versie-intervallen, binaire hashes en hun IDL/built-source-koppeling zijn
nog niet gereconstrueerd. Een huidige IDL-hash of GitHub-publicatiedatum bewijst geen historische
deployment. Het bewijs toont in ieder geval dat de twee Pump-proefvensters door een echte
upgrade gescheiden zijn. Gelijk decoderen betekent niet automatisch gelijke economische regels.

## Onafhankelijke bron en bereik

Een aanvraag `getBlocks(447000000,447000002)` aan de door PublicNode gepubliceerde Solana-RPC
leverde HTTP 403. Na één poging is gestopt. Er is daardoor geen onafhankelijk verkregen
blok- of launchpopulatie om te vergelijken. Dit zegt niets over toegankelijkheid via een
ander toegestaan account, noch dat een betaald abonnement noodzakelijk is.

Instructies en logs uit dezelfde raw-response zijn twee representaties van dezelfde bron.
Overeenstemming daarvan is waardevol, maar is geen onafhankelijke censuscontrole.
De 44 blokken zijn twee korte vensters; zij dekken niet de hele beoogde creatiedag.
De twee upgradeblokken worden alleen voor versieonderzoek gebruikt, niet bij de launchsample
gevoegd. Er is geen selectie op latere tokenwinst en geen bulkdownload gestart.

## Gatebesluit

| Controle | Status |
|---|---|
| Zes create-instructies ↔ zes scoped CreateEvents | PASS binnen 44 blokken |
| Flags en holder-rewards-PDA | PASS voor de geobserveerde records |
| Twee historische Upgrade-instructies | Bevestigd; geen volledige versiekaart |
| Onafhankelijke launch-census | UNPROVEN; tweede RPC-aanvraag HTTP 403 |
| Volledige launchpopulatie van 14 september | UNPROVEN |
| Historische binary ↔ IDL ↔ economische regels | UNPROVEN |
| Resterende CPI-kandidaat uit vorige stap | Nog één administratief event in quarantaine |
| EXP-000 / EXP-001 | FAIL / geblokkeerd |

De volgende stap is bewijs voor de Pump-versie vóór 15 september verkrijgen en de twee
proefvensters tegen een toegankelijke onafhankelijke bron vergelijken. Daarna volgen de
volledige census, reserve-/transfer-ledgers en het begrensde 1.000-launch-downloadplan.
Er zijn geen betaalde diensten aangeschaft of trades geplaatst.

## Reproduceren en bewijs

```bash
python -m pip install -r requirements.lock
PYTHONPATH=src python -m unittest discover -s tests -v
python -m meme_quant.cli census \
  --manifest data/raw/manifests/e6f27b744a0dcd838d24de1b916109ac8cd744cdf2103871bc2592d0f90413b5.json \
  --manifest data/raw/manifests/2b1a82e1062f068ff884a34b34ca1c7c94400fa99bba4fa7fffafca9f7695683.json \
  --out data/processed/census-new.json
```

Verwacht: lokale vergelijking PASS; totaal FAIL en exitcode 2. Kies een nieuwe outputnaam.
`observe-programs` doet vier nieuwe publieke metadata-aanvragen; die leveren een nieuwe
observatie en vervangen nooit de oude. Gebruik de opgeslagen raw-responses voor exacte replay.
Solders is vastgepind voor PDA-afleiding; ook de transitieve dependencies staan in de lockfile.

- [Census-audit](../experiments/exp000/census-regimes-v1.json).
- [Programmaobservatie](../experiments/exp000/program-observation-v1.json).
- [Controlebewijs](CENSUS_REGIME_VERIFICATION.json): zes launchfixtures en twee upgradefixtures
  exact vergeleken met originele raw-transacties; twee programmaheaders opnieuw uit raw gelezen.
- De bestaande CPI- en economische resultaten zijn niet overschreven.

## Primaire technische referenties

- [Pump: coin creation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/COIN_CREATION.md).
- [Pump: holder rewards](https://github.com/pump-fun/pump-public-docs/blob/main/docs/HOLDER_REWARDS_README.md).
- [Solana: program deployments](https://solana.com/docs/programs/deploying).
- [Loader-v3 account-layout](https://docs.rs/crate/solana-loader-v3-interface/latest/source/src/state.rs).
- [Solders PDA-afleiding](https://kevinheavey.github.io/solders/api_reference/pubkey.html).
- [PublicNode endpoint](https://solana.publicnode.com/).
