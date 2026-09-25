import os

base_path = r'D:/创建skill/skills/chip-daily-report/芯片行业日报_20260808.md'
snip_path = r'D:/创建skill/skills/chip-daily-report/insert_snippet.md'

with open(base_path, encoding='utf-8') as f:
    base = f.read()
with open(snip_path, encoding='utf-8') as f:
    snip = f.read()

marker = '## 产业链关联'
assert marker in base, 'marker not found'
idx = base.index(marker)
prefix = base[:idx]
if not prefix.endswith('\n\n'):
    prefix += '\n' if prefix.endswith('\n') else '\n\n'
new = prefix + snip.strip('\n') + '\n\n' + base[idx:]

with open(base_path, 'w', encoding='utf-8') as f:
    f.write(new)

for h in ['## 市场与需求', '## 政策与监管', '## 资本与投融资']:
    print(h, '->', h in new)
print('inserted. new length =', len(new))
