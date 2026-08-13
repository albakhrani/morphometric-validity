"""Step 0 -- try to recover image_id -> file_name from the LIVECell COCO json."""
import io, sys, re, csv, json, glob, os, pathlib, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

R = pathlib.Path(r'D:\paper1_mechanobiology - Copy (2)')

print('=== COCO json files on disk ===')
js = [p for p in glob.glob(str(R / '**' / '*.json'), recursive=True)
      if '.venv' not in p and 'coco' in os.path.basename(p).lower()]
for p in js:
    print('  %-64s %10d bytes' % (os.path.relpath(p, R), os.path.getsize(p)))
if not js:
    print('  none found')
    sys.exit(1)

mapping = {}
per_file = {}
for p in js:
    try:
        d = json.load(open(p, encoding='utf-8'))
    except Exception as e:
        print('  !! %s unreadable: %s' % (os.path.basename(p), e))
        continue
    imgs = d.get('images', [])
    per_file[os.path.basename(p)] = len(imgs)
    for im in imgs:
        if 'id' in im and 'file_name' in im:
            mapping[str(im['id'])] = im['file_name']
print()
print('  images per file: %s' % per_file)
print('  distinct image ids collected: %d' % len(mapping))

rows = list(csv.DictReader(
    open(R / 'fig7_expanded' / 'time_out' / 'time_per_image.csv', encoding='utf-8')))
ids = [r['image_id'] for r in rows]
hit = sum(1 for i in ids if i in mapping)
print()
print('=== join test against time_per_image.csv ===')
print('  rows %d, ids resolved %d (%.1f%%)' % (len(rows), hit, 100 * hit / len(rows)))

if hit < len(rows):
    print('  -> INCOMPLETE JOIN. Taking branch 3b.')
    sys.exit(2)

# validate: lineage prefix of the joined filename must match the CSV column
PAT = re.compile(r'^(?P<lin>[A-Za-z0-9\-]+)_Phase_(?P<well>[A-Z]\d+)_'
                 r'(?P<pos>\d+)_(?P<t>\d+d\d+h\d+m)_(?P<crop>\d+)\.tif$')
mismatch = unparsed = 0
for r in rows:
    fn = mapping[r['image_id']]
    m = PAT.match(fn)
    if not m:
        unparsed += 1
        continue
    if m.group('lin') != r['cell_type']:
        mismatch += 1
print('  filenames unparsed: %d   lineage mismatches: %d' % (unparsed, mismatch))
if unparsed or mismatch:
    print('  -> JOIN NOT VALIDATED. Taking branch 3b.')
    sys.exit(3)

print('  -> JOIN VALIDATED on all %d rows. Taking branch 3a.' % len(rows))
NAME = {'BT474': 'BT-474', 'BV2': 'BV-2'}
by = collections.defaultdict(list)
for r in rows:
    g = PAT.match(mapping[r['image_id']]).groupdict()
    r['_acq'] = (g['lin'], g['well'], g['pos'], g['t'])
    r['_pos'] = (g['lin'], g['well'], g['pos'])
    r['_well'] = (g['lin'], g['well'])
    by[NAME.get(r['cell_type'], r['cell_type'])].append(r)

print()
print('=== atlas cluster structure (4,875 images, all three splits) ===')
print('  overall: %d images, %d acquisitions, %d positions, %d wells'
      % (len(rows), len({r['_acq'] for r in rows}),
         len({r['_pos'] for r in rows}), len({r['_well'] for r in rows})))
print('  %-9s %7s %13s %10s %6s' % ('lineage', 'images', 'acquisitions',
                                    'positions', 'wells'))
for L in sorted(by):
    v = by[L]
    print('  %-9s %7d %13d %10d %6d'
          % (L, len(v), len({r['_acq'] for r in v}),
             len({r['_pos'] for r in v}), len({r['_well'] for r in v})))
c = collections.Counter(collections.Counter(r['_acq'] for r in rows).values())
print('  crops per acquisition: %s' % dict(sorted(c.items())))
json.dump({r['image_id']: mapping[r['image_id']] for r in rows},
          open(R.parent / 'atlas_id_map.json', 'w'), indent=0)
print()
print('  mapping written for reuse')
