import io, sys, re, csv, math, pathlib, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

R = pathlib.Path(r'D:\paper1_mechanobiology - Copy (2)')
rows = list(csv.DictReader(
    open(R / 'fig7_expanded' / 'time_out' / 'time_per_image.csv', encoding='utf-8')))
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


def raw(s):
    return pear(rank([float(r['phi']) for r in s]),
                rank([float(r['mean_q']) for r in s]))


def partial(s):
    p = rank([float(r['phi']) for r in s])
    q = rank([float(r['mean_q']) for r in s])
    a = rank([float(r['mean_area']) for r in s])
    return pear(resid(p, a), resid(q, a))


pub = {NAME.get(r['cell_type'], r['cell_type']): r for r in csv.DictReader(
    open(R / 'final_table_all' / 'final_lineage_table.csv', encoding='utf-8'))}

print('=' * 76)
print('VALIDATION -- the 4,875-image basis reproduces the published tier table')
print('=' * 76)
print('  %-9s %6s %9s %9s %9s %9s %6s' % ('lineage', 'n', 'raw pub',
                                          'raw calc', 'part pub', 'part calc', 'tier'))
worst = 0.0
for L in sorted(by):
    rr, pp = raw(by[L]), partial(by[L])
    worst = max(worst, abs(rr - float(pub[L]['raw_rho'])),
                abs(pp - float(pub[L]['partial_rho'])))
    print('  %-9s %6d %9.3f %9.3f %9.3f %9.3f %6s'
          % (L, len(by[L]), float(pub[L]['raw_rho']), rr,
             float(pub[L]['partial_rho']), pp, pub[L].get('tier', '?')))
print('  worst deviation: %.4f  -> %s'
      % (worst, 'reproduces' if worst < 0.005 else '** DOES NOT REPRODUCE **'))

print()
print('=' * 76)
print('2. DO ANY TIER CRITERIA DEPEND ON AN INTERVAL OR A p-VALUE?')
print('=' * 76)
s = (R / 'paper2_bib' / 'body.tex').read_text(encoding='utf-8', errors='replace')
flat = re.sub(r'\s+', ' ', s)
i = flat.find('A trajectory was called robust')
seg = flat[i:i + 1150]
print(seg)
print()
for term, note in (('confidence interval', 'interval dependence'),
                   ('bootstrap', 'resampling dependence'),
                   ('$p', 'p-value dependence'), ('p =', 'p-value dependence'),
                   ('significan', 'significance dependence')):
    print('  %-22s in the criteria text: %s' % (note, term in seg))
