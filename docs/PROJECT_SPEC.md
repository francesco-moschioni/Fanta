# Specifica di prodotto

Stato: canonico. Ambito: applicazione privata, locale e non commerciale per una lega di 20 squadre.

## Obiettivo

Costruire un assistente decisionale che unisca:

1. previsioni probabilistiche ex ante di rendimento e disponibilità;
2. valore marginale del giocatore nella rosa, non un ranking isolato;
3. simulazione e ottimizzazione dei quattro giri d’asta;
4. composizione visuale di rosa e formazione attorno alle scelte dell’utente;
5. cockpit live con offerte, assegnazioni, slot e crediti di tutte le 20 squadre;
6. apprendimento incrementale dei prezzi osservati, dell’inflazione e della domanda avversaria;
7. formazione settimanale e analisi post-asta in una fase successiva.

L’utente resta l’autorità finale. Ogni raccomandazione deve essere spiegabile, riproducibile e accompagnata da incertezza e data di aggiornamento.

## Contesto di lega

- Competizioni storiche: campionato, coppa, supercoppa.
- 20 squadre.
- Rosa: 24 giocatori — blocco di 3 portieri della stessa squadra, 8 difensori, 8 centrocampisti, 5 attaccanti; fallback storico a 4 attaccanti se l’offerta non basta.
- Moduli: 3-4-3, 3-5-2, 4-5-1, 4-4-2, 4-3-3, 5-4-1, 5-3-2, 5-2-3.
- Massimo 5 sostituzioni, no switch, formazione entro 5 minuti dall’inizio della giornata; in assenza, eredita quella precedente.

Le formule partita storiche sono sintetizzate in `SCORING_RULES.md`; i punti ambigui richiedono decisione in `OPEN_QUESTIONS.md`.

## Moduli applicativi

1. Ingestion con snapshot immutabili e registry fonti.
2. Identità canoniche di giocatori, squadre, competizioni e stagioni.
3. Feature ex ante e modelli modulari di minuti, eventi, voto e partita.
4. Motore deterministico del regolamento e simulazione Monte Carlo.
5. Valutazione asta: replacement, scarsità, rischio, fit, costo-opportunità e mercato.
6. Pool/lista/versioni, offerte, assegnazioni, ledger e replay.
7. Ottimizzatore rosa e undici con giocatori bloccati e modulo fisso/libero.
8. Cockpit live e profili di mercato delle squadre avversarie.
9. Export/import JSON e CSV, audit e riproducibilità.

## Requisiti non funzionali

- Locale-first, autosalvataggio e recupero dopo refresh/interruzione.
- Motore deterministico; simulazioni con seed e snapshot versionati.
- Nessuna formula statistica duplicata nel frontend.
- Raw immutabile; separazione raw/staged/curated/features/models/outputs.
- Audit trail per import, override, previsioni, offerte, assegnazioni e undo.
- Degradazione controllata quando una fonte manca.
- Accessibilità da laptop, tastiera, alto contrasto e colori non esclusivi.
- Nessun dato privato o segreto inviato a modelli esterni.

## Fuori scope iniziale

- Scraping Fantacalcio o uso di endpoint privati/non documentati.
- Redistribuzione di dati grezzi o database derivati.
- Automazione totale delle decisioni dell’utente.
- Injury prediction clinica senza dati adeguati.
- Deep learning/NLP prima che superino baseline forti fuori campione.
