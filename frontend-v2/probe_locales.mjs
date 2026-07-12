import fs from 'node:fs';
import path from 'node:path';
import { transformSync } from 'esbuild';

const locales = ['zh-CN','en-US','ja-JP','ko-KR','fr-FR','de-DE','es-ES','ru-RU','ar-SA'];
for (const loc of locales) {
  const fp = path.join('D:/Hermes/生产平台/nanobot-factory/frontend-v2/src/locales', loc + '.ts');
  const content = fs.readFileSync(fp, 'utf-8');
  try {
    const out = transformSync(content, { loader: 'ts', format: 'cjs' });
    let stripped = out.text.replace(/exports\.default = /, 'module.exports = ');
    const tmpPath = path.join(process.env.TEMP || 'C:/tmp', 'locale_' + loc + '.cjs');
    fs.writeFileSync(tmpPath, stripped);
    delete require.cache[tmpPath];
    const data = require(tmpPath);
    if (!data.workflowBuilder) {
      console.log(loc + ': MISSING workflowBuilder!');
      continue;
    }
    const keys = Object.keys(data.workflowBuilder).filter(k => /^t\d{3}$/.test(k));
    console.log(loc + ': ' + keys.length + ' keys, t000="' + data.workflowBuilder.t000.substring(0, 30) + '"');
    fs.unlinkSync(tmpPath);
  } catch (e) {
    console.log(loc + ': PARSE ERROR ' + e.message);
  }
}
