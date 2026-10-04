#!/usr/bin/env python3
"""Marktdaten-Helfer fuer das taegliche Screening.

Holt Tageskurse ueber die oeffentliche Yahoo-Finance-Chart-API und berechnet
Trend-/Momentum-Kennzahlen. Nutzung:

  python3 market.py quote SYMBOL [SYMBOL ...]        # Kurzuebersicht
  python3 market.py screen [--universe default]      # Momentum-Ranking
  python3 market.py json SYMBOL [SYMBOL ...] > x.json
"""
import json, sys, time, math
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
HOSTS = ["query2.finance.yahoo.com", "query1.finance.yahoo.com"]

UNIVERSE = {
    "Indizes & Makro": "^GSPC ^NDX ^GDAXI ^STOXX50E ^N225 ^HSI 000001.SS ^NSEI WIG20.WA ^VIX ^TNX DX-Y.NYB EURUSD=X",
    "Rohstoffe & Krypto": "GC=F SI=F HG=F PL=F PA=F CL=F BZ=F NG=F ZW=F KC=F CC=F BTC-USD ETH-USD",
    "Themen-ETFs": "SMH ITA GDX GDXJ COPX URA URNM LIT REMX TAN XBI IBIT XLE XLU XLF XLV XLI XLK XLP EPOL INDA EEM KWEB",
    "US Tech": "AAPL MSFT NVDA AMZN GOOGL META TSLA AVGO ORCL AMD TSM ASML NFLX PLTR CRM NOW ADBE INTC MU QCOM ANET ARM DELL IBM CSCO UBER SHOP COIN HOOD MSTR APP CRWD PANW NET SNOW",
    "US Finanzen & Konsum": "JPM GS MS BAC V MA AXP BRK-B WMT COST HD MCD NKE SBUX KO PG",
    "US Gesundheit": "LLY NVO UNH JNJ ABBV MRK PFE ISRG VRTX AMGN HIMS CYBN",
    "US Industrie, Energie, Rohstoffe": "GE GEV CAT DE LMT RTX NOC GD BA ETN VRT PWR HON XOM CVX OXY SLB VST CEG NRG CCJ OKLO SMR NEE FCX NEM AEM GOLD SCCO MP ALB RIO BHP VALE",
    "Europa": "SAP.DE SIE.DE ALV.DE DTE.DE MUV2.DE RHM.DE HAG.DE R3NK.DE MTX.DE ENR.DE IFX.DE BAS.DE BAYN.DE VOW3.DE MBG.DE BMW.DE DBK.DE CBK.DE ADS.DE ZAL.DE AIR.PA SAF.PA MC.PA RMS.PA OR.PA TTE.PA SU.PA ASML.AS NOVO-B.CO NOVN.SW ROG.SW NESN.SW UBSG.SW SHEL.L AZN.L RR.L BA.L LDO.MI UCG.MI ISP.MI SAN.MC IBE.MC ITX.MC",
    "Asien": "0700.HK 9988.HK 3690.HK 1810.HK 1211.HK 7203.T 6758.T 8035.T 005930.KS 000660.KS INFY RELIANCE.NS",
}


def fetch(symbol, rng="1y", interval="1d", tries=4):
    last = None
    for i in range(tries):
        host = HOSTS[i % 2]
        url = f"https://{host}/v8/finance/chart/{symbol}"
        try:
            r = requests.get(url, params={"range": rng, "interval": interval}, headers=UA, timeout=20)
            if r.status_code == 200:
                res = r.json()["chart"]["result"][0]
                q = res["indicators"]["quote"][0]
                rows = [(t, c, h, l) for t, c, h, l in zip(res["timestamp"], q["close"], q["high"], q["low"]) if c is not None]
                return {"meta": res["meta"], "t": [r[0] for r in rows], "close": [r[1] for r in rows],
                        "high": [r[2] or r[1] for r in rows], "low": [r[3] or r[1] for r in rows]}
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{symbol}: {last}")


def ret(c, n):
    return (c[-1] / c[-1 - n] - 1) * 100 if len(c) > n and c[-1 - n] else None


