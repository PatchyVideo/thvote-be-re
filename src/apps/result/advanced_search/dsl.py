"""高级搜索 DSL:文法、AST、解析(设计稿 §四/§五)。

语法(需求文档 §846-923):6 种原子条件 + AND/OR/括号,AND 结合紧于 OR。
解析产物是与 lark 解耦的 frozen dataclass AST,B-053 直接消费。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Union

from lark import Lark, Token, Transformer
from lark import exceptions as lark_exceptions

from src.common.exceptions import ValidationError

MAX_QUERY_LENGTH = 1024
MAX_ATOMS = 20
MAX_DEPTH = 5


@dataclass(frozen=True)
class QCond:
    qcode: str
    ocode: str


@dataclass(frozen=True)
class CharAny:
    names: tuple[str, ...]


@dataclass(frozen=True)
class CharFirst:
    name: str


@dataclass(frozen=True)
class MusicAny:
    names: tuple[str, ...]


@dataclass(frozen=True)
class MusicFirst:
    name: str


@dataclass(frozen=True)
class And:
    children: tuple["Node", ...]


@dataclass(frozen=True)
class Or:
    children: tuple["Node", ...]


Node = Union[QCond, CharAny, CharFirst, MusicAny, MusicFirst, And, Or]

_GRAMMAR = r"""
?expr: or_expr
?or_expr: and_expr ("OR" and_expr)*
?and_expr: atom ("AND" atom)*
?atom: "(" expr ")"
     | q_cond
     | chars_any
     | chars_first
     | musics_any
     | musics_first

q_cond: QNAME "=" INT
chars_any: "chars" ":" "[" string ("," string)* "]"
chars_first: "chars_first" "=" string
musics_any: "musics" ":" "[" string ("," string)* "]"
musics_first: "musics_first" "=" string

string: ESCAPED_STRING
QNAME: /q\d+/

%import common.ESCAPED_STRING
%import common.INT
%import common.WS
%ignore WS
"""

_PARSER = Lark(_GRAMMAR, start="expr")


class _ToAst(Transformer):
    """lark 树 → frozen dataclass AST。

    `?or_expr`/`?and_expr` 单子节点时被 lark 内联,只有真正出现
    OR/AND 时才会调用对应方法——不会产生单儿子的 And/Or 包装。
    """

    def string(self, items: list[Token]) -> str:
        return json.loads(str(items[0]))  # ESCAPED_STRING 与 JSON 字符串同格式

    def q_cond(self, items: list[Token]) -> QCond:
        return QCond(qcode=str(items[0])[1:], ocode=str(items[1]))

    def chars_any(self, items: list[str]) -> CharAny:
        return CharAny(names=tuple(items))

    def chars_first(self, items: list[str]) -> CharFirst:
        return CharFirst(name=items[0])

    def musics_any(self, items: list[str]) -> MusicAny:
        return MusicAny(names=tuple(items))

    def musics_first(self, items: list[str]) -> MusicFirst:
        return MusicFirst(name=items[0])

    def or_expr(self, items: list[Node]) -> Or:
        return Or(children=tuple(items))

    def and_expr(self, items: list[Node]) -> And:
        return And(children=tuple(items))


def parse_query(query: str) -> Node:
    """query 字符串 → AST。语法错/超长 → 可辨识 ValidationError。"""
    if len(query) > MAX_QUERY_LENGTH:
        raise ValidationError(
            "ADVANCED_SEARCH_TOO_COMPLEX",
            human_readable_message=f"高级搜索指令过长(超过 {MAX_QUERY_LENGTH} 字符)",
        )
    try:
        tree = _PARSER.parse(query)
        return _ToAst().transform(tree)
    except lark_exceptions.UnexpectedInput as exc:
        line = getattr(exc, "line", "?")
        column = getattr(exc, "column", "?")
        raise ValidationError(
            "ADVANCED_SEARCH_SYNTAX_ERROR",
            human_readable_message=f"高级搜索语法错误(第 {line} 行第 {column} 列附近)",
        ) from exc
    except lark_exceptions.VisitError as exc:
        raise ValidationError(
            "ADVANCED_SEARCH_SYNTAX_ERROR",
            human_readable_message="高级搜索语法错误",
        ) from exc
