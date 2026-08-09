"""exe 로 묶을 때 쓰는 진입점 — 패키지를 정상적으로 import 하는 얇은 껍데기.

⚠️ 왜 이 파일이 따로 필요한가 (실제로 겪은 문제):
PyInstaller 에 `src/clap_launcher/__main__.py` 를 그대로 넘기면, PyInstaller 는 그 파일을
**패키지 밖의 단독 스크립트**로 실행한다. 그런데 그 파일 안에는 `from .console import ...`
같은 상대 import 가 있고, 단독 스크립트에는 '부모 패키지'가 없으므로 이렇게 죽는다.

    ImportError: attempted relative import with no known parent package

그래서 패키지를 제대로 import 해서 main() 만 불러주는 진입점을 따로 둔다.
(빌드할 때 --paths 로 src 를 알려주므로 clap_launcher 를 찾을 수 있다)

⚠️ 이 파일은 `python tools/entry_point.py` 로도 실행되지 않는다 — 그건 정상이다.
   개발 중에는 `python -m clap_launcher` 를 쓰면 된다. 이 파일은 오직 빌드용이다.
"""

import sys

from clap_launcher.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
