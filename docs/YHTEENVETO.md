<!--
Kieli: suomi. Ylläpitäjä (Antti Räisälä) on hyväksynyt, että tämä dokumentti
on suomeksi, poikkeuksena säännöstä, jonka mukaan repon tiedostot ovat
englanniksi. Älä käännä tätä tiedostoa. Pidä se ajan tasalla (tämä ei ole
lokitiedosto): kun tilepane muuttuu, päivitä vastaava kohta.

Language: Finnish, approved by the maintainer as an exception to the
English-only rule. Do not translate this file. Keep it current (it is not a
log file).
-->

# tilepane: yhteenveto

Tämä on ylätason kuvaus tilepanesta: mikä se on, miten sitä käytetään, mitä
on päätetty ja missä ollaan. Tarkemmat tiedot ovat repossa (katso lopusta).
Dokumentti on tarkoitettu lisättäväksi Claude-projektin tietoihin, jotta
projektin keskustelut tietävät, mistä on kyse.

## Mikä tilepane on

tilepane avaa pääteikkunoita tarkasti määriteltyihin kohtiin näytöllä ja
käynnistää niihin halutut komennot, esimerkiksi htop, watch tai nvidia-smi.
Asettelu (layout) kuvataan JSON-tiedostossa puuna: näyttö jaetaan kahtia, osat
jaetaan edelleen, ja jokaisesta lopullisesta suorakaiteesta (ruudusta) tulee
yksi ikkuna. Asettelua voi muokata myös hiirellä selaimessa.

Ohjelma on Linuxille, X11-istuntoon (Ubuntu, Mint ja muut). Se on kirjoitettu
Pythonilla ilman ulkoisia kirjastoja; ainoa lisäosa on python-xlib, jolla
ikkunat siirretään paikoilleen. Projekti on julkinen (GPL-3.0):
https://github.com/anttiraisala/tilepane

## Käyttö

```
tilepane --demo                          # satunnainen asettelu hauskoilla komennoilla
tilepane meters.json --monitor 1         # avaa asettelu näytölle 1
tilepane --close all                     # sulje tilepanen ikkunat (tästä työtilasta)
tilepane --toggle meters.json            # avaa, tai sulje jos jo auki
tilepane --edit meters.json              # muokkaa selaimessa
tilepane --dry-run meters.json           # näytä suorakaiteet avaamatta mitään
tilepane --doctor                        # ympäristön tarkistus
tilepane --monitors                      # näyttöjen numerot
```

Pieni esimerkki: htop vasemmalle (60 %), oikea puoli kahtia.

```json
{
  "name": "meters",
  "margin": 8,
  "split": {
    "dir": "columns", "at": "60%",
    "a": { "run": "htop" },
    "b": { "dir": "rows",
           "a": { "run": "watch -n1 sensors" },
           "b": { "run": ["date", "whoami", "ls -la"] } }
  }
}
```

## Tärkeimmät periaatteet ja päätökset

- **Jako:** `dir` on `columns` (rinnakkain) tai `rows` (päällekkäin). Jakokohta
  `at` annetaan prosentteina tai pikseleinä, alusta tai lopusta (`-300px`).
  Useamman osan jako: `children` ja `sizes` (`1frac`, `300px`, `20%`).
- **Marginaali** on ikkunoiden välinen kokonaisrako; reunassa puolet siitä.
- **Tyhjä ruutu:** ruutu, jota ei ole kirjoitettu tai joka on `{}`, jää
  tyhjäksi. Ruutu saa ikkunan, kun siinä on jokin oma asetus (komento,
  hakemisto, otsikko...).
- **Useita komentoja:** `run` voi olla lista; komennot ajetaan peräkkäin
  samassa ikkunassa. Lopuksi ikkuna jää auki komentoriville (`on_exit`:
  `keep`, `close` tai `restart`).
- **Terminaali ja komentotulkki** valitaan ruutukohtaisesti (`terminal`,
  `shell`). Oletus on `auto`: ensimmäinen löytyvä terminaali ja käyttäjän oma
  komentotulkki (Mintissä bash). Asetukset periytyvät alaspäin puussa.
- **Näytöt** numeroidaan sijainnin mukaan vasemmalta oikealle, alkaen nollasta.
- **Työtilat** pidetään erillään: sama asettelu voidaan avata eri työtiloihin,
  ja kumpikin saa omat ikkunansa. `--close` sulkee vain nykyisestä työtilasta;
  `--workspace N` tai `--workspace all` valitsee toisin.
- **Uudelleenavaus** ei tee kaksoiskappaleita: auki olevat ikkunat siirretään
  paikoilleen ja puuttuvat avataan. Käsin suljettu ikkuna avataan uudelleen.
- **Turvallisuus:** asettelutiedosto on ohjelma, koska se ajaa komentoja.
  Editorin palvelin toimii vain omalla koneella salaisella osoitteella.
- **Asetusten lähde** on JSON-skeema; siitä syntyvät asetusten dokumentaatio,
  `--explain` ja editorin ohjetekstit.

## Missä ollaan

Valmiina ja testattuna:

- ympäristön tarkistus, näyttöjen numerointi ja työalue (paneelit huomioiden)
- geometria, asetusten luku ja tarkistus, `--dry-run`
- ikkunoiden avaus X11:ssä gnome-terminalilla ja xtermillä, tarkka sijoitus
- ikkunoiden muistaminen, `--close`, `--toggle`, uudelleenavaus, työtilat
- `snap` (merkkiruudukko tai tarkka pikselikoko), ikkunareunuksen poisto
- `--demo` ja `--for` (ikkunat sulkeutuvat annetun ajan jälkeen)
- komentotulkin valinta ruutukohtaisesti
- selaineditori (`--edit`)

Testattu omistajan koneella (Linux Mint, Cinnamon): työtilat. Kehitysympäristössä
testattu virtuaalinäytöllä (Xvfb, Openbox, xterm): demo, työtilat, editorin
"Open on screen".

Puuttuu tai kesken:

- `--watch`: ikkunat päivittyvät heti, kun tiedosto tallennetaan
- Wayland-tuki (GNOME, KDE, sway, Hyprland)
- kitty- ja alacritty-terminaalien valmis tuki
- `mode: cycle` (komennot vuorottelevat samassa ruudussa)
- editorin merkkiruudukon esikatselu
- Compiz/Unityn työtilat (ne toteutetaan siellä eri tavalla)

Uusien toimintojen ehdotukset ja suositeltu järjestys ovat SPEC.md:n luvussa 6
("Open work and proposals"). Seuraavaksi suositeltu: `--watch` ja lokitiedosto,
sitten `--install-autostart` ja `--install-shortcut`, sitten `--dry-run --ascii`.

Kehitys tehdään haarassa `claude-personal`; `master` pidetään ennallaan, kunnes
omistaja päättää yhdistää.

## Tarkemmat tiedot repossa

- `README.md`: asennus, vaatimukset ja käyttö
- `SPEC.md`: koko spesifikaatio ja päätökset
- `PROGRESS.md`: kehityksen päiväkirja ja tilataulukko
- `docs/CONFIG.md`: jokainen asetus tyyppeineen ja oletuksineen
- `CLAUDE.md`: ohjeet Claude-istunnoille
