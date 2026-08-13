"""The check nothing performs: does any interval in a table contradict the
same quantity in the text?"""
import io, sys, re, pathlib, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pypdf import PdfReader

R = pathlib.Path(r'D:\paper1_mechanobiology - Copy (2)')
t = re.sub(r'\s+', ' ', ' '.join(
    p.extract_text() or '' for p in PdfReader(R / 'paper2_bib' / 'main.pdf').pages))

# every quantity that appears both in prose and in Table 7 panel (c)
PAIRS = [
    ('BT-474 expert', r'raw\s*\u03c1?\s*=?\s*0\.26.{0,40}?\[\s*\u22120\.01\s*,\s*0\.51',
     r'\+?0\.26.{0,30}?\u22120\.01.{0,20}?\+?0\.51'),
    ('BT-474 ours', r'extension recovers\s*\u03c1?\s*=?\s*0\.66\s*\[0\.44\s*,\s*0\.78',
     r'\+?0\.66.{0,20}?\+?0\.44.{0,20}?\+?0\.78'),
    ('BT-474 Cellpose', r'Cellpose masks is\s*\u03c1?\s*=?\s*\u22120\.01\s*\[\u22120\.28\s*,\s*0\.24',
     r'\u22120\.01.{0,20}?\u22120\.28.{0,20}?\+?0\.24'),
]
print('=== text vs Table 7 panel (c), same quantity ===')
bad = 0
for lab, tx, tb in PAIRS:
    intext = re.search(tx, t) is not None
    intab = re.search(tb, t) is not None
    ok = intext and intab
    bad += not ok
    print('  %-18s in text: %-5s   in table: %-5s   %s'
          % (lab, intext, intab, 'AGREE' if ok else '** CHECK **'))

print()
print('=== every bracketed interval printed anywhere, grouped by value ===')
iv = collections.Counter(re.findall(r'\[\s*[\u2212+-]?\d\.\d\d\s*,\s*[\u2212+-]?\d\.\d\d\s*\]', t))
print('  distinct intervals printed: %d' % len(iv))
old = ['[0.10, 0.41]', '[0.54, 0.75]', '[\u22120.18, 0.17]']
for o in old:
    n = t.count(o)
    print('  superseded unclustered interval %-16s still printed: %d' % (o, n))
print()
print('failures: %d' % bad)
