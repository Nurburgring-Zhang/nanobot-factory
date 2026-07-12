// Check 4 brand-name keys in zh-CN
const fs = require('fs');
const rawZh = fs.readFileSync('src/locales/zh-CN.ts', 'utf8');
let zhJs = rawZh.replace(/export default\s*/, '').replace(/as const\s*$/, '');
const zh = new Function('return (' + zhJs + ')')();
console.log('common.appSubName =', JSON.stringify(zh.common && zh.common.appSubName));
console.log('auth.loginSubtitle =', JSON.stringify(zh.auth && zh.auth.loginSubtitle));
console.log('annotation.colId =', JSON.stringify(zh.annotation && zh.annotation.colId));
console.log('engines.colId =', JSON.stringify(zh.engines && zh.engines.colId));
