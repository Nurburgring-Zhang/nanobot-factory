import jaJP from './src/locales/ja-JP';

const cc = jaJP.collectionCenter;
if (cc) {
  const keys = Object.keys(cc).sort();
  console.log('collectionCenter has ' + keys.length + ' keys');
  console.log('first 5:', keys.slice(0, 5));
  console.log('last 5:', keys.slice(-5));
} else {
  console.log('collectionCenter is undefined');
}
