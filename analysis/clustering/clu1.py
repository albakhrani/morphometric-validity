"""Step 1 -- cluster structure from the LIVECell filenames. No edits."""
import io, sys, re, csv, pathlib, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

D = pathlib.Path(r'D:\paper1_mechanobiology - Copy (2)\release_repo\data')
rows = list(csv.DictReader(open(D / 'mask_source_comparison_per_image.csv',
                                encoding='utf-8')))

# LIVECell: {lineage}_Phase_{well}_{position}_{timestamp}_{crop}.tif
PAT = re.compile(r'^(?P<lin>[A-Za-z0-9\-]+)_Phase_(?P<well>[A-Z]\d+)_'
                 r'(?P<pos>\d+)_(?P<t>\d+d\d+h\d+m)_(?P<crop>\d+)\.tif$')

print('=== parsing rule, validated on a sample ===')
print('  {lineage}_Phase_{well}_{position}_{timestamp}_{crop}.tif')
ok = bad = 0
samples = []
for r in rows:
    m = PAT.match(r['file'])
    if m:
        ok += 1
        if len(samples) < 5:
            samples.append((r['file'], m.groupdict()))
    else:
        bad += 1
        if bad <= 5:
            print('  UNPARSED: %r' % r['file'])
print('  parsed %d of %d filenames (%d unparsed)' % (ok, ok + bad, bad))
for f, g in samples:
    print('   %-42s -> lin=%-7s well=%-3s pos=%s t=%-9s crop=%s'
          % (f, g['lin'], g['well'], g['pos'], g['t'], g['crop']))
if bad:
    print('  !! unparsed filenames present -- stopping before any count')
    sys.exit(1)

acq, well, seq, lin = set(), set(), set(), collections.defaultdict(
    lambda: {'img': 0, 'acq': set(), 'well': set(), 'seq': set()})
percrop = collections.Counter()
for r in rows:
    g = PAT.match(r['file']).groupdict()
    a = (g['lin'], g['well'], g['pos'], g['t'])      # acquisition = one field, one time
    w = (g['lin'], g['well'], g['pos'])              # a position followed over time
    s = (g['lin'], g['well'])                        # a well, all positions and times
    acq.add(a); well.add(w); seq.add(s)
    percrop[a] += 1
    L = lin[r['cell_type']]
    L['img'] += 1
    L['acq'].add(a); L['well'].add(w); L['seq'].add(s)

print()
print('=== 1. acquisitions (lineage + well + position + timepoint) ===')
print('  distinct acquisitions: %d   images: %d' % (len(acq), len(rows)))
c = collections.Counter(percrop.values())
print('  crops per acquisition: %s' % dict(sorted(c.items())))
print('  uniformly four? %s' % (set(percrop.values()) == {4}))

print()
print('=== 2. positions followed over time (lineage + well + position) ===')
print('  distinct: %d' % len(well))
print('=== 3. wells (lineage + well) ===')
print('  distinct: %d' % len(seq))

print()
print('=== 4. per lineage ===')
print('%-9s %7s %13s %11s %7s %s' % ('lineage', 'images', 'acquisitions',
                                     'positions', 'wells', 'img/acq'))
for k in sorted(lin):
    v = lin[k]
    print('%-9s %7d %13d %11d %7d %7.2f'
          % (k, v['img'], len(v['acq']), len(v['well']), len(v['seq']),
             v['img'] / len(v['acq'])))

print()
print('=== 5. duplicated field names ===')
fn = collections.Counter(r['file'] for r in rows)
dup = {k: v for k, v in fn.items() if v > 1}
print('  file names appearing more than once in this table: %d' % len(dup))
print('  (the manuscript documents 52 duplicated field names in the 1,564-record')
print('   test-split pool; this table is the 1,420 post-attachment subset)')
