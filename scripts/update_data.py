import os, json, math, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'data'
DATA_DIR.mkdir(exist_ok=True)
API_KEY = os.getenv('FRED_API_KEY','').strip()

SERIES = {
  # Rates / Treasury
  'DFF': {'name':'Effective Fed Funds Rate','section':'Rates','unit':'%','importance':5},
  'DGS3MO': {'name':'3M Treasury Yield','section':'Rates','unit':'%','importance':4},
  'DGS2': {'name':'2Y Treasury Yield','section':'Rates','unit':'%','importance':5},
  'DGS5': {'name':'5Y Treasury Yield','section':'Rates','unit':'%','importance':4},
  'DGS10': {'name':'10Y Treasury Yield','section':'Rates','unit':'%','importance':5},
  'DGS30': {'name':'30Y Treasury Yield','section':'Rates','unit':'%','importance':4},
  'T10Y2Y': {'name':'10Y–2Y Treasury Spread','section':'Rates','unit':'pp','importance':4},
  'T10Y3M': {'name':'10Y–3M Treasury Spread','section':'Rates','unit':'pp','importance':4},
  'DFII10': {'name':'10Y Real Yield','section':'Rates','unit':'%','importance':5},
  # Inflation
  'CPIAUCSL': {'name':'CPI Index','section':'Inflation','unit':'index','importance':5,'transform':'yoy'},
  'CPILFESL': {'name':'Core CPI Index','section':'Inflation','unit':'index','importance':5,'transform':'yoy'},
  'PCEPI': {'name':'PCE Price Index','section':'Inflation','unit':'index','importance':4,'transform':'yoy'},
  'PCEPILFE': {'name':'Core PCE Price Index','section':'Inflation','unit':'index','importance':5,'transform':'yoy'},
  'T5YIE': {'name':'5Y Breakeven Inflation','section':'Inflation','unit':'%','importance':4},
  'T10YIE': {'name':'10Y Breakeven Inflation','section':'Inflation','unit':'%','importance':4},
  # Labor
  'UNRATE': {'name':'Unemployment Rate','section':'Labor','unit':'%','importance':5},
  'PAYEMS': {'name':'Nonfarm Payrolls','section':'Labor','unit':'thousands','importance':5,'transform':'mom_diff'},
  'ICSA': {'name':'Initial Jobless Claims','section':'Labor','unit':'claims','importance':4},
  'CCSA': {'name':'Continuing Claims','section':'Labor','unit':'claims','importance':3},
  'CIVPART': {'name':'Labor Force Participation','section':'Labor','unit':'%','importance':3},
  'CES0500000003': {'name':'Average Hourly Earnings','section':'Labor','unit':'$/hr','importance':4,'transform':'yoy'},
  # Growth
  'GDPC1': {'name':'Real GDP','section':'Growth','unit':'$bn chained','importance':5,'transform':'qoq_ann'},
  'INDPRO': {'name':'Industrial Production','section':'Growth','unit':'index','importance':3,'transform':'yoy'},
  'RSAFS': {'name':'Retail Sales','section':'Growth','unit':'$mn','importance':4,'transform':'yoy'},
  # Consumer
  'PI': {'name':'Personal Income','section':'Consumer','unit':'$bn','importance':3,'transform':'yoy'},
  'PCE': {'name':'Personal Spending','section':'Consumer','unit':'$bn','importance':4,'transform':'yoy'},
  'PSAVERT': {'name':'Personal Saving Rate','section':'Consumer','unit':'%','importance':3},
  # Corporate
  'CP': {'name':'Corporate Profits After Tax','section':'Corporate','unit':'$bn','importance':4,'transform':'yoy'},
  # Financial conditions / credit
  'NFCI': {'name':'Chicago Fed NFCI','section':'Financial Conditions','unit':'index','importance':5},
  'ANFCI': {'name':'Adjusted NFCI','section':'Financial Conditions','unit':'index','importance':4},
  'BAMLH0A0HYM2': {'name':'High Yield Credit Spread','section':'Financial Conditions','unit':'%','importance':5},
  'BAMLC0A0CM': {'name':'Investment Grade Credit Spread','section':'Financial Conditions','unit':'%','importance':4},
  'VIXCLS': {'name':'VIX','section':'Financial Conditions','unit':'index','importance':5},
  # Liquidity
  'WALCL': {'name':'Fed Total Assets','section':'Liquidity','unit':'$mn','importance':4},
  'WTREGEN': {'name':'Treasury General Account','section':'Liquidity','unit':'$bn','importance':4},
  'RRPONTSYD': {'name':'Overnight Reverse Repo','section':'Liquidity','unit':'$bn','importance':4},
  'M2SL': {'name':'M2 Money Supply','section':'Liquidity','unit':'$bn','importance':3,'transform':'yoy'},
  # Treasury / fiscal proxies available on FRED
  'GFDEBTN': {'name':'Federal Debt','section':'Treasury & Fiscal','unit':'$mn','importance':3},
  'FYFSD': {'name':'Federal Surplus / Deficit','section':'Treasury & Fiscal','unit':'$mn','importance':3},
}

