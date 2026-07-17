// 表格列定义(DataTable 用)。cell-<key> 具名插槽可自定义单元格渲染。
export interface Column {
  key: string
  label: string
  width?: string
}
