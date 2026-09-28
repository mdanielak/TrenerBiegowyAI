# Zasady tworzenia treningów

Dokument obowiązujący dla wszystkiego, co dotyczy budowania treningów i stref tętna.
**Jeśli cokolwiek w innych plikach jest z tym sprzeczne — obowiązuje ten dokument.**
Ostatnia weryfikacja: 2026-09-28.

---

## 1. REGUŁA ROZGRZEWKI — każdy bieg w strefie 2

> **Każdy bieg w strefie 2 otwiera 5-6 minut w tempie 7:00-8:30/km BEZ alarmu strefy tętna.
> Dopiero po rozgrzewce włącza się pilnowanie strefy 2.**

**Dlaczego.** Na starcie tętno jest fizjologicznie niskie — organizm jeszcze nie wdrożył pracy.
Alarm strefy wyje wtedy o *„za niskim tętnie"* przez pierwsze minuty, więc biegacz przestaje
ufać strefie i zaczyna ją ignorować. Rozgrzewka **na tempo** (nie na tętno) podnosi tętno,
zanim włączy się pilnowanie strefy. Problem znika, strefa odzyskuje autorytet.

**Dotyczy:** regeneracji, biegów łatwych, długich wybiegań — czyli każdego treningu z alarmem
strefy 2.

**Wbudowane w kod.** `garmin_workout.py` — parametr `warmup_min`, domyślnie 6. Nie da się
stworzyć treningu strefowego z kodu bez rozgrzewki, chyba że świadomie poda się `warmup_min=0`.

### Czas całkowity a rozgrzewka

| Budowniczy | Znaczenie parametru czasu |
|---|---|
| `easy_run_zoned(main_min=N)` | N = część na tętno. Rozgrzewka jest **dodatkowo**: razem **N + 6 min** |
| `hr_zone_run(duration_min=N)` | N = **całkowity** czas na nogach. Rozgrzewka jest **w środku**: N − 6 min na strefę |

**Nazwa treningu musi mówić prawdę o czasie na nogach.** Trening „45 min" to 45 minut, nie 51.

### Struktura typowego treningu strefowego (45 min)

```
warmup     6:00   |  TEMPO 7:00 – 8:30 /km      ← bez alarmu tętna
interval  39:00   |  TĘTNO strefa 2 (115-134)
──────────────────────────────────────────────
RAZEM     45:00
```

---

## 2. STREFY TĘTNA (aktualne, źródło: Garmin Connect API)

Metoda: **%HRmax**, HRmax = **192** (ustawiony ręcznie w zegarku 2026-09-16).

| Strefa | bpm | %HRmax | Kiedy używać |
|---|---|---|---|
| Z1 | 96-115 | 50-60% | praktycznie nieosiągalna w biegu — to tempo marszu |
| **Z2** | **115-134** | 60-70% | regeneracja, biegi łatwe, długie |
| **Z3** | **134-154** | 70-80% | **szara strefa** — używać świadomie i rzadko |
| **Z4** | **154-173** | 80-90% | tempo i próg (próg = 174) |
| Z5 | 173-192 | 90-100% | powyżej progu |

Pobranie aktualnych stref: `gc.connectapi('/biometric-service/heartRateZones')`

### OSTRZEŻENIE — pułapka na dane historyczne

Kolumny `hrz_*_hr` w `garmin_activities.db` są **historyczne** (zapisane pod starą
konfiguracją HRmax 186: 93/111/130/148/167) i **NIE opisują obecnych stref**.
Czytanie stref z tych kolumn to błąd, który już raz popełniono w tym projekcie.

### Dolna granica strefy 2

**Z1 zbiera 19-32 sekundy na 45-80-minutowy bieg** — czyli 0-2%. Tętno 115 to tempo marszu,
nie biegu. Praktyczna konsekwencja: alarm *„za niskie tętno"* jest dokładnie tym, co irytuje
biegacza, i to jest główny powód istnienia reguły rozgrzewki z sekcji 1.

Jeśli strefa 2 ma być kiedykolwiek zmieniana — **podnosić dolną granicę** (115 → 122),
a nie górną. Podniesienie sufitu daje pozwolenie na dryf w szarą strefę.

---

## 3. TEMPO A TĘTNO — tętno wiąże, tempo jest wskazówką

