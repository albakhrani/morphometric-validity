"""Steps 2-3: ICC and clustered bootstrap. Verification only, no edits."""
import io, sys, re, csv, math, random, pathlib, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

D = pathlib.Path(r'D:\paper1_mechanobiology - Copy (2)\release_repo\data')
random.seed(20260811)
REPS = 1000
PAT = re.compile(r'^(?P<lin>[A-Za-z0-9\-]+)_Phase_(?P<well>[A-Z]\d+)_'
                 r'(?P<pos>\d+)_(?P<t>\d+d\d+h\d+m)_(?P<crop>\d+)\.tif$')

rows = list(csv.DictReader(open(D / 'mask_source_comparison_per_image.csv',
                                encoding='utf-8')))
for r in rows:
    g = PAT.match(r['file']).groupdict()
    r['_acq'] = (g['lin'], g['well'], g['pos'], g['t'])
    r['_pos'] = (g['lin'], g['well'], g['pos'])
    r['_well'] = (g['lin'], g['well'])

NAME = {'BT474': 'BT-474', 'BV2': 'BV-2'}
by = collections.defaultdict(list)
for r in rows:
    by[NAME.get(r['cell_type'], r['cell_type'])].append(r)


def rank(v):
    idx = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and v[idx[j + 1]] == v[idx[i]]:
            j += 1
        for k in range(i, j + 1):
            out[idx[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return out


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


def sp(x, y):
    return pear(rank(x), rank(y))


def icc(groups):
    """One-way random-effects ICC(1) from group means and within-group var."""
    gs = [g for g in groups if len(g) >= 1]
    N = sum(len(g) for g in gs)
    k = len(gs)
    if k < 2 or N <= k:
        return float('nan')
    gm = sum(sum(g) for g in gs) / N
    msb = sum(len(g) * (sum(g) / len(g) - gm) ** 2 for g in gs) / (k - 1)
    msw = sum(sum((x - sum(g) / len(g)) ** 2 for x in g) for g in gs) / (N - k)
    k0 = (N - sum(len(g) ** 2 for g in gs) / N) / (k - 1)
    if msb + (k0 - 1) * msw == 0:
        return float('nan')
    return (msb - msw) / (msb + (k0 - 1) * msw)


print('=' * 76)
print('STEP 2 -- INTRACLASS CORRELATION, measured not assumed')
print('=' * 76)
for lvl in ('_acq', '_pos', '_well'):
    for col, lab in (('meanq_expert', 'mean shape index'), ('phi', 'confluence')):
        g = collections.defaultdict(list)
        for r in rows:
            if r[col] not in ('', 'nan'):
                g[r[lvl]].append(float(r[col]))
        v = icc(list(g.values()))
        print('  overall  %-6s %-18s ICC = %6.3f   (%d clusters)'
              % (lvl[1:], lab, v, len(g)))
print()
print('  per lineage, ACQUISITION level:')
print('  %-9s %10s %10s %8s' % ('lineage', 'ICC meanq', 'ICC phi', 'clusters'))
for L in sorted(by):
    g1 = collections.defaultdict(list)
    g2 = collections.defaultdict(list)
    for r in by[L]:
        if r['meanq_expert'] not in ('', 'nan'):
            g1[r['_acq']].append(float(r['meanq_expert']))
        g2[r['_acq']].append(float(r['phi']))
    print('  %-9s %10.3f %10.3f %8d' % (L, icc(list(g1.values())),
                                        icc(list(g2.values())), len(g1)))


def boot(sub, col, lvl=None):
    """Percentile CI for Spearman(phi, col). lvl=None -> resample images."""
    data = [(float(r['phi']), float(r[col]), r[lvl] if lvl else None)
            for r in sub if r[col] not in ('', 'nan')]
    if lvl:
        cl = collections.defaultdict(list)
        for d in data:
            cl[d[2]].append(d)
        keys = list(cl)
        if len(keys) < 4:
            return (float('nan'), float('nan'), len(keys))
    out = []
    for _ in range(REPS):
        if lvl:
            samp = []
            for _ in range(len(keys)):
                samp.extend(cl[keys[random.randrange(len(keys))]])
        else:
            samp = [data[random.randrange(len(data))] for _ in range(len(data))]
        v = sp([s[0] for s in samp], [s[1] for s in samp])
        if v == v:
            out.append(v)
    out.sort()
    if not out:
        return (float('nan'), float('nan'), 0)
    return (out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1],
            len(keys) if lvl else len(data))


print()
print('=' * 76)
print('VALIDATION -- reproduce the published unclustered BT-474 expert interval')
print('=' * 76)
b = by['BT-474']
x = [float(r['phi']) for r in b]
y = [float(r['meanq_expert']) for r in b]
rho = sp(x, y)
lo, hi = boot(b, 'meanq_expert')[:2]
print('  published : rho = +0.264 [+0.095, +0.403]')
print('  recomputed: rho = %+.3f [%+.3f, %+.3f]' % (rho, lo, hi))
match = abs(rho - 0.264) < 0.002 and abs(lo - 0.095) < 0.03 and abs(hi - 0.403) < 0.03
print('  reproduces: %s' % match)
if not match:
    print('  !! does not reproduce -- stopping')
    sys.exit(1)

print()
print('=' * 76)
print('STEP 3.1 -- EXPERT BT-474, unclustered vs clustered')
print('=' * 76)
for lvl, lab in ((None, 'images (published)'), ('_acq', 'acquisitions'),
                 ('_pos', 'positions'), ('_well', 'wells')):
    lo, hi, k = boot(b, 'meanq_expert', lvl)
    if lo != lo:
        print('  %-20s n=%-4s DEGENERATE: too few clusters to resample' % (lab, k))
        continue
    print('  %-20s n=%-4d [%+.3f, %+.3f]  half-width %.3f  excludes zero: %s'
          % (lab, k, lo, hi, (hi - lo) / 2, 'YES' if (lo > 0 or hi < 0) else 'NO'))

print()
print('=' * 76)
print('STEP 3.2 -- the three BT-474 source coefficients')
print('=' * 76)
for col, lab in (('meanq_ours', 'ours, detection-optimal'),
                 ('meanq_oursalt', 'ours, measurement-optimal'),
                 ('meanq_cellpose', 'Cellpose')):
    xs = [float(r['phi']) for r in b if r[col] not in ('', 'nan')]
    ys = [float(r[col]) for r in b if r[col] not in ('', 'nan')]
    r0 = sp(xs, ys)
    u = boot(b, col)
    a = boot(b, col, '_acq')
    print('  %-26s rho %+.3f | images [%+.3f,%+.3f] | acq [%+.3f,%+.3f]'
          % (lab, r0, u[0], u[1], a[0], a[1]))
