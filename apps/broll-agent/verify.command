#!/bin/zsh
set -euo pipefail
cd "${0:A:h}"
python3 -m compileall -q . -x 'node_modules|runtime|data'
python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/*.cjs
print '制作引擎的存储、Agent、HTTP、渲染与界面回归全部通过；产品效果以用户审看为准。'
