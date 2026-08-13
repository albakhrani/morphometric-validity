"""Pin down the BT-474 expert lower bound: many seeds, more reps."""
import io, sys, re, csv, math, random, pathlib, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

D = pathlib.Path(r'D:\paper1_mechanobiology - Copy (2)\release_repo\data')
PAT = re.compile(r'^(?P<lin>[A-Za-z0-9\-]+)_Phase_(?P<well>[A-Z]\d+)_'
                 r'(?P<pos>\d+)_(?P<t>\d+d\d+h\d+m)_(?P<crop>\d+)\.tif$')
rows = [r for r in csv.DictReader(open(D / 'mask_source_comparison_per_image.csv',
                                       encoding='utf-8'))
        if r['cell_type'] == 'BT474' and r['meanq_expert'] not in ('', 'nan')]
for r in rows:
    g = PAT.match(r['file']).groupdict()
    r['_acq'] = (g['well'], g['pos'], g['t'])


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


def sp(x, y):
    a, b = rank(x), rank(y)
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((p - ma) ** 2 for p in a)
    vb = sum((p - mb) ** 2 for p in b)
    if va <= 0 or vb <= 0:
        return float('nan')
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / math.sqrt(va * vb)


cl = collections.defaultdict(list)
for r in rows:
    cl[r['_acq']].append((float(r['phi']), float(r['meanq_expert'])))
keys = list(cl)
print('BT-474: %d images in %d acquisitions' % (len(rows), len(keys)))
print('point estimate rho = %+.4f'
      % sp([float(r['phi']) for r in rows],
           [float(r['meanq_expert']) for r in rows]))
print()
print('acquisition-clustered bootstrap, 5,000 reps, five seeds:')
print('%8s %10s %10s %10s' % ('seed', 'lo(2.5%)', 'hi(97.5%)', 'P(rho<=0)'))
los = []
for seed in (20260811, 1, 7, 42, 2026):
    random.seed(seed)
    out = []
    for _ in range(5000):
        s = []
        for _ in range(len(keys)):
            s.extend(cl[keys[random.randrange(len(keys))]])
        v = sp([q[0] for q in s], [q[1] for q in s])
        if v == v:
            out.append(v)
    out.sort()
    lo = out[int(0.025 * len(out))]
    hi = out[int(0.975 * len(out)) - 1]
    p0 = sum(1 for v in out if v <= 0) / len(out)
    los.append(lo)
    print('%8d %+10.4f %+10.4f %10.4f' % (seed, lo, hi, p0))
print()
print('lower bound across seeds: %+.4f to %+.4f' % (min(los), max(los)))
print('-> the 2.5%% bound sits ON zero; significance is not robust at this level')
