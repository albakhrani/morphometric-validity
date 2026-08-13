import io, sys, re, csv, math, random, glob, os, pathlib, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

R = pathlib.Path(r'D:\paper1_mechanobiology - Copy (2)')
D = R / 'release_repo' / 'data'
random.seed(20260811)
REPS = 1000
PAT = re.compile(r'^(?P<lin>[A-Za-z0-9\-]+)_Phase_(?P<well>[A-Z]\d+)_'
                 r'(?P<pos>\d+)_(?P<t>\d+d\d+h\d+m)_(?P<crop>\d+)\.tif$')

rows = list(csv.DictReader(open(D / 'mask_source_comparison_per_image.csv',
                                encoding='utf-8')))
for r in rows:
    g = PAT.match(r['file']).groupdict()
    r['_acq'] = (g['lin'], g['well'], g['pos'], g['t'])
NAME = {'BT474': 'BT-474', 'BV2': 'BV-2'}
by = collections.defaultdict(list)
for r in rows:
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


def sp(x, y):
    return pear(rank(x), rank(y))


def cboot(sub, col):
    data = [(float(r['phi']), float(r[col]), r['_acq'])
            for r in sub if r[col] not in ('', 'nan')]
    cl = collections.defaultdict(list)
    for d in data:
        cl[d[2]].append(d)
    keys = list(cl)
    out = []
    for _ in range(REPS):
        s = []
        for _ in range(len(keys)):
            s.extend(cl[keys[random.randrange(len(keys))]])
        v = sp([q[0] for q in s], [q[1] for q in s])
        if v == v:
            out.append(v)
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1], len(keys)


print('=' * 76)
print('STEP 3.3 -- all eight lineages, expert coefficient, acquisition-clustered')
print('=' * 76)
print('%-9s %8s %22s %22s' % ('lineage', 'rho', 'images CI', 'acquisition CI'))
res = {}
for L in sorted(by):
    sub = by[L]
    x = [float(r['phi']) for r in sub if r['meanq_expert'] not in ('', 'nan')]
    y = [float(r['meanq_expert']) for r in sub if r['meanq_expert'] not in ('', 'nan')]
    rho = sp(x, y)
    d = [(float(r['phi']), float(r['meanq_expert'])) for r in sub
         if r['meanq_expert'] not in ('', 'nan')]
    u = []
    for _ in range(REPS):
        s = [d[random.randrange(len(d))] for _ in range(len(d))]
        v = sp([q[0] for q in s], [q[1] for q in s])
        if v == v:
            u.append(v)
    u.sort()
    ulo, uhi = u[int(0.025 * len(u))], u[int(0.975 * len(u)) - 1]
    clo, chi, k = cboot(sub, 'meanq_expert')
    res[L] = (rho, ulo, uhi, clo, chi, k)
    flag = '' if (clo > 0 or chi < 0) else '   ** now includes zero **'
    print('%-9s %+8.3f  [%+.3f, %+.3f]   [%+.3f, %+.3f]  n=%d%s'
          % (L, rho, ulo, uhi, clo, chi, k, flag))

print()
print('=' * 76)
print('STEP 3.5 -- direction counts under C2 with ACQUISITION-clustered intervals')
print('=' * 76)
SUP = ['A172', 'BT-474', 'Huh7', 'SH-SY5Y', 'SK-OV-3', 'SkBr3']
SRC = [('meanq_conncomp', 'connected components', 0.111),
       ('meanq_oursalt', 'ours, measurement-optimal', 0.576),
       ('meanq_ours', 'ours, detection-optimal', 0.709),
       ('meanq_cellpose', 'Cellpose', 0.815)]
print('%-26s %6s %14s %16s' % ('source', 'F1', 'C2 (images)', 'C2 (clustered)'))
for col, nm, f1 in SRC:
    n_u = n_c = 0
    fails_c = []
    for L in SUP:
        sub = by[L]
        e = res[L][0]
        d = [(float(r['phi']), float(r[col])) for r in sub
             if r[col] not in ('', 'nan')]
        if len(d) < 4:
            continue
        rho = sp([q[0] for q in d], [q[1] for q in d])
        u = []
        for _ in range(REPS):
            s = [d[random.randrange(len(d))] for _ in range(len(d))]
            v = sp([q[0] for q in s], [q[1] for q in s])
            if v == v:
                u.append(v)
        u.sort()
        ulo, uhi = u[int(0.025 * len(u))], u[int(0.975 * len(u)) - 1]
        clo, chi, _ = cboot(sub, col)
        sign = (rho > 0) == (e > 0)
        if sign and not (ulo <= 0 <= uhi):
            n_u += 1
        if sign and not (clo <= 0 <= chi):
            n_c += 1
        else:
            fails_c.append(L)
    print('%-26s %6.3f %14d %16d   fails: %s' % (nm, f1, n_u, n_c, fails_c))

print()
print('=' * 76)
print("STEP 3.6 -- A172's coverage-inversion result")
print('=' * 76)
a = by['A172']
full = [(float(r['phi']), float(r['meanq_expert'])) for r in a
        if r['meanq_expert'] not in ('', 'nan')]
cc = [(float(r['phi']), float(r['meanq_expert'])) for r in a
      if r['meanq_expert'] not in ('', 'nan') and r['meanq_conncomp'] not in ('', 'nan')]
print('  expert rho over all %d A172 images        : %+.3f' % (len(full), sp([q[0] for q in full], [q[1] for q in full])))
print('  expert rho over the %d CC-measurable ones : %+.3f' % (len(cc), sp([q[0] for q in cc], [q[1] for q in cc])))
print('  -> this compares two computations on the same expert annotations;')
print('     it estimates no population parameter, so clustering does not apply.')
