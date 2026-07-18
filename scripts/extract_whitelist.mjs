// scripts/extract_whitelist.mjs
// 用法: node scripts/extract_whitelist.mjs <前端仓库根> <后端仓库根>
// 例:   node scripts/extract_whitelist.mjs /data/sunyunbo/www/Touhou-Vote /data/sunyunbo/www/Thvote-be/thvote-be-re
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const [frontRoot, backRoot] = process.argv.slice(2);
if (!frontRoot || !backRoot) {
  console.error('usage: node extract_whitelist.mjs <frontRoot> <backRoot>');
  process.exit(1);
}

function extractArray(tsText, varName) {
  // 取 "<varName>...= [" 后到匹配 "]" 的数组字面量文本。
  // 注意：不能直接找 varName 之后第一个 "["——声明形如
  // `export const characterList: Character[] = [...]`，类型注解
  // `Character[]` 里的空数组括号会先被匹配到。改为先找到赋值号 "="，
  // 再从其后找第一个 "[" 作为数组字面量起点。
  const nameIdx = tsText.indexOf(varName);
  if (nameIdx < 0) throw new Error(`declaration for ${varName} not found`);
  const eqIdx = tsText.indexOf('=', nameIdx);
  if (eqIdx < 0) throw new Error(`assignment for ${varName} not found`);
  const start = tsText.indexOf('[', eqIdx);
  if (start < 0) throw new Error(`array for ${varName} not found`);
  let depth = 0, i = start;
  for (; i < tsText.length; i++) {
    const ch = tsText[i];
    if (ch === '[') depth++;
    else if (ch === ']') { depth--; if (depth === 0) { i++; break; } }
  }
  const literal = tsText.slice(start, i);
  // 纯对象字面量数组，安全求值
  return new Function(`return (${literal});`)();
}

function build(list, kind /* 'character'|'music' */) {
  return list.map((e, idx) => ({
    id: String(e.id),
    name: String(e.name ?? ''),
    name_jp: String(e.origname ?? ''),
    work: kind === 'character' ? (e.work ?? []) : [],
    kind: e.kind ?? [],
    date: typeof e.date === 'number' ? e.date : null,
    album: kind === 'music' ? (e.album ?? null) : null,
    system_id: idx,
  }));
}

const charTs = readFileSync(join(frontRoot, 'packages/shared/data/character.ts'), 'utf8');
const musicTs = readFileSync(join(frontRoot, 'packages/shared/data/music.ts'), 'utf8');

const chars = build(extractArray(charTs, 'characterList'), 'character');
const musics = build(extractArray(musicTs, 'musicList'), 'music');

const outDir = join(backRoot, 'src/apps/result/data');
mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, 'whitelist_character.json'), JSON.stringify(chars, null, 2) + '\n');
writeFileSync(join(outDir, 'whitelist_music.json'), JSON.stringify(musics, null, 2) + '\n');
console.log(`characters=${chars.length} musics=${musics.length}`);