def get_json(url, params):
    params = dict(params)
    params['api_key'] = API_KEY
    params['file_type'] = 'json'
    full = url + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={'User-Agent':'macro-dashboard/1.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def fred_series(series_id):
    meta = get_json('https://api.stlouisfed.org/fred/series', {'series_id':series_id})['seriess'][0]
    obs = get_json('https://api.stlouisfed.org/fred/series/observations', {
        'series_id':series_id, 'sort_order':'asc', 'observation_start':'2000-01-01'
    })['observations']
    clean=[]
    for o in obs:
        try: v=float(o['value'])
        except: continue
        if math.isfinite(v): clean.append({'date':o['date'],'value':v})
    return meta, clean

def pct(a,b): return None if b in (None,0) else (a/b-1)*100

def transform(rows, kind):
    if not rows: return []
    vals=[x['value'] for x in rows]
    dates=[x['date'] for x in rows]
    out=[]
    if kind=='yoy':
        # monthly = 12 lag; quarterly = 4; infer from date spacing conservatively
        lag=12
        if len(dates)>2:
            y0,m0=map(int,dates[-2][:7].split('-')); y1,m1=map(int,dates[-1][:7].split('-'))
            months=(y1-y0)*12+(m1-m0)
            if months>=2: lag=4 if months<=4 else 1
        for i in range(lag,len(rows)):
            v=pct(vals[i],vals[i-lag])
            if v is not None: out.append({'date':dates[i],'value':v})
    elif kind=='mom_diff':
        for i in range(1,len(rows)): out.append({'date':dates[i],'value':vals[i]-vals[i-1]})
    elif kind=='qoq_ann':
        for i in range(1,len(rows)):
            if vals[i-1]!=0:
                v=((vals[i]/vals[i-1])**4-1)*100
                out.append({'date':dates[i],'value':v})
    else: return rows
    return out

def status_for(name, latest, change):
    lower_good = any(k in name.lower() for k in ['yield','fed funds','inflation','cpi','pce price','credit spread','vix','nfci','jobless','claims'])
    if change is None: return 'neutral'
    if lower_good: return 'positive' if change < 0 else ('negative' if change > 0 else 'neutral')
    return 'positive' if change > 0 else ('negative' if change < 0 else 'neutral')

def main():
    if not API_KEY:
        raise SystemExit('FRED_API_KEY environment variable is required.')
    metrics=[]; errors=[]
    for sid,cfg in SERIES.items():
        try:
            meta, raw=fred_series(sid)
            shown=transform(raw,cfg.get('transform')) if cfg.get('transform') else raw
            if not shown: raise ValueError('No usable observations')
            latest=shown[-1]; prior=shown[-2] if len(shown)>1 else None
            change=(latest['value']-prior['value']) if prior else None
            metrics.append({
                'id':sid,'name':cfg['name'],'section':cfg['section'],'unit':cfg['unit'],
                'importance':cfg['importance'],'value':latest['value'],'date':latest['date'],
                'change':change,'status':status_for(cfg['name'],latest['value'],change),
                'source':'FRED','source_title':meta.get('title',cfg['name']),
                'frequency':meta.get('frequency',''),'last_updated':meta.get('last_updated',''),
                'history':shown[-240:]
            })
        except Exception as e:
            errors.append({'id':sid,'error':str(e)})
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'metrics':metrics,'errors':errors}
    (DATA_DIR/'latest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f'Updated {len(metrics)} series; {len(errors)} errors')

if __name__=='__main__': main()