| Rodzaj | Tętno | Tempo |
|---|---|---|
| Regeneracja / łatwe | Z2, 115-134 | **7:20-8:10/km** |
| Długie | 130-145 | 7:20-8:10/km |
| Tempo | 152-163 | 5:50-6:15/km |
| Próg | **165-174** | 5:30-5:50/km |
| Przebieżki | do ~170 | 3:06-3:35/km |

**Kalibracja:** realne tempo strefy 2 to **7:20-8:10/km**, nie 5:45-6:30/km.
Godzinę na 150-155 bpm da się przebiec szybciej, ale to już nie jest strefa 2.
Przy tym samym tempie 7:20-7:40/km tętno waha się między 130 a 133 bpm z dnia na dzień —
**3 bpm rozrzutu to norma**, więc przesuwanie granicy strefy o 2-3 punkty jest mniejsze niż
własny szum pomiarowy.

---

## 4. SZARA STREFA (Z3, 134-154) — główny problem tego biegacza

Rozkład z 2026 roku (93 biegi): **77-87% HRmax = 62,1%** całego biegania.
Z2 to zaledwie 21%, Z4+ 11%. Przez dwa lata trening żył w Z3.

Z3 to najgorszy punkt na krzywej koszt/korzyść: daje **niewiele więcej bodźca tlenowego niż
Z2**, kosztuje **wyraźnie więcej zmęczenia**, a **nie sięga progu**. Płaci się prawie pełną
cenę i nie dostaje prawie nic, czego nie dałoby Z2.

**Praktyczna konsekwencja:** regularny wyciek powyżej 134 w biegach łatwych to nie drobiazg.
21.09 — 9 min powyżej, 24.09 — 10 min, 25.09 — 22 min. Każdy z tych dni był „łatwy".

**Cel rozkładu:** ~90% łatwo / ~10% mocno. Jedna sesja jakościowa w tygodniu.

---

## 5. SENSORY TĘTNA

| Trening | Czujnik |
|---|---|
| Łatwe, regeneracja, długie | **optyczny na nadgarstku** (Fenix 7S) |
| Akcenty: tempo, próg, interwały | **pas piersiowy** — Magene H303, nie GEOID |

Optyczny został zmierzony na długim biegu: 2,2 skoki ≥6 bpm / 10 min, **zero cadence locka**
(HR/(2×kadencja) = 0,85; lock daje ~1,00). Nadaje się do strefy 2. Na wysokiej intensywności
nieprzetestowany — tam pas zostaje obowiązkowy.

Gdy pas padnie w trakcie biegu: **zatrzymać się, przełożyć i zwilżyć, biec dalej.**
Nie przełączać się na optyczny w połowie sesji i nie biec na fałszywych danych.
**Luka w danych jest lepsza niż kłamstwo.**

Kolejność naprawy „złego" pasa piersiowego:
1. **Wymienić sam pas** (elektrody wchłaniają sól i detergent) — najczęstsza przyczyna
2. Świeża bateria CR2032
3. Umyć w letniej wodzie bez detergentu

---

## 6. STRATEGIA I KONWENCJE PLIKÓW

- `training-plans/long-term/mdanielak-half-marathon-2027.md` zawiera aktualną strategię i cele długoterminowe; jest źródłem kierunku dla planowania tygodniowego.
- Brak tygodniowego JSON-a jest prawidłowy: readiness i rekomendacje dzienne działają bez niego.
- JSON-y tygodniowe, jeśli są potrzebne, są wyłącznie planami wykonawczymi. Nie zastępują strategii Markdown.
- `training-plans/_garmin_workouts.jsonl` jest lokalnym, ignorowanym rejestrem uploadów/usunięć Garmin, a nie planem.

- Plany: `training-plans/{YYYY-MM}/{start_day}-{end_day}.json`, w katalogu miesiąca,
  w którym blok się **zaczyna**. Blok może przechodzić przez granicę miesiąca — wtedy
  `28-4.json` (pon 28.09 – nd 4.10), a nie `28-04`.
- CSV jest **generowany z JSON-a** przez `services/training_plan.write_plan_csv()`.
  Nigdy nie pisać CSV ręcznie — tak się rozjeżdżają.
- `distance_km` / `duration_min` w planie to wartości **planowane**; fakty idą do `notes`.
- Rejestr treningów wgranych do Garmina: `training-plans/_garmin_workouts.jsonl`
  (append-only, stan odtwarzany przez replay). Każdy upload i każde usunięcie zapisuje się
   automatycznie — dzięki temu usunięty trening da się odtworzyć.
