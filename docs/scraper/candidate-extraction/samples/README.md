# THBWiki 角色数据源样本

抓取自 THBWiki 页面 `官方角色列表/角色数据`（真正的候选角色结构化数据源，详见
`docs/superpowers/specs/2026-07-20-thbwiki-candidate-extraction-design.md` 第 3 节）。

- `character_data_wikitext.txt`：2026-07-20 通过 `https://thwiki.cc/api.php`
  （`action=query&prop=revisions&rvprop=content&titles=官方角色列表/角色数据`）
  拉取的原始 wikitext（page revision 968155）。
- `character_data.csv`：对上面 wikitext 做的一次性解析（按 `==`/`===` 分节 + 逗号切
  分字段），共 179 条角色记录，用于人工核对数据结构、以及后续给
  `candidate_sync` 抽取器的规则解析器/单元测试当样本。

**用途仅限研究与开发参照，不是候选清单成品**——多数角色的中文名/日文名/英文名列
是空的（wiki 上标注为"从词条页自动获取"），本轮工具实现后需要再批量拉每个词条页
的 `{{官方角色信息}}` 模板参数补全，具体见设计文档第 3、4 节。