def stats(symbol, d):
    c, h, l = d["close"], d["high"], d["low"]
    sma = lambda n: sum(c[-n:]) / n if len(c) >= n else None
    trs = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(max(1, len(c) - 14), len(c))]
    atr = sum(trs) / len(trs) if trs else None
    dr = [math.log(c[i] / c[i - 1]) for i in range(max(1, len(c) - 63), len(c)) if c[i - 1]]
    vol = (sum((x - sum(dr) / len(dr)) ** 2 for x in dr) / (len(dr) - 1)) ** 0.5 * math.sqrt(252) * 100 if len(dr) > 2 else None
    hi52 = max(c[-252:])
    s50, s200 = sma(50), sma(200)
    m = d["meta"]
    return {
        "symbol": symbol, "name": m.get("shortName") or m.get("longName") or symbol,
        "currency": m.get("currency"), "date": time.strftime("%Y-%m-%d", time.gmtime(d["t"][-1])),
        "last": round(c[-1], 4), "d1": ret(c, 1), "d5": ret(c, 5), "m1": ret(c, 21), "m3": ret(c, 63),
        "m6": ret(c, 126), "m12": ret(c, min(251, len(c) - 1)),
        "vs_sma50": (c[-1] / s50 - 1) * 100 if s50 else None,
        "vs_sma200": (c[-1] / s200 - 1) * 100 if s200 else None,
        "from_high": (c[-1] / hi52 - 1) * 100, "atr_pct": atr / c[-1] * 100 if atr else None,
        "vol3m": vol, "day_high": round(h[-1], 4), "day_low": round(l[-1], 4),
        "sma50": round(s50, 4) if s50 else None, "sma200": round(s200, 4) if s200 else None,
    }


def fmt(v, w=7):
    return f"{v:{w}.1f}" if isinstance(v, (int, float)) else " " * (w - 1) + "-"


def table(rows):
    print(f"{'Symbol':<11}{'Name':<26}{'Kurs':>11} {'Cur':<4}{'1T%':>7}{'5T%':>7}{'1M%':>7}{'3M%':>7}{'6M%':>7}{'12M%':>7}{'SMA50':>7}{'SMA200':>7}{'v.Hoch':>7}{'ATR%':>6}{'Vol':>6}  Datum")
    for r in rows:
        print(f"{r['symbol']:<11}{r['name'][:25]:<26}{r['last']:>11.2f} {str(r['currency'])[:3]:<4}{fmt(r['d1'])}{fmt(r['d5'])}{fmt(r['m1'])}{fmt(r['m3'])}{fmt(r['m6'])}{fmt(r['m12'])}{fmt(r['vs_sma50'])}{fmt(r['vs_sma200'])}{fmt(r['from_high'])}{fmt(r['atr_pct'],6)}{fmt(r['vol3m'],6)}  {r['date']}")


def collect(symbols):
    out, errs = [], []
    for s in symbols:
        try:
            out.append(stats(s, fetch(s)))
        except Exception as e:  # noqa: BLE001
            errs.append(str(e))
        time.sleep(0.25)
    if errs:
        print("Fehler:", "; ".join(errs), file=sys.stderr)
    return out


def momentum_score(r):
    # Klassisches 12-1-Momentum ergaenzt um 6M und 3M, nur fuer Titel im Aufwaertstrend.
    parts = [(r["m12"] or 0) - (r["m1"] or 0), r["m6"] or 0, r["m3"] or 0]
    return sum(parts) / 3 / max(r["vol3m"] or 30, 15) * 30


if __name__ == "__main__":
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("screen", [])
    if cmd == "quote":
        table(collect(args))
    elif cmd == "json":
        print(json.dumps(collect(args), indent=1))
    elif cmd == "screen":
        groups = args or list(UNIVERSE)
        allrows = []
        for g in groups:
            rows = collect(UNIVERSE[g].split())
            print(f"\n### {g}")
            table(rows)
            allrows += rows
        trend = [r for r in allrows if (r["vs_sma200"] or -1) > 0 and (r["vs_sma50"] or -1) > 0 and not r["symbol"].startswith("^")]
        trend.sort(key=momentum_score, reverse=True)
        print("\n### Top-Momentum (ueber SMA50 und SMA200, risikoadjustiert)")
        table(trend[:30])
        with open("screen_latest.json", "w") as f:
            json.dump(allrows, f)
