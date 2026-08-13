import io, sys, re, csv, math, random, pathlib, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

D = pathlib.Path(r'D:\paper1_mechanobiology - Copy (2)\release_repo\data')
REPS = 3000
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


def sp(x, y):
    a, b = rank(x), rank(y)
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((p - ma) ** 2 for p in a)
    vb = sum((p - mb) ** 2 for p in b)
    if va <= 0 or vb <= 0:
        return float('nan')
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / math.sqrt(va * vb)


def ci(sub, col, clustered, seed=20260811):
    random.seed(seed)
    d = [(float(r['phi']), float(r[col]), r['_acq'])
         for r in sub if r[col] not in ('', 'nan')]
    if clustered:
        cl = collections.defaultdict(list)
        for x in d:
            cl[x[2]].append(x)
        keys = list(cl)
    out = []
    for _ in range(REPS):
        if clustered:
            s = []
            for _ in range(len(keys)):
                s.extend(cl[keys[random.randrange(len(keys))]])
        else:
            s = [d[random.randrange(len(d))] for _ in range(len(d))]
        v = sp([q[0] for q in s], [q[1] for q in s])
        if v == v:
            out.append(v)
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1], len(d)


PRINTED = {  # lineage: (expert, ours, cellpose) as (rho, lo, hi)
    'SK-OV-3': ((-0.76, -0.83, -0.68), (-0.79, -0.84, -0.73), (-0.89, -0.92, -0.85)),
    'SH-SY5Y': ((-0.75, -0.82, -0.66), (-0.79, -0.86, -0.70), (-0.82, -0.88, -0.74)),
    'A172':    ((-0.47, -0.58, -0.33), (-0.10, -0.29, +0.09), (-0.69, -0.79, -0.57)),
    'MCF7':    ((-0.21, -0.35, -0.06), (+0.44, +0.31, +0.57), (-0.82, -0.87, -0.74)),
    'BV-2':    ((+0.16, -0.01, +0.32), (+0.88, +0.81, +0.93), (+0.61, +0.46, +0.74)),
    'BT-474':  ((+0.26, +0.10, +0.41), (+0.66, +0.54, +0.75), (-0.01, -0.18, +0.17)),
    'Huh7':    ((+0.42, +0.31, +0.52), (+0.70, +0.62, +0.77), (+0.28, +0.15, +0.39)),
    'SkBr3':   ((+0.91, +0.86, +0.93), (+0.92, +0.88, +0.94), (+0.95, +0.93, +0.96)),
}
COLS = [('meanq_expert', 'Expert'), ('meanq_ours', 'Ours'),
        ('meanq_cellpose', 'Cellpose')]
ORDER = ['SK-OV-3', 'SH-SY5Y', 'A172', 'MCF7', 'BV-2', 'BT-474', 'Huh7', 'SkBr3']

print('VALIDATION -- unclustered recomputation against the printed panel (c)')
worst = 0.0
for L in ORDER:
    for j, (col, nm) in enumerate(COLS):
        sub = by[L]
        d = [r for r in sub if r[col] not in ('', 'nan')]
        rho = sp([float(r['phi']) for r in d], [float(r[col]) for r in d])
        worst = max(worst, abs(rho - PRINTED[L][j][0]))
print('  worst point-estimate deviation: %.4f  -> %s'
      % (worst, 'reproduces' if worst < 0.006 else '** MISMATCH **'))
if worst >= 0.006:
    sys.exit(1)

print()
print('PANEL (c) UNDER ACQUISITION CLUSTERING (%d reps)' % REPS)
print('%-9s %-9s %22s %24s %s' % ('lineage', 'source', 'printed', 'clustered', 'flag'))
newrow = {}
for L in ORDER:
    cells = []
    for j, (col, nm) in enumerate(COLS):
        sub = by[L]
        d = [r for r in sub if r[col] not in ('', 'nan')]
        rho = sp([float(r['phi']) for r in d], [float(r[col]) for r in d])
        lo, hi, n = ci(sub, col, True)
        p = PRINTED[L][j]
        was_excl = not (p[1] <= 0 <= p[2])
        now_excl = not (lo <= 0 <= hi)
        flag = ''
        if was_excl and not now_excl:
            flag = '  ** STOPS EXCLUDING ZERO **'
        print('%-9s %-9s  %+.2f [%+.2f, %+.2f]   %+.3f [%+.3f, %+.3f]%s'
              % (L, nm, p[0], p[1], p[2], rho, lo, hi, flag))
        cells.append('$%+.2f$ [$%+.2f$, $%+.2f$]'.replace('+', '')
                     if False else '$%s%.2f$ [$%s%.2f$, $%s%.2f$]'
                     % ('+' if rho >= 0 else '-', abs(rho),
                        '+' if lo >= 0 else '-', abs(lo),
                        '+' if hi >= 0 else '-', abs(hi)))
    newrow[L] = cells
    print()

print('=== LaTeX rows for panel (c) ===')
TIER = {'SK-OV-3': 'A', 'SH-SY5Y': 'A', 'A172': 'B', 'MCF7': 'C', 'BV-2': 'C',
        'BT-474': 'A', 'Huh7': 'A', 'SkBr3': 'A'}
NN = {'SK-OV-3': 308, 'SH-SY5Y': 160, 'A172': 136, 'MCF7': 168, 'BV-2': 135,
      'BT-474': 152, 'Huh7': 200, 'SkBr3': 160}
for L in ORDER:
    print('%s & %s & %d & %s & %s & %s \\\\'
          % (L, TIER[L], NN[L], newrow[L][0], newrow[L][1], newrow[L][2]))
