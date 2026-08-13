"""Step 1 -- atlas coefficients with acquisition-clustered intervals."""
import io, sys, re, csv, json, math, random, pathlib, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

R = pathlib.Path(r'D:\paper1_mechanobiology - Copy (2)')
REPS = 2000
PAT = re.compile(r'^(?P<lin>[A-Za-z0-9]+)_Phase_(?P<well>[A-Z]\d+)_'
                 r'(?P<pos>\d+)_(?P<t>\d+d\d+h\d+m)_(?P<crop>\d+)\.tif$')
NAME = {'BT474': 'BT-474', 'BV2': 'BV-2'}

mp = json.load(open(R / 'atlas_id_map.json', encoding='utf-8'))
rows = list(csv.DictReader(
    open(R / 'fig7_expanded' / 'time_out' / 'time_per_image.csv', encoding='utf-8')))
by = collections.defaultdict(list)
for r in rows:
    g = PAT.match(mp[r['image_id']]).groupdict()
    r['_acq'] = (g['lin'], g['well'], g['pos'], g['t'])
    r['_well'] = (g['lin'], g['well'])
    by[NAME.get(r['cell_type'], r['cell_type'])].append(r)


def rank(v):
    idx = sorted(range(len(v)), key=lambda i: v[i])
    o = [0.0] * len(v)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and v[idx[j + 1]] == v[idx[i]]:
            j += 1
        for k in range(i, j + 1):
            o[idx[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return o


def pear(a, b):
    n = len(a)
    if n < 3:
        return float('nan')
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return float('nan')
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / math.sqrt(va * vb)


def resid(y, x):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    vx = sum((v - mx) ** 2 for v in x)
    b = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / vx if vx > 0 else 0
    a = my - b * mx
    return [y[i] - (a + b * x[i]) for i in range(n)]


def coeffs(s):
    p = rank([float(r['phi']) for r in s])
    q = rank([float(r['mean_q']) for r in s])
    a = rank([float(r['mean_area']) for r in s])
    return pear(p, q), pear(resid(p, a), resid(q, a))


def cboot(sub, lvl, reps=REPS, seed=20260811):
    random.seed(seed)
    cl = collections.defaultdict(list)
    for r in sub:
        cl[r[lvl]].append(r)
    keys = list(cl)
    raws, pars = [], []
    for _ in range(reps):
        s = []
        for _ in range(len(keys)):
            s.extend(cl[keys[random.randrange(len(keys))]])
        a, b = coeffs(s)
        if a == a:
            raws.append(a)
        if b == b:
            pars.append(b)
    raws.sort(); pars.sort()
    q = lambda v: (v[int(0.025 * len(v))], v[int(0.975 * len(v)) - 1])
    return q(raws), q(pars), len(keys)


def tp(r, n):
    if n < 4 or abs(r) >= 1:
        return float('nan')
    t = abs(r) * math.sqrt((n - 2) / (1 - r * r))
    return math.erfc(t / math.sqrt(2))


pub = {NAME.get(r['cell_type'], r['cell_type']): r for r in csv.DictReader(
    open(R / 'final_table_all' / 'final_lineage_table.csv', encoding='utf-8'))}

print('=' * 92)
print('ATLAS COEFFICIENTS, ACQUISITION-CLUSTERED (%d reps)' % REPS)
print('=' * 92)
print('%-9s %6s %5s | %7s %-20s | %7s %-20s' %
      ('lineage', 'n img', 'nacq', 'raw', 'raw clustered CI',
       'partial', 'partial clustered CI'))
info = {}
for L in sorted(by):
    sub = by[L]
    rr, pp = coeffs(sub)
    (rl, rh), (pl, ph), k = cboot(sub, '_acq')
    info[L] = (rr, rl, rh, pp, pl, ph, k, len(sub))
    f1 = '' if (rl > 0 or rh < 0) else ' **raw incl 0**'
    f2 = '' if (pl > 0 or ph < 0) else ' **partial incl 0**'
    print('%-9s %6d %5d | %+7.3f [%+.3f, %+.3f] | %+7.3f [%+.3f, %+.3f]%s%s'
          % (L, len(sub), k, rr, rl, rh, pp, pl, ph, f1, f2))

print()
print('=' * 92)
print('PRINTED p-VALUES vs ACQUISITION-CLUSTERED')
print('=' * 92)
print('%-9s %13s %13s | %13s %13s' % ('lineage', 'raw p (pub)', 'raw p (acq)',
                                      'part p (pub)', 'part p (acq)'))
for L in sorted(by):
    rr, _, _, pp, _, _, k, _ = info[L]
    print('%-9s %13.2e %13.2e | %13.2e %13.2e'
          % (L, float(pub[L]['raw_p']), tp(rr, k),
             float(pub[L]['partial_p']), tp(pp, k)))

print()
print('=' * 92)
print('BT-474, THE DECIDING NUMBER -- 5,000 reps, five seeds, acquisition level')
print('=' * 92)
b = by['BT-474']
print('  n = %d images, %d acquisitions, %d wells'
      % (len(b), len({r['_acq'] for r in b}), len({r['_well'] for r in b})))
rr, pp = coeffs(b)
print('  point estimates: raw %+.4f  partial %+.4f' % (rr, pp))
print('  %8s %22s %22s' % ('seed', 'raw CI', 'partial CI'))
lows = []
for sd in (20260811, 1, 7, 42, 2026):
    (rl, rh), (pl, ph), _ = cboot(b, '_acq', 5000, sd)
    lows.append((rl, pl))
    print('  %8d  [%+.4f, %+.4f]   [%+.4f, %+.4f]' % (sd, rl, rh, pl, ph))
print('  raw lower bound across seeds     : %+.4f to %+.4f'
      % (min(x[0] for x in lows), max(x[0] for x in lows)))
print('  partial lower bound across seeds : %+.4f to %+.4f'
      % (min(x[1] for x in lows), max(x[1] for x in lows)))
print('  -> excludes zero at 95%%: raw %s, partial %s'
      % (all(x[0] > 0 for x in lows), all(x[1] > 0 for x in lows)))

print()
print('=' * 92)
print('WELL-CLUSTERED, where computable (3-4 wells per lineage)')
print('=' * 92)
for L in sorted(by):
    nw = len({r['_well'] for r in by[L]})
    if nw < 4:
        print('  %-9s %d wells -- too few to resample meaningfully' % (L, nw))
        continue
    (rl, rh), (pl, ph), k = cboot(by[L], '_well')
    print('  %-9s %d wells | raw [%+.3f, %+.3f] | partial [%+.3f, %+.3f]'
          % (L, k, rl, rh, pl, ph))
print('  NOTE: 4 clusters is far too few for a percentile bootstrap to be')
print('        trustworthy; these are reported as a flag, not relied on.')
