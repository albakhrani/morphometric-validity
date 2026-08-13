"""Remaining intervals under acquisition clustering. REPORT ONLY."""
import io, sys, re, csv, math, random, pathlib, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

D = pathlib.Path(r'D:\paper1_mechanobiology - Copy (2)\release_repo\data')
REPS = 2000
PAT = re.compile(r'^(?P<lin>[A-Za-z0-9\-]+)_Phase_(?P<well>[A-Z]\d+)_'
                 r'(?P<pos>\d+)_(?P<t>\d+d\d+h\d+m)_(?P<crop>\d+)\.tif$')


def tag(rows):
    for r in rows:
        g = PAT.match(r['file']).groupdict()
        r['_acq'] = (g['lin'], g['well'], g['pos'], g['t'])
        r['_well'] = (g['lin'], g['well'])
    return rows


f1 = tag(list(csv.DictReader(open(D / 'per_image_f1.csv', encoding='utf-8'))))
td = tag(list(csv.DictReader(open(D / 'per_image_tradeoff.csv', encoding='utf-8'))))

print('=' * 78)
print('CLUSTER STRUCTURE OF THE TWO SETS')
print('=' * 78)
for lab, rows, key in (('180-image detection benchmark', f1, 'method'),
                       ('150-image operating-point set', td, 'setting')):
    one = [r for r in rows if r[key] == sorted({x[key] for x in rows})[0]]
    print('  %-32s %4d images, %3d acquisitions, %2d wells'
          % (lab, len(one), len({r['_acq'] for r in one}),
             len({r['_well'] for r in one})))
    c = collections.Counter(collections.Counter(r['_acq'] for r in one).values())
    print('      crops per acquisition: %s' % dict(sorted(c.items())))


def micro(rows):
    tp = sum(int(r['tp']) for r in rows)
    fp = sum(int(r['fp']) for r in rows)
    fn = sum(int(r['fn']) for r in rows)
    d = 2 * tp + fp + fn
    return (2 * tp / d) if d else float('nan')


def boot(rows, clustered, reps=REPS, seed=20260811):
    random.seed(seed)
    if clustered:
        cl = collections.defaultdict(list)
        for r in rows:
            cl[r['_acq']].append(r)
        keys = list(cl)
    out = []
    for _ in range(reps):
        if clustered:
            s = []
            for _ in range(len(keys)):
                s.extend(cl[keys[random.randrange(len(keys))]])
        else:
            s = [rows[random.randrange(len(rows))] for _ in range(len(rows))]
        v = micro(s)
        if v == v:
            out.append(v)
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]


print()
print('=' * 78)
print('DETECTION-F1 INTERVALS (uncertainty.csv, 180-image set)')
print('=' * 78)
pub = {r['method']: r for r in csv.DictReader(open(D / 'uncertainty.csv',
                                                   encoding='utf-8'))}
byM = collections.defaultdict(list)
for r in f1:
    byM[r['method']].append(r)
res = {}
print('  %-20s %7s %20s %22s' % ('method', 'F1', 'published CI', 'clustered CI'))
for m in ('Cellpose', 'ours (watershed)', 'connected comp.', 'StarDist'):
    rows = byM[m]
    v = micro(rows)
    p = pub[m]
    lo, hi = boot(rows, True)
    res[m] = (v, lo, hi)
    print('  %-20s %7.4f  [%.4f, %.4f]   [%.4f, %.4f]'
          % (m, v, float(p['ci_lo']), float(p['ci_hi']), lo, hi))

print()
print('  --- the non-overlap claims ---')
PAIRS = [('Cellpose', 'ours (watershed)', 'Cellpose detects better than ours'),
         ('ours (watershed)', 'connected comp.', 'ours beats connected components')]
for a, b, lab in PAIRS:
    pa, pb = pub[a], pub[b]
    ov_pub = not (float(pa['ci_lo']) > float(pb['ci_hi'])
                  or float(pb['ci_lo']) > float(pa['ci_hi']))
    ra, rb = res[a], res[b]
    ov_cl = not (ra[1] > rb[2] or rb[1] > ra[2])
    print('    %-38s published overlap: %-5s   clustered overlap: %-5s  %s'
          % (lab, ov_pub, ov_cl, '** CLAIM AT RISK **' if ov_cl else 'holds'))

print()
print('=' * 78)
print('OPERATING-POINT INTERVALS (tradeoff_ci.csv, 150-image set)')
print('=' * 78)
pubt = {r['setting']: r for r in csv.DictReader(open(D / 'tradeoff_ci.csv',
                                                     encoding='utf-8'))}
byS = collections.defaultdict(list)
for r in td:
    byS[r['setting']].append(r)
rest = {}
print('  %-24s %7s %20s %22s' % ('setting', 'F1', 'published CI', 'clustered CI'))
for s in ('detection-optimal', 'balanced', 'measurement-optimal',
          'connected components'):
    rows = byS[s]
    v = micro(rows)
    p = pubt[s]
    lo, hi = boot(rows, True)
    rest[s] = (v, lo, hi)
    print('  %-24s %7.4f  [%.4f, %.4f]   [%.4f, %.4f]'
          % (s, v, float(p['ci_lo']), float(p['ci_hi']), lo, hi))

print()
print('  --- adjacent operating points: do the intervals overlap? ---')
for a, b in (('detection-optimal', 'balanced'),
             ('balanced', 'measurement-optimal')):
    ra, rb = rest[a], rest[b]
    ov = not (ra[1] > rb[2] or rb[1] > ra[2])
    print('    %-24s vs %-22s clustered overlap: %-5s' % (a, b, ov))
print('    NOTE: the paper asserts these differ by a paired Wilcoxon test,')
print('          which is unaffected by clustering; interval overlap is a')
print('          weaker and different criterion and no sentence rests on it.')
