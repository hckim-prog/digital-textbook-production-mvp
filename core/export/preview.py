"""Built-in sample preview: never reads a user's manuscript or calls an API."""
from core.master import Block, Master
from core.export.outputs import web
from core.manuscript.structure import node, validate


def sample_master():
    blocks=[Block('b1','paragraph','Chapter 1 프로그램 시작하기'),
            Block('b2','paragraph','1.1 처음 만나는 프로그램'),
            Block('b3','paragraph','프로그램은 작은 명령을 순서대로 실행합니다. 개념을 읽고 예제를 실행하면서 결과를 확인해 보세요. 이 페이지는 디자인 확인용 예시입니다.'),
            Block('b4','code-block','#include <iostream>\n\nint main() {\n    std::cout << "Hello, world!";\n    return 0;\n}'),
            Block('b5','code-output','Hello, world!'),
            Block('b6','paragraph','1.2 실행 결과 이해하기'),
            Block('b7','table',rows=[['구성 요소','역할'],['입력','프로그램이 전달받는 값'],['출력','실행 결과를 화면에 표시']]),
            Block('b8','procedure-step','1. 코드를 입력한 뒤 실행 버튼을 누릅니다.'),
            Block('b9','exercise','연습문제: 화면에 표시할 문장을 바꾸어 실행해 보세요.')]
    m=Master('작은 코드로 시작하는 프로그래밍','design-sample.docx','design-sample',blocks)
    m.outline=validate(m,[node(blocks[0],1),node(blocks[1],2),node(blocks[5],2)])
    return m


def create_preview(dest, theme='auto'):
    return web(sample_master(),dest/'no-assets',dest/theme,theme=theme)
